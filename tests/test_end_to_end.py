"""End-to-end test of `coursework` against a fake Canvas: no network, no token.

Runs the whole flow a new user goes through (init with term grouping, preview,
sync, verify, a second sync, next, rename, ignore, the Echo360 gate) on every OS
in CI. The fake course contains every awkward case met on real CBS courses:
hidden files on the Syllabus page and in assignment descriptions, a case dumped
in "unfiled" but assigned to a session, Harvard coursepack links, decorative
images, unicode and Windows-reserved file names, a deep folder tree, an
oversized deck and a lecture video.

    python -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

# Isolate HOME *before* importing the package: it reads ~/.config at import time.
HOME = tempfile.mkdtemp(prefix="cw-home-")
os.environ["HOME"] = os.environ["USERPROFILE"] = HOME
os.environ["CANVAS_TOKEN"] = "1234~" + "x" * 40
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from coursework import cli, echo360, sync  # noqa: E402

sync.DOWNLOAD_PAUSE = 0
NOW = datetime.now(timezone.utc)
MB = 1024 * 1024


def iso(delta_days, hour=14):
    return (NOW + timedelta(days=delta_days)).replace(hour=hour, minute=20, second=0,
                                                       microsecond=0).isoformat().replace("+00:00", "Z")


def a(href, text, title=None):
    t = f' title="{title}"' if title else ""
    return f'<a href="{href}"{t}>{text}</a>'


C = "https://courseworks2.columbia.edu"
LONG = "An Extremely Long Reading Title That Professors Love " * 3

FILES = {
    "101": [
        {"id": 1, "display_name": "Syllabus Fall 2026.pdf", "size": 100, "folder_id": 11},
        {"id": 2, "display_name": "Café – “Notes” ✓.pdf", "size": 120, "folder_id": 10},
        {"id": 3, "display_name": "Pitney Case.pdf", "size": 130, "folder_id": 12},
        {"id": 4, "display_name": "Big deck.pdf", "size": 50 * MB, "folder_id": 10},
        {"id": 5, "display_name": "Lecture 1.mp4", "size": 140, "folder_id": 10},
        {"id": 6, "display_name": LONG.strip() + ".pdf", "size": 150, "folder_id": 13},
        {"id": 7, "display_name": "CON.pdf", "size": 160, "folder_id": 10},
        {"id": 8, "display_name": "Session01 deck", "filename": "Session01+deck.pdf",
         "size": 170, "folder_id": 10},
    ],
    "102": [{"id": 20, "display_name": "Negotiation prep.docx", "size": 200, "folder_id": 30}],
}
FOLDERS = {
    "101": [{"id": 10, "full_name": "course files"}, {"id": 11, "full_name": "course files/Syllabus"},
            {"id": 12, "full_name": "course files/unfiled"},
            {"id": 13, "full_name": "course files/Week Folders/Week 1/Optional/Extra Deep"}],
    "102": [{"id": 30, "full_name": "course files"}],
}
HIDDEN = {  # linked from somewhere, not on the Files tab
    "50": {"id": 50, "display_name": "Real Syllabus.pdf", "size": 210},
    "51": {"id": 51, "display_name": "prof-headshot.jpg", "size": 220},
    "52": {"id": 52, "display_name": "Platforms Reading.pdf", "size": 230},
    "53": {"id": 53, "display_name": "Answer Key PS1.pdf", "size": 240},
}
EVENTS = {
    "101": [
        {"title": "Session 1: Intro", "start_at": iso(-30), "end_at": iso(-30, 16), "description": ""},
        {"title": "Session 2: Pricing", "start_at": iso(-25), "end_at": iso(-25, 16),
         "description": "<p>Read: " + a(f"{C}/courses/101/files/3?wrap=1", "Pitney Case") + " and "
                        + a(f"{C}/courses/101/external_tools/retrieve?display=borderless&x=1",
                            "Pitney Bowes HBS", "Pitney Bowes HBS") + "</p>"},
        {"title": "Session 3: Platforms (MRKTB8636_001_2026_3 - Product Management)",
         "start_at": iso(3), "end_at": iso(3, 15), "description": ""},
        {"title": "Session 3: Platforms", "start_at": iso(3), "end_at": iso(3, 18),
         "description": "<p>Required: " + a(f"{C}/courses/101/files/52", "Platforms Reading")
                        + ", plus " + a("https://hbr.org/2020/01/platforms", "Platform article")
                        + ". Speaker: " + a("https://www.linkedin.com/in/someone", "Guest") + "</p>"},
        {"title": "Final exam window closes", "start_at": iso(5), "end_at": iso(5), "description": ""},
    ],
    "102": [{"title": f"Negotiations Session {i}: Topic", "start_at": iso(-40 + 13 * i),
             "end_at": iso(-40 + 13 * i, 17), "description": ""} for i in range(8)],
}
MODULES = {"101": [{"name": "Harvard Case Readings", "items": [
    {"type": "ExternalTool", "title": "Google Glass",
     "url": "https://services.hbsp.harvard.edu/lti/links/content-launch"}]}]}
ASSIGNMENTS = {"101": [{"name": "Case write-up", "due_at": iso(2), "points_possible": 50,
                        "description": "<p>Use " + a(f"{C}/courses/101/files/53", "the answer key") + "</p>"}]}
SYLLABUS = {"101": "<p>" + a(f"{C}/courses/101/files/50", "Syllabus PDF")
            + a(f"{C}/courses/101/files/51", "<img src='x'>") + "</p>"}
COURSES = [
    {"id": "101", "name": "Product Management (Jane Prof) FA2026", "term": "Fall 2026",
     "term_start": "", "roles": ["student"]},
    {"id": "102", "name": "Negotiations (Bob Prof) FA2026", "term": "Fall 2026",
     "term_start": "", "roles": ["student"]},
    {"id": "103", "name": "Business Analytics II (Ta Course) FA2026", "term": "Fall 2026",
     "term_start": "", "roles": ["ta"]},
]


class Resp:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def with_url(f, cid):
    return {**f, "url": f"{C}/files/{f['id']}/download", "updated_at": "2026-09-01T00:00:00Z",
            "filename": f.get("filename") or f["display_name"]}


class FakeCanvas:
    downloads = []

    def __init__(self, *_):
        self.s = self

    def get(self, path, params=None, **_):  # also stands in for requests.Session.get
        path = path.replace(C, "").replace("/api/v1", "")
        for cid, files in FILES.items():
            if path.startswith(f"/courses/{cid}/files/") or path.startswith("/files/"):
                fid = path.rsplit("/", 1)[-1]
                if fid in HIDDEN:
                    return Resp(200, with_url(HIDDEN[fid], cid))
                return Resp(404)
        if path.startswith("/courses?") or path == "/courses":
            return Resp(200, [])
        return Resp(404)

    def json(self, path, params=None):
        cid = path.split("/")[2] if path.startswith("/courses/") else None
        if path == f"/courses/{cid}":
            return {"syllabus_body": SYLLABUS.get(cid, "")}
        r = self.get(path)
        r.raise_for_status()
        return r.json()

    def paginate(self, path, params=None):
        params = params or {}
        if path == "/calendar_events":
            cid = params["context_codes[]"].split("_")[1]
            return iter(EVENTS.get(cid, []))
        if path == "/announcements":
            return iter([])
        cid, what = path.split("/")[2], path.split("/")[3]
        data = {"files": [with_url(f, cid) for f in FILES.get(cid, [])],
                "folders": FOLDERS.get(cid, []), "modules": MODULES.get(cid, []),
                "assignments": ASSIGNMENTS.get(cid, []), "pages": []}.get(what)
        if data is None:
            raise requests.HTTPError(response=Resp(404))
        return iter(data)

    def download(self, url, tmp):
        fid = url.rsplit("/", 2)[-2]
        size = next((f["size"] for fs in FILES.values() for f in fs if str(f["id"]) == fid),
                    HIDDEN.get(fid, {}).get("size", 1))
        assert size < MB, f"downloaded a file over the cap: {fid}"
        FakeCanvas.downloads.append(fid)
        with open(tmp, "wb") as fh:
            fh.write(b"x" * size)

    def courses(self):
        return COURSES


FAKE = FakeCanvas()
cli.canvas_for = lambda ws: FAKE
cli.Canvas = FakeCanvas


def run(*argv):
    """Run the CLI, return (exit code, output)."""
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cli.main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if e.code and not isinstance(e.code, int):
                print(e.code)
    return code, out.getvalue()


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deep on purpose: makes Windows' 260-character path limit bite.
        cls.root = os.path.join(tempfile.mkdtemp(prefix="cw-"), "My Drive", "School",
                                "A folder with a long name to push the path length", "Fall 2026")
        os.makedirs(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(cls.root)))),
                      ignore_errors=True)
        shutil.rmtree(HOME, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def ledger(self):
        with open(self.p(".coursework", "ledger.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_full_flow(self):
        pm = self.p("A-term", "Product Management")

        # init: term grouping worked out from class dates; TA course listed, not added
        code, out = run("init", self.root, "--add", "101,102", "--group-by-term")
        self.assertEqual(code, 0, out)
        self.assertIn("ta", out)
        self.assertTrue(os.path.isdir(pm), out)
        self.assertTrue(os.path.isdir(self.p("Full Term", "Negotiations")), out)
        self.assertEqual(sorted(os.listdir(self.root)), [".coursework", "A-term", "Full Term"])

        # dry run writes nothing
        code, out = run("--root", self.root, "sync", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(FakeCanvas.downloads, [])
        self.assertIn("WOULD-ADD", out)

        # real sync
        code, out = run("--root", self.root, "sync")
        self.assertEqual(code, 0, out)
        must = [("Syllabus", "Syllabus Fall 2026.pdf"), ("Café – “Notes” ✓.pdf",),
                ("Readings", "S02 Pitney Case.pdf"),          # loose in "unfiled" -> Readings/
                ("Real Syllabus.pdf",),                         # only on the Syllabus page
                ("Readings", "S03 Platforms Reading.pdf"),      # only in a calendar event
                ("Assignments", "Answer Key PS1.pdf"),          # only in an assignment
                ("_CON.pdf",), ("Session01 deck.pdf",),         # reserved name, missing extension
                ("Canvas_Assignments.md",), ("Canvas_Links.md",)]
        for parts in must:
            self.assertTrue(os.path.exists(os.path.join(pm, *parts)), f"missing {parts}\n{out}")
        for absent in ("Big deck.pdf", "Lecture 1.mp4", "prof-headshot.jpg"):
            self.assertFalse(any(absent in f for _d, _s, fs in os.walk(pm) for f in fs), absent)
        self.assertIn("TOO-LARGE", out)
        self.assertIn("LINKS", out)
        self.assertIn("PREFIXED", out)
        self.assertIn("FLATTENED", out)

        # the deep, long-named file landed, within Windows' limit there
        deep = [os.path.join(d, f) for d, _s, fs in os.walk(pm) for f in fs if f.startswith("An Extremely")]
        self.assertEqual(len(deep), 1, deep)
        if sys.platform == "win32":
            self.assertLessEqual(len(deep[0]), 240)

        with open(os.path.join(pm, "Canvas_Links.md"), encoding="utf-8") as fh:
            links = fh.read()
        for want in ("Google Glass", "Harvard coursepack", "Pitney Bowes HBS", "Platform article"):
            self.assertIn(want, links)
        self.assertNotIn("linkedin", links)

        # verify passes, and a second sync has nothing to do
        code, out = run("--root", self.root, "verify")
        self.assertEqual(code, 0, out)
        self.assertIn("VERIFIED", out)
        code, out = run("--root", self.root, "sync")
        self.assertIn("changes this run: none", out)
        for e in self.ledger().values():
            self.assertNotIn("\\", e.get("saved_to") or "", "ledger paths must use /")

        # next: the next class, its notes with local files, what's due
        code, out = run("--root", self.root, "next", "pm")
        self.assertEqual(code, 0, out)
        self.assertIn("S3 Platforms", out)
        self.assertIn("Readings/S03 Platforms Reading.pdf", out.replace("\\", "/"))
        self.assertIn("Case write-up", out)
        self.assertIn("Final exam window closes", out)
        code, out = run("--root", self.root, "next", "--save")
        self.assertTrue(os.path.exists(self.p("Up next.md")))

        # rename through the tool, then a Finder-style rename reconnected afterwards
        code, out = run("--root", self.root, "rename", "pm", "A-term/PM")
        self.assertEqual(code, 0, out)
        os.rename(self.p("Full Term", "Negotiations"), self.p("Full Term", "Negs"))
        code, out = run("--root", self.root, "verify")
        self.assertNotEqual(code, 0)
        self.assertIn("is gone", out)
        run("--root", self.root, "rename", "Negotiations", "Full Term/Negs")
        code, out = run("--root", self.root, "verify")
        self.assertEqual(code, 0, out)

        # ignore + delete an old version: stays gone after a sync
        old = self.p("A-term", "PM", "Syllabus", "Syllabus Fall 2026.pdf")
        code, out = run("--root", self.root, "ignore", old, "--delete")
        self.assertFalse(os.path.exists(old))
        run("--root", self.root, "sync")
        self.assertFalse(os.path.exists(old))
        code, out = run("--root", self.root, "verify")
        self.assertEqual(code, 0, out)

        # ungroup: back to flat folders, still verified
        code, out = run("init", self.root, "--no-group-by-term")
        self.assertTrue(os.path.isdir(self.p("PM")), out)
        code, out = run("--root", self.root, "verify")
        self.assertEqual(code, 0, out)

        # Echo360 gate: no class since the last transcript -> no browser at all
        cfgp = self.p(".coursework", "config.json")
        with open(cfgp, encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["courses"]["102"]["echo360"] = {"section": "x", "group": ""}
        with open(cfgp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        held = [i for i in range(8) if NOW + timedelta(days=-40 + 13 * i) < NOW - timedelta(hours=3)]
        with open(self.p(".coursework", "echo360_ledger.json"), "w", encoding="utf-8") as fh:
            json.dump({f"m{i}": {"course_id": "102", "session": i, "status": "downloaded"}
                       for i in held}, fh)
        echo360.Browser = None  # any attempt to open a browser would crash the test
        code, out = run("--root", self.root, "echo360", "pull")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to pull", out)

    def test_pasted_token_retries_and_strips_invisible_characters(self):
        answers = iter(["", "\u200b1234~" + "z" * 40 + "\u00a0\n"])  # empty paste, then one with junk
        cli.getpass.getpass = lambda prompt="": next(answers)
        code, out = run("token")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing was pasted", out)
        self.assertIn("accepted by Canvas", out)
        with open(os.path.join(HOME, ".config", "coursework", "canvas_token"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "1234~" + "z" * 40)

    def test_clipboard_token(self):
        cli._clipboard = lambda clear=False: None if clear else "  1234~" + "y" * 40 + "\n"
        code, out = run("token", "--from-clipboard")
        self.assertEqual(code, 0, out)
        self.assertIn("accepted by Canvas", out)
        self.assertNotIn("yyyy", out)  # never printed
        with open(os.path.join(HOME, ".config", "coursework", "canvas_token"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "1234~" + "y" * 40)


if __name__ == "__main__":
    unittest.main()
