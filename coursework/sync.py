"""Canvas sync: files, files linked from elsewhere, and assignment descriptions.

Per course, one sync pulls:
  1. Everything on the Files tab, mirroring the professor's folders (3 levels max).
  2. "Hidden" files: files a professor links from a calendar event, a Canvas
     page or an assignment description without listing them on the Files tab.
     The Files-tab listing never returns these, so they are found by scanning
     those three places for /files/<id> links.
  3. Every assignment description, into <course>/Canvas_Assignments.md.

The ledger (.coursework/ledger.json) is keyed by Canvas file id, so you can
rename, move or delete local files freely: nothing is fetched twice, and an
updated file overwrites your renamed copy instead of landing beside it.
"""

import hashlib
import html
import html.parser
import os
import re
import time
from datetime import datetime

import requests

from .naming import (VIDEO_EXTS, clean_file_name, session_number, unique_path,
                     with_session_prefix)

MIRROR_DEPTH = 3
DOWNLOAD_PAUSE = 0.25
MAX_PAGES_SCANNED = 80

# Canvas folders that are just upload dumps: their files go to the course root
# instead of a stub folder called "unfiled".
ROOT_FOLDERS = {"unfiled", "uploaded media"}

# Where linked (hidden) files land, by where the link was found.
LINKED_DIRS = {"calendar": "Readings", "page": "Readings", "assignment": "Assignments"}

FILE_LINK = re.compile(r"/files/(\d+)")


class Run:
    def __init__(self, ws, canvas, dry_run=False, max_mb=None, quiet=False):
        self.ws = ws
        self.canvas = canvas
        self.dry_run = dry_run
        self.max_mb = ws.config.get("max_mb", 30) if max_mb is None else max_mb
        self.quiet = quiet
        self.changes = []   # (folder, kind, detail): things that changed or would
        self.notes = []     # (folder, kind, detail): worth knowing, not a change
        self.details = []   # (folder, kind, detail): log only, too noisy to print
        self._prefixed = {}

    def say(self, msg):
        if not self.quiet:
            print(msg)

    def change(self, folder, kind, detail):
        self.changes.append((folder, kind, detail))

    def note(self, folder, kind, detail):
        self.notes.append((folder, kind, detail))

    def prefixed(self, folder, items):
        self._prefixed.setdefault(folder, []).extend(items)

    def flush_prefixed(self, folder):
        """One summary line per course; the per-file list goes to the log."""
        items = self._prefixed.pop(folder, [])
        if not items:
            return
        verb = "would get" if self.dry_run else "got"
        self.note(folder, "PREFIXED", f"{len(items)} new file(s) {verb} a session prefix from "
                                      f"the Canvas calendar (full list in the log)")
        for name, where in items:
            self.details.append((folder, "PREFIXED", f'{name}  (from "{where}")'))


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def sync_course(run, cid, cfg):
    folder = cfg["folder"]
    c = run.canvas
    try:
        files = list(c.paginate(f"/courses/{cid}/files"))
    except requests.HTTPError as e:
        code = e.response.status_code
        files = []
        if code in (401, 403, 404):
            run.note(folder, "NO-ACCESS",
                     f"Files tab returned {code}. If you dropped this course, run "
                     f"`coursework drop \"{folder}\"` (your files are kept).")
        else:
            run.change(folder, "ERROR", f"Files tab unreadable (HTTP {code})")
    folders = _folder_paths(c, cid)
    assignments = _safe_list(run, folder, f"/courses/{cid}/assignments",
                             {"order_by": "due_at"}, "assignments")
    linked = find_linked_files(run, cid, cfg, assignments)

    sync_files(run, cid, cfg, files, folders, linked)
    tab_ids = {str(f["id"]) for f in files}
    sync_linked(run, cid, cfg, {k: v for k, v in linked.items() if k not in tab_ids})
    if assignments is not None:
        write_assignments(run, cid, cfg, assignments)
    run.flush_prefixed(folder)


def _safe_list(run, folder, path, params, what):
    try:
        return list(run.canvas.paginate(path, params))
    except requests.HTTPError as e:
        run.note(folder, "NO-ACCESS", f"{what} returned HTTP {e.response.status_code}")
        return None


def _folder_paths(c, cid):
    """folder_id -> relative path, without Canvas's root 'course files'."""
    paths = {}
    try:
        for f in c.paginate(f"/courses/{cid}/folders"):
            parts = [p for p in (f.get("full_name") or "").split("/") if p]
            if parts and parts[0] == "course files":
                parts = parts[1:]
            paths[f["id"]] = "/".join(parts)
    except requests.HTTPError:
        pass
    return paths


# -----------------------------------------------------------------------------
# Linked files: calendar events, pages, assignment descriptions
# -----------------------------------------------------------------------------

def find_linked_files(run, cid, cfg, assignments):
    """file id -> {"source", "where", "session"} for every /files/<id> link.

    Calendar events are where CBS professors keep the session structure, so a
    file linked from "Session 3: …" is a session-3 reading. That is the only
    place a session number is taken from; it is never guessed.
    """
    found = {}

    def add(fid, source, where, session=None):
        cur = found.get(fid)
        if cur is None:
            found[fid] = {"source": source, "where": where, "session": session}
        elif session is not None and (cur["session"] is None or session < cur["session"]):
            # Linked from several sessions: file it under the earliest.
            cur.update(source=source, where=where, session=session)

    c = run.canvas
    try:
        for ev in c.paginate("/calendar_events", {"context_codes[]": f"course_{cid}",
                                                  "type": "event", "all_events": "true"}):
            title = ev.get("title") or ""
            for fid in FILE_LINK.findall(ev.get("description") or ""):
                add(fid, "calendar", title, session_number(title))
    except requests.HTTPError:
        pass

    if cfg.get("scan_pages", True):
        try:
            pages = list(c.paginate(f"/courses/{cid}/pages"))[:MAX_PAGES_SCANNED]
        except requests.HTTPError:
            pages = []
        for p in pages:
            if not p.get("url"):
                continue
            try:
                body = c.json(f"/courses/{cid}/pages/{p['url']}").get("body") or ""
            except requests.HTTPError:
                continue
            for fid in FILE_LINK.findall(body):
                add(fid, "page", p.get("title") or p["url"])

    for a in assignments or []:
        for fid in FILE_LINK.findall(a.get("description") or ""):
            add(fid, "assignment", a.get("name") or "assignment")
    return found


# -----------------------------------------------------------------------------
# Files
# -----------------------------------------------------------------------------

def resolve_dest_dir(cfg, canvas_subpath, filename, flattened):
    """Folder (relative to the course folder) for a file, or None to skip it.

    Optional per-course `routes` in config.json, tried in order:
      {"prefix": "Required Reading", "target": "Readings"}
      {"prefix": "depot", "ext": [".pdf"], "target": "Slides"}
      {"name_match": "Section[ _]?2", "target": null}      # null = never download
      {"prefix": "Sessions", "target": "Sessions", "keep_subpath": true}
    Unrouted files mirror Canvas's folders, capped at 3 levels.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXTS:
        return None  # lecture videos are never downloaded
    for route in cfg.get("routes", []):
        prefix = route.get("prefix", "")
        if prefix and not (canvas_subpath == prefix or canvas_subpath.startswith(prefix + "/")):
            continue
        if route.get("ext") and ext not in route["ext"]:
            continue
        if route.get("name_match") and not re.search(route["name_match"], filename, re.I):
            continue
        target = route["target"]
        if target is None or not route.get("keep_subpath"):
            return target
        rest = canvas_subpath[len(prefix):].strip("/") if prefix else canvas_subpath
        return "/".join(p for p in [target, rest] if p)

    parts = [p for p in canvas_subpath.split("/") if p]
    if parts and parts[0].lower() in ROOT_FOLDERS:
        parts = parts[1:]
    if len(parts) > MIRROR_DEPTH:
        flattened.add(canvas_subpath)
    return "/".join(parts[:MIRROR_DEPTH])


def sync_files(run, cid, cfg, files, folders, linked):
    folder = cfg["folder"]
    counts = dict(new=0, updated=0, unchanged=0, excluded=0, large=0, failed=0)
    flattened, prefixed = set(), []
    for f in files:
        fid = str(f["id"])
        name = clean_file_name(f.get("display_name") or "", f.get("filename"))
        session = (linked.get(fid) or {}).get("session") if cfg.get("session_prefix", True) else None
        target = resolve_dest_dir(cfg, folders.get(f.get("folder_id"), ""), name, flattened)
        if target is not None:
            target = os.path.join(folder, *[p for p in target.split("/") if p])
        final = with_session_prefix(name, session)
        if _sync_one(run, cid, folder, fid, f, final, target, "files", counts) and final != name:
            prefixed.append((final, linked[fid]["where"]))
    if files or counts["failed"]:
        run.say(f"  files: {counts['new']} new, {counts['updated']} updated, "
                f"{counts['unchanged']} unchanged, {counts['excluded']} excluded, "
                f"{counts['large']} over {run.max_mb:g} MB, {counts['failed']} failed")
    run.prefixed(folder, prefixed)
    for path in sorted(flattened):
        run.note(folder, "FLATTENED", f"Canvas folder deeper than {MIRROR_DEPTH} levels: "
                                      f"{path} (add a route to file it properly)")


def sync_linked(run, cid, cfg, linked):
    """Files linked from calendar/pages/assignments but absent from the Files tab."""
    folder = cfg["folder"]
    counts = dict(new=0, updated=0, unchanged=0, excluded=0, large=0, failed=0)
    prefixed = []
    for fid, ref in sorted(linked.items()):
        entry = run.ws.ledger.get(fid)
        if entry and entry.get("status") == "ignored":
            counts["excluded"] += 1
            continue
        resp = run.canvas.get(f"/courses/{cid}/files/{fid}")
        if resp.status_code != 200:
            resp = run.canvas.get(f"/files/{fid}")
        info = resp.json() if resp.status_code == 200 else None
        if not info or not info.get("url"):
            if not entry:
                run.note(folder, "LOCKED", f"file {fid} linked from {ref['source']} "
                                           f"'{ref['where'][:60]}' is not downloadable")
                run.ws.ledger[fid] = {"course_id": cid, "course": folder,
                                      "status": "unavailable", "source": ref["source"]}
                if not run.dry_run:
                    run.ws.save_ledger()
            continue
        name = clean_file_name(info.get("display_name") or "", info.get("filename"))
        # An event without a session number ("Midterm review") gives no prefix.
        session = ref["session"] if cfg.get("session_prefix", True) else None
        target = os.path.join(folder, LINKED_DIRS[ref["source"]])
        final = with_session_prefix(name, session)
        if _sync_one(run, cid, folder, fid, info, final, target,
                     f"linked:{ref['source']}", counts) and final != name:
            prefixed.append((final, ref["where"]))
    run.prefixed(folder, prefixed)
    if any(counts[k] for k in ("new", "updated", "failed", "large")):
        run.say(f"  linked files (not on the Files tab): {counts['new']} new, "
                f"{counts['updated']} updated, {counts['large']} over size limit, "
                f"{counts['failed']} failed")


def _sync_one(run, cid, folder, fid, f, name, target_dir, source, counts):
    """Shared download logic for Files-tab and linked files.
    Returns True only when a new file was (or, in a dry run, would be) added."""
    ws, ledger = run.ws, run.ws.ledger
    entry = ledger.get(fid)
    unchanged = (entry is not None and entry.get("size") == f.get("size")
                 and entry.get("updated_at") == f.get("updated_at"))

    if entry and entry.get("status") == "ignored":
        # Excluded by you (a duplicate, an old version): a re-upload on Canvas
        # must not bring it back.
        counts["excluded"] += 1
        return
    if unchanged and entry.get("status") == "downloaded":
        counts["unchanged"] += 1
        return

    record = {"course_id": cid, "course": folder, "name": name, "size": f.get("size"),
              "updated_at": f.get("updated_at"), "source": source}
    if target_dir is None:
        record.update(status="ignored", ignored_reason="excluded by a route")
        ledger[fid] = record
        counts["excluded"] += 1
        if not run.dry_run:
            ws.save_ledger()
        return

    size = f.get("size") or 0
    if run.max_mb and size > run.max_mb * 1024 * 1024:
        run.note(folder, "TOO-LARGE", f"{name} ({size / 1048576:.0f} MB) — "
                                      f"`coursework sync \"{folder}\" --max-mb 0` to get it")
        counts["large"] += 1
        return

    dest = ws.abspath(os.path.join(target_dir, name))
    was_known = bool(entry and entry.get("status") == "downloaded")
    kept = ws.abspath(entry["saved_to"]) if was_known and entry.get("saved_to") else None
    if kept and os.path.exists(kept):
        dest = kept  # overwrite your renamed/refiled copy in place
    elif os.path.exists(dest) and os.path.getsize(dest) == size:
        # Already there (an existing folder, or filed by hand): adopt it.
        record.update(status="downloaded", saved_to=ws.relpath(dest))
        ledger[fid] = record
        counts["unchanged"] += 1
        if not run.dry_run:
            ws.save_ledger()
        return

    rel = ws.relpath(dest)
    if run.dry_run:
        run.change(folder, "WOULD-UPDATE" if was_known else "WOULD-ADD", rel)
        counts["updated" if was_known else "new"] += 1
        return not was_known

    if dest != kept:
        dest = unique_path(dest)
        rel = ws.relpath(dest)
    try:
        if not f.get("url"):
            raise RuntimeError("no download URL (locked on Canvas)")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        run.canvas.download(f["url"], dest + ".part")
        os.replace(dest + ".part", dest)
    except Exception as e:
        run.change(folder, "FAILED", f"{name}: {e}")
        counts["failed"] += 1
        return
    run.say(f"  {'updated' if was_known else 'saved  '} {rel}")
    run.change(folder, "UPDATED" if was_known else "NEW", rel)
    record.update(status="downloaded", saved_to=rel)
    ledger[fid] = record
    ws.save_ledger()
    counts["updated" if was_known else "new"] += 1
    time.sleep(DOWNLOAD_PAUSE)
    return not was_known


# -----------------------------------------------------------------------------
# Assignment descriptions
# -----------------------------------------------------------------------------

class _HTMLToText(html.parser.HTMLParser):
    """Minimal HTML -> Markdown-ish text, stdlib only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self._href, self._skip = [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "div", "br", "tr"):
            self.out.append("\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n### ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self.out.append("[")
        elif tag in ("td", "th"):
            self.out.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a":
            self.out.append(f"]({self._href})" if self._href else "]")
            self._href = None
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)

    def text(self):
        txt = "".join(self.out).replace("\xa0", " ")
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r" *\n *", "\n", txt)
        return re.sub(r"\n{3,}", "\n\n", txt).strip()


def html_to_text(raw):
    if not raw:
        return ""
    p = _HTMLToText()
    try:
        p.feed(raw)
        p.close()
    except Exception:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
    return p.text()


def write_assignments(run, cid, cfg, assignments):
    """Deliberately never asks for submissions: no scores, nobody's work."""
    folder = cfg["folder"]
    lines = [f"# {cfg.get('canvas_name', folder)} — assignment descriptions", "",
             "Written by `coursework sync` from Canvas and rewritten on every sync, "
             "so don't edit it by hand. Descriptions only: no grades, no submissions.", ""]
    with_body = 0
    for a in sorted(assignments, key=lambda x: (x.get("due_at") is None, x.get("due_at") or "")):
        due = (a.get("due_at") or "")[:10] or "no due date"
        meta = [f"**Due:** {due}"]
        if a.get("points_possible") is not None:
            meta.append(f"**Points:** {a['points_possible']:g}")
        body = html_to_text(a.get("description"))
        with_body += bool(body)
        lines += [f"## {(a.get('name') or 'Untitled').strip()}", " · ".join(meta), "",
                  body or "_No description posted on Canvas._", ""]

    content = "\n".join(lines).rstrip() + "\n"
    dest = run.ws.abspath(os.path.join(folder, "Canvas_Assignments.md"))
    key = f"assignments:{cid}"
    prev = (run.ws.ledger.get(key) or {}).get("hash")
    now = hashlib.sha256(content.encode()).hexdigest()[:16]
    if prev == now and os.path.exists(dest):
        return
    if run.dry_run:
        # Between two runs this usually means the professor edited a description.
        run.change(folder, "WOULD-WRITE", f"Canvas_Assignments.md ({len(assignments)} assignments)")
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as fh:
        fh.write(content)
    run.ws.ledger[key] = {"course_id": cid, "course": folder, "hash": now,
                          "count": len(assignments), "status": "written",
                          "saved_to": run.ws.relpath(dest)}
    run.ws.save_ledger()
    run.say(f"  assignments: wrote {len(assignments)} ({with_body} with descriptions)")
    run.change(folder, "NEW" if prev is None else "UPDATED",
               f"Canvas_Assignments.md ({len(assignments)} assignments)")


# -----------------------------------------------------------------------------
# Log, verify, relink
# -----------------------------------------------------------------------------

def write_change_log(run):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(run.ws.change_log, "a") as fh:
        fh.write(f"\n===== {stamp}{'  (dry run)' if run.dry_run else ''}\n")
        if not run.changes and not run.notes:
            fh.write("  no changes\n")
        for folder, kind, detail in run.changes + run.notes + run.details:
            fh.write(f"  {kind:<12} {folder:<34} {detail}\n")


def missing_on_disk(ws):
    """Ledger entries that say 'downloaded' but whose file is gone."""
    return [(fid, e) for fid, e in ws.ledger.items()
            if e.get("status") in ("downloaded", "written") and e.get("saved_to")
            and not os.path.exists(ws.abspath(e["saved_to"]))]


def relink(ws, missing):
    """Find files you moved or renamed and point the ledger at them again.

    A match is a file of exactly the same size inside the same course folder,
    whose name contains the original name (so "S04 Case.pdf" matches "Case.pdf"),
    and that no other ledger entry already claims. Ambiguous ones are left alone.
    """
    claimed = {e.get("saved_to") for e in ws.ledger.values()}
    fixed, unresolved = [], []
    for fid, e in missing:
        course_dir = ws.abspath(e.get("course", ""))
        stem = os.path.splitext(e.get("name") or os.path.basename(e["saved_to"]))[0].lower()
        hits = []
        for dirpath, _dirs, names in os.walk(course_dir):
            for n in names:
                p = os.path.join(dirpath, n)
                if (stem and stem in n.lower() and os.path.getsize(p) == e.get("size")
                        and ws.relpath(p) not in claimed):
                    hits.append(p)
        if len(hits) == 1:
            e["saved_to"] = ws.relpath(hits[0])
            claimed.add(e["saved_to"])
            fixed.append(e["saved_to"])
        else:
            unresolved.append((fid, e))
    if fixed:
        ws.save_ledger()
    return fixed, unresolved
