"""Echo360 lecture transcripts: an optional add-on.

Needs Playwright (`pip install -r requirements-echo360.txt && playwright install
chromium`) and a real browser login with your UNI + Duo, so it can't run
unattended the way `coursework sync` can. Kept separate on purpose: an expired
Echo360 login never blocks the file sync.

  coursework echo360 status            which courses have a class you don't have yet
                                       (Canvas calendar only, no login needed)
  coursework echo360 login             sign in once (UNI + Duo), then press Enter
  coursework echo360 setup <course>    find the course's Echo360 section (once per course)
  coursework echo360 pull [courses]    download new transcripts

Transcripts land in <course>/Transcripts/ as "S07 Transcript.txt": plain text,
no timestamps, ready to hand to Claude.

Why a browser at all: Columbia only exposes Echo360 inside a Canvas iframe, and
Chrome partitions that iframe's cookie, so every request is made from inside
the iframe's own JavaScript (frame.evaluate). Canvas's login cookies are
session-only, so `login` saves them to a file and every run re-injects them.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from .naming import sanitize, session_number
from .workspace import USER_DIR, Workspace, load_json, save_json, write_secret

# A class counts once it ended this long ago (transcripts take a while to appear),
# and a session still missing a day after a pull is treated as never recorded.
GRACE = timedelta(hours=2)
GIVE_UP = timedelta(hours=24)

ECHO = "https://echo360.org"
TRANSCRIPT = "/api/ui/echoplayer/lessons/{lesson}/medias/{media}/transcript-file?format=vtt"
COOKIES = os.environ.get("COURSEWORK_ECHO360_COOKIES",
                         os.path.join(USER_DIR, "echo360_cookies.json"))
# A ~200 MB browser profile: kept in the cache folder, never in your Drive.
if sys.platform == "win32":
    _CACHE = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/AppData/Local")
else:
    _CACHE = os.path.expanduser("~/Library/Caches" if sys.platform == "darwin" else "~/.cache")
PROFILE = os.path.join(_CACHE, "coursework", "echo360_profile")


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("The Echo360 add-on needs Playwright. One time:\n"
                 "  pip install -r requirements-echo360.txt\n  playwright install chromium")
    return sync_playwright


def lti_url(ws, cid):
    return f"{ws.config['canvas_url']}/courses/{cid}/external_tools/{ws.config['echo360_tool_id']}"


# -- browser plumbing ----------------------------------------------------------

class Browser:
    """A headless browser carrying your saved Canvas login."""

    def __init__(self, headless=True):
        self.headless = headless

    def __enter__(self):
        if not os.path.exists(COOKIES):
            sys.exit("No Echo360 login saved yet. Run `coursework echo360 login`.")
        self._mgr = _playwright()()
        self._pw = self._mgr.__enter__()
        os.makedirs(PROFILE, exist_ok=True)
        self.ctx = self._pw.chromium.launch_persistent_context(PROFILE, headless=self.headless)
        with open(COOKIES, encoding="utf-8") as fh:
            self.ctx.add_cookies(json.load(fh))
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def __exit__(self, *exc):
        self.ctx.close()
        self._mgr.__exit__(*exc)

    def open_course(self, url, timeout_ms=30000):
        """Load the course's Echo360 tool; return its iframe, or None.
        Exits with a clear message if Canvas bounced us to the login page."""
        self.page.goto(url)
        if "/login" in self.page.url or "cas." in self.page.url:
            sys.exit("Your Echo360 login has expired (Canvas asked to sign in again).\n"
                     "Run `coursework echo360 login`, then try again.")
        deadline = datetime.now().timestamp() + timeout_ms / 1000
        while datetime.now().timestamp() < deadline:
            for fr in self.page.frames:
                if "echo360" in fr.url:
                    return fr
            self.page.wait_for_timeout(500)
        return None


def fetch(frame, url):
    """GET from inside the Echo360 iframe. Returns (status, text)."""
    r = frame.evaluate("""async (url) => {
        try { const r = await fetch(url, {credentials: 'include'});
              return {status: r.status, text: await r.text()}; }
        catch (e) { return {status: 0, text: ''}; } }""", url)
    return r["status"], r["text"]


def fetch_json(frame, path):
    status, text = fetch(frame, ECHO + path)
    if status != 200:
        raise RuntimeError(f"Echo360 {path} -> HTTP {status}")
    return json.loads(text)


def lessons(syllabus):
    """(group, lesson name, lesson id, media id) for every lesson with a recording.

    The syllabus mixes grouped entries ({"groupInfo", "lessons": [...]}, e.g.
    "Section 001") with standalone ones ({"lesson": ...}, e.g. a combined session).
    """
    def from_wrap(wrap, group):
        les = wrap.get("lesson") or {}
        meta = les.get("lesson") or {}
        for m in les.get("medias") or []:
            if m.get("id") and meta.get("id"):
                yield group, meta.get("name") or meta.get("displayName") or "lesson", meta["id"], m["id"]

    for g in syllabus.get("data", []):
        if "lesson" in g:
            yield from from_wrap(g, g.get("type") or "Ungrouped")
            continue
        group = (g.get("groupInfo") or {}).get("name") or g.get("type") or ""
        for wrap in g.get("lessons", []):
            yield from from_wrap(wrap, group)


def vtt_to_text(vtt):
    """WebVTT -> one paragraph of plain text.

    Drops timestamps, cue numbers, speaker tags and Echo360's `NOTE CONF {...}`
    confidence blocks (which run to the next blank line and would otherwise
    roughly double the token count)."""
    out, last, in_note = [], None, False
    for ln in vtt.splitlines():
        s = ln.strip()
        if not s:
            in_note = False
            continue
        if in_note or s == "NOTE" or s.startswith("NOTE "):
            in_note = True
            continue
        if s == "WEBVTT" or s.isdigit() or "-->" in s:
            continue
        s = re.sub(r"<[^>]+>", "", s)
        if s and s != last:
            out.append(s)
            last = s
    return " ".join(out) + "\n"


# -- commands --------------------------------------------------------------------

def cmd_login(ws, args):
    sync_playwright = _playwright()
    os.makedirs(PROFILE, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PROFILE, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ws.config["canvas_url"])
        print("\nA browser opened at Canvas. Log in with your UNI + Duo.\n"
              ">>> Then come back HERE and press Enter. The login is not saved until you do.")
        input("Press Enter once Canvas has loaded… ")
        write_secret(COOKIES, json.dumps(ctx.cookies()))
        ctx.close()
    print(f"Login saved ({COOKIES}). It lasts a few days; run this again when pull says so.")


def cmd_setup(ws, args):
    if not args.courses:
        sys.exit("Which course? e.g. `coursework echo360 setup \"Product Management\"`")
    with Browser() as b:
        for name in args.courses:
            cid = ws.resolve_course(name)
            cfg = ws.config["courses"][cid]
            frame = b.open_course(lti_url(ws, cid))
            m = re.search(r"/section/([0-9a-f-]{36})", frame.url) if frame else None
            if not m:
                print(f"{cfg['folder']}: no Echo360 recordings (some courses only use Zoom).")
                continue
            section = m.group(1)
            groups = sorted({g for g, *_ in lessons(fetch_json(frame, f"/section/{section}/syllabus"))})
            group = args.group
            if not group and len(groups) == 1:
                group = groups[0]
            if not group and groups:
                print(f"{cfg['folder']}: recordings are split by section: {', '.join(groups)}\n"
                      f"  Re-run with yours, e.g. `coursework echo360 setup \"{cfg['folder']}\" "
                      f"--group 001`")
                continue
            cfg["echo360"] = {"section": section, "group": group or ""}
            ws.save_config()
            print(f"{cfg['folder']}: set up (section {section[:8]}…, group {group or 'all'}).")


def last_class(canvas, cid, now):
    """(session number, end time) of the latest numbered class that ended GRACE ago."""
    best = None
    for ev in canvas.paginate("/calendar_events", {"context_codes[]": f"course_{cid}",
                                                   "type": "event", "all_events": "true"}):
        n = session_number(ev.get("title"))
        end = ev.get("end_at") or ev.get("start_at")
        if not n or not end:
            continue
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
        if end + GRACE <= now and (best is None or n > best[0]):
            best = (n, end)
    return best


def due_courses(ws, names):
    """Which courses could have a new transcript, decided from Canvas alone (no login).

    A course is due when its latest finished class is newer than its newest
    transcript, unless a pull already ran a day or more after that class and
    found nothing (the professor didn't record it)."""
    from .cli import canvas_for
    canvas = canvas_for(ws)
    ledger = load_json(ws.echo_ledger_file, {})
    now = datetime.now(timezone.utc)
    cids = [ws.resolve_course(n) for n in names] if names else \
        [cid for cid, c in ws.config["courses"].items() if c.get("echo360") and not c.get("skip")]
    report = []
    for cid in cids:
        cfg = ws.config["courses"][cid]
        if not cfg.get("echo360"):
            report.append((cid, "setup", None, None))
            continue
        have = max([e.get("session") or 0 for e in ledger.values()
                    if e.get("course_id") == cid] or [0])
        held = last_class(canvas, cid, now)
        checked = ledger.get(f"checked:{cid}") or {}
        if held is None:
            state = "unknown"
        elif held[0] <= have:
            state = "ok"
        elif (checked.get("session", 0) >= held[0]
              and checked.get("at", "") >= (held[1] + GIVE_UP).isoformat()):
            state = "not-recorded"
        else:
            state = "due"
        report.append((cid, state, held[0] if held else None, have))
    return report


def print_report(ws, report):
    for cid, state, held, have in report:
        folder = ws.config["courses"][cid]["folder"]
        msg = {"due": f"session {held} has happened; you have up to {have or 'none'}",
               "ok": f"up to date (session {have})",
               "not-recorded": f"session {held} seems not to have been recorded; skipping it",
               "unknown": "calendar has no numbered sessions; will check Echo360",
               "setup": "not set up for Echo360 (`coursework echo360 setup`)"}[state]
        print(f"  {'PULL' if state in ('due', 'unknown') else '-':<5} {folder}: {msg}")


def cmd_status(ws, args):
    """Tells you whether a login is worth it, before you do UNI + Duo."""
    report = due_courses(ws, args.courses)
    print_report(ws, report)
    due = [r for r in report if r[1] in ("due", "unknown")]
    print("\nNothing new to pull: no need to log in." if not due else
          "\n`coursework echo360 pull` will fetch these.")


def cmd_pull(ws, args):
    """Checks the Canvas calendar first and only opens a browser (and so only
    risks a login prompt) when some course can actually have a new transcript."""
    ledger = load_json(ws.echo_ledger_file, {})
    report = due_courses(ws, args.courses)
    if not any(r[1] != "setup" for r in report):
        sys.exit("No courses set up for Echo360 yet: `coursework echo360 setup <course>`.")
    targets = [cid for cid, state, *_ in report
               if state in ("due", "unknown") or (args.force and state != "setup")]
    if not targets:
        print_report(ws, report)
        print("\nNo class has finished since your last transcripts, so there's nothing to "
              "pull (and no login needed). `--force` checks Echo360 anyway.")
        return
    held_by = {cid: held for cid, _s, held, _h in report}
    with Browser() as b:
        for i, cid in enumerate(targets):
            cfg = ws.config["courses"][cid]
            e3 = cfg["echo360"]
            frame = b.open_course(lti_url(ws, cid))
            try:
                syl = fetch_json(frame, f"/section/{e3['section']}/syllabus") if frame else None
            except RuntimeError:
                syl = None
            if syl is None:
                if i == 0:  # the first course is the canary for an expired login
                    sys.exit("Echo360 didn't load: your login has probably expired.\n"
                             "Run `coursework echo360 login`, then pull again.")
                print(f"{cfg['folder']}: Echo360 didn't load; skipped")
                continue
            got = _pull_course(ws, cid, cfg, frame, syl, ledger, args.keep_vtt)
            ledger[f"checked:{cid}"] = {"session": held_by.get(cid) or 0,
                                        "at": datetime.now(timezone.utc).isoformat()}
            save_json(ws.echo_ledger_file, ledger)
            print(f"{cfg['folder']}: {got} new transcript(s)")
    print("\nNext: ask Claude to update the Master Takeaways for these courses.")


def _pull_course(ws, cid, cfg, frame, syl, ledger, keep_vtt):
    group = (cfg["echo360"].get("group") or "").lower()
    picked = [l for l in lessons(syl) if not group or group in l[0].lower() or group in l[1].lower()]
    dest = ws.abspath(os.path.join(cfg["folder"], "Transcripts"))
    parts = {}
    got = 0
    for _g, name, lesson_id, media_id in picked:
        parts[lesson_id] = parts.get(lesson_id, 0) + 1
        if (ledger.get(media_id) or {}).get("status") == "downloaded":
            continue
        status, vtt = fetch(frame, ECHO + TRANSCRIPT.format(lesson=lesson_id, media=media_id))
        if status != 200 or not vtt.strip():
            continue  # not transcribed yet; tried again next pull
        n = session_number(name)
        base = f"S{n:02d} Transcript" if n else sanitize(name)
        if parts[lesson_id] > 1:
            base += f" (part {parts[lesson_id]})"
        os.makedirs(dest, exist_ok=True)
        txt = os.path.join(dest, base + ".txt")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(vtt_to_text(vtt))
        if keep_vtt:
            with open(os.path.join(dest, base + ".vtt"), "w", encoding="utf-8") as fh:
                fh.write(vtt)
        ledger[media_id] = {"course_id": cid, "name": name, "session": n,
                            "status": "downloaded", "saved_to": ws.relpath(txt)}
        save_json(ws.echo_ledger_file, ledger)
        print(f"  saved  {ws.relpath(txt)}  ({len(open(txt, encoding='utf-8').read().split()):,} words)")
        got += 1
    return got


def main(args):
    ws = Workspace.find(args.root)
    {"login": cmd_login, "setup": cmd_setup, "status": cmd_status, "pull": cmd_pull}[args.action](ws, args)
