"""Canvas sync: files, files linked from elsewhere, and assignment descriptions.

Per course, one sync pulls:
  1. Everything on the Files tab, mirroring the professor's folders (3 levels max).
  2. "Hidden" files: files a professor links from the Syllabus page, a calendar
     event, a Canvas page, a module, an announcement or an assignment description
     without listing them on the Files tab. The Files-tab listing never returns
     these, so they are found by scanning those places for /files/<id> links.
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
LINKED_DIRS = {"syllabus": "", "calendar": "Readings", "page": "Readings", "module": "Readings",
               "announcement": "Announcements", "assignment": "Assignments"}

# Images linked from a page are decoration (headshots, banners), not course material.
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".heic"}

# A Canvas file link, absolute or relative. Not just "/files/<n>": plenty of web
# addresses contain that (kff.org/wp-content/…/files/2024/…).
FILE_LINK = re.compile(r"(?:/courses/\d+/files/|/api/v1/files/|[\"']/files/)(\d+)")
ANCHOR = re.compile(r'<a\b([^>]*)>(.*?)</a>', re.I | re.S)
HREF = re.compile(r'href="([^"]+)"', re.I)
TITLE_ATTR = re.compile(r'title="([^"]+)"', re.I)
# Links that are never readings: people, meetings, forms.
NOT_READINGS = re.compile(r"linkedin\.com|zoom\.us|mailto:|calendly|forms\.gle|docs\.google\.com/forms"
                          r"|polleverywhere|/courses/\d+/(?:assignments|pages|modules|discussion_topics|quizzes)"
                          r"|/files/\d+", re.I)


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
    linked, links = find_linked_files(run, cid, cfg, assignments)

    sync_files(run, cid, cfg, files, folders, linked)
    tab_ids = {str(f["id"]) for f in files}
    twins = {(clean_file_name(f.get("display_name") or "", f.get("filename")).lower(), f.get("size"))
             for f in files}
    sync_linked(run, cid, cfg, {k: v for k, v in linked.items() if k not in tab_ids}, twins)
    if assignments is not None:
        write_assignments(run, cid, cfg, assignments)
    write_links(run, cid, cfg, links)
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
    found, links = {}, {}

    def add_link(url, title, kind, source, where, session=None):
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title or ""))).strip()
        if not title or NOT_READINGS.search(url or ""):
            return
        cur = links.get(title.lower())
        if cur is None or (session is not None and (cur["session"] is None or session < cur["session"])):
            links[title.lower()] = {"title": title, "url": url, "kind": kind, "source": source,
                                    "where": where, "session": session}

    def scan_links(raw, source, where, session=None, tools_only=False):
        """Readings that are links, not files: coursepack/Canvas-tool links always,
        plain web links only where a professor lists readings (calendar, modules)."""
        for attrs, label in ANCHOR.findall(raw or ""):
            m = HREF.search(attrs)
            url = html.unescape(m.group(1)) if m else ""
            t = TITLE_ATTR.search(attrs)
            title = label if re.sub(r"<[^>]+>", "", label).strip() else (t.group(1) if t else "")
            kind = link_kind(url)
            if kind == "web" and tools_only:
                continue
            if kind:
                add_link(url, title, kind, source, where, session)

    def add(fid, source, where, session=None):
        cur = found.get(fid)
        if cur is None:
            found[fid] = {"source": source, "where": where, "session": session}
        elif session is not None and (cur["session"] is None or session < cur["session"]):
            # Linked from several sessions: file it under the earliest.
            cur.update(source=source, where=where, session=session)

    c = run.canvas
    try:
        # Many professors leave the Syllabus page as boilerplate, but some link
        # the real syllabus PDF there and nowhere else.
        body = c.json(f"/courses/{cid}", {"include[]": "syllabus_body"}).get("syllabus_body")
        for fid in FILE_LINK.findall(body or ""):
            add(fid, "syllabus", "Syllabus page")
        scan_links(body, "syllabus", "Syllabus page", tools_only=True)
    except requests.HTTPError:
        pass
    try:
        for ev in c.paginate("/calendar_events", {"context_codes[]": f"course_{cid}",
                                                  "type": "event", "all_events": "true"}):
            title = ev.get("title") or ""
            for fid in FILE_LINK.findall(ev.get("description") or ""):
                add(fid, "calendar", title, session_number(title))
            scan_links(ev.get("description"), "calendar", title, session_number(title))
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
            scan_links(body, "page", p.get("title") or p["url"], tools_only=True)

    try:
        for m in c.paginate(f"/courses/{cid}/modules", {"include[]": "items"}):
            for it in m.get("items") or []:
                n = session_number(m.get("name"))
                if it.get("type") == "File" and it.get("content_id"):
                    # Only the module's name may give a session ("Session 3"): file
                    # titles can carry last year's numbering.
                    add(str(it["content_id"]), "module", m.get("name") or "module", n)
                elif it.get("type") in ("ExternalTool", "ExternalUrl"):
                    url = it.get("external_url") or it.get("url") or ""
                    kind = "Canvas tool" if it["type"] == "ExternalTool" else "web"
                    add_link(url, it.get("title"), link_kind(url) or kind, "module",
                             m.get("name") or "module", n)
    except requests.HTTPError:
        pass

    try:
        for d in c.paginate("/announcements", {"context_codes[]": f"course_{cid}",
                                              "start_date": "2000-01-01"}):
            for fid in FILE_LINK.findall(d.get("message") or ""):
                add(fid, "announcement", d.get("title") or "announcement")
            for att in d.get("attachments") or []:
                if att.get("id"):
                    add(str(att["id"]), "announcement", d.get("title") or "announcement")
    except requests.HTTPError:
        pass

    for a in assignments or []:
        for fid in FILE_LINK.findall(a.get("description") or ""):
            add(fid, "assignment", a.get("name") or "assignment")
        scan_links(a.get("description"), "assignment", a.get("name") or "assignment",
                   tools_only=True)
    return found, list(links.values())


def link_kind(url):
    """'Harvard coursepack', 'Canvas tool', 'web', or None for non-reading links."""
    u = (url or "").lower()
    if "hbsp.harvard.edu" in u or "hbr.org/store" in u:
        return "Harvard coursepack"
    if "/external_tools/" in u:
        return "Canvas tool"
    if u.startswith("http") and "courseworks" not in u and "instructure" not in u:
        return "web"
    return None


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
        if target == "" and session is not None and (linked.get(fid) or {}).get("source") == "calendar":
            # Loose in the course root (an "unfiled" dump) but assigned to a session
            # on the calendar: it's a reading, so file it with the others.
            target = "Readings"
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


def sync_linked(run, cid, cfg, linked, twins=frozenset()):
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
        skip = ("decorative image" if os.path.splitext(name)[1].lower() in IMAGE_EXTS else
                "duplicate of a Files-tab file" if (name.lower(), info.get("size")) in twins else None)
        if skip:
            # A second upload of a Files-tab file (same name and size) would be a
            # second copy of the same document: keep only one.
            run.ws.ledger[fid] = {"course_id": cid, "course": folder, "name": name,
                                  "status": "ignored", "ignored_reason": skip,
                                  "source": ref["source"]}
            if not run.dry_run:
                run.ws.save_ledger()
            continue
        # An event without a session number ("Midterm review") gives no prefix.
        session = ref["session"] if cfg.get("session_prefix", True) else None
        target = os.path.join(folder, LINKED_DIRS[ref["source"]]) if LINKED_DIRS[ref["source"]] else folder
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


def write_links(run, cid, cfg, links):
    """<course>/Canvas_Links.md: readings that are links, not files, so they can't
    be downloaded (Harvard coursepack cases, other Canvas tools, web articles).
    ✓ marks one you've since saved yourself (a file in the course folder with
    that title in its name)."""
    folder = cfg["folder"]
    dest = run.ws.abspath(os.path.join(folder, "Canvas_Links.md"))
    key = f"links:{cid}"
    if not links:
        return
    course_dir = run.ws.abspath(folder)
    files_here = [(n, os.path.join(d, n)) for d, _s, fs in os.walk(course_dir) for n in fs
                  if not n.startswith("Canvas_")]

    def have(title):
        """The file you saved for this link, if any: its name must contain the whole
        title, and short titles ("Google Glass") also need to be in Readings/ so a
        lecture deck with the same words doesn't count."""
        t = _norm(title)
        for n, path in files_here:
            if t and t in _norm(n) and (len(t) >= 15 or "/Readings/" in path):
                return os.path.relpath(path, course_dir)
        return None

    order = sorted(links, key=lambda l: (l["session"] is None, l["session"] or 0, l["title"].lower()))
    how = {"Harvard coursepack": "buy/download from the Harvard link on Canvas",
           "Canvas tool": "open from Canvas (it isn't a file)",
           "web": "open in a browser"}
    body, group = [], object()
    for l in order:
        g = f"S{l['session']:02d}" if l["session"] else "No session given"
        if g != group:
            body += ["", f"## {g}"]
            group = g
        got = have(l["title"])
        mark = f"✓ (you have `{got}`)" if got else "☐"
        body.append(f"- {mark} **{l['title']}** · {l['kind']}: {how[l['kind']]} "
                    f"(from {l['source']} \"{l['where'][:60]}\") · [link]({l['url']})")
    missing = [l for l in links if not have(l["title"])]
    paid = sum(l["kind"] == "Harvard coursepack" for l in missing)
    web = sum(l["kind"] == "web" for l in missing)
    head = [f"# {folder.rsplit('/', 1)[-1]}: readings that are links, not files", "",
            "Written by `coursework sync` and rewritten each time. These can't be downloaded "
            "automatically. ✓ = a file with that title is already in this course folder "
            f"(save yours into Readings/ as `S03 <title>.pdf` and it gets ticked).", ""]
    content = "\n".join(head + body).rstrip() + "\n"
    # Compare only the links themselves: not the title (renaming the folder
    # changes it) and not the ✓ marks (they change as you save files).
    marks_free = re.sub(r"- (?:✓ \(you have `[^`]*`\)|☐) ", "- ", "\n".join(body))
    now = hashlib.sha256(marks_free.encode()).hexdigest()[:16]
    prev = (run.ws.ledger.get(key) or {}).get("hash")
    if missing:
        parts = [f"{paid} Harvard coursepack" if paid else "",
                 f"{web} web article(s)" if web else "",
                 f"{len(missing) - paid - web} other Canvas link(s)" if len(missing) - paid - web else ""]
        run.note(folder, "LINKS", f"{len(missing)} reading(s) can't be downloaded, they're links: "
                                  + ", ".join(p for p in parts if p) + ". See Canvas_Links.md")
    if run.dry_run:
        if prev != now:
            run.change(folder, "WOULD-WRITE", f"Canvas_Links.md ({len(links)} links)")
        return
    old = open(dest).read() if os.path.exists(dest) else None
    if old != content:
        with open(dest, "w") as fh:
            fh.write(content)
    if prev != now:
        run.change(folder, "NEW" if prev is None else "UPDATED", f"Canvas_Links.md ({len(links)} links)")
    run.ws.ledger[key] = {"course_id": cid, "course": folder, "hash": now, "status": "written",
                          "saved_to": run.ws.relpath(dest)}
    run.ws.save_ledger()


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


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
