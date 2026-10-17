"""Where things live.

A *workspace* is the term folder you study from, e.g. "My Drive/School/Spring 2027".
It holds your course folders and exactly one hidden folder, `.coursework/`, with
the sync state. No scripts, no tokens, nothing else at the top level.

    Spring 2027/
      .coursework/          config.json, ledger.json, changes.log, echo360_ledger.json
      Product Management/
      Negotiations/

Secrets never go in the workspace (it is usually inside Google Drive or Dropbox,
which would upload them). They live in ~/.config/coursework/:

    ~/.config/coursework/canvas_token          your Canvas access token
    ~/.config/coursework/echo360_cookies.json  Echo360 login (add-on only)

CANVAS_TOKEN in the environment overrides the token file.
"""

import json
import os
import re
import stat
import sys

STATE_DIRNAME = ".coursework"
USER_DIR = os.path.join(os.path.expanduser("~"), ".config", "coursework")
TOKEN_FILE = os.path.join(USER_DIR, "canvas_token")

DEFAULT_CONFIG = {
    "canvas_url": "https://courseworks2.columbia.edu",
    "term": None,
    "max_mb": 30,
    "echo360_tool_id": 18261,
    "courses": {},
}


class Workspace:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.state = os.path.join(self.root, STATE_DIRNAME)
        self.config_file = os.path.join(self.state, "config.json")
        self.ledger_file = os.path.join(self.state, "ledger.json")
        self.change_log = os.path.join(self.state, "changes.log")
        self.echo_ledger_file = os.path.join(self.state, "echo360_ledger.json")
        self._config = None
        self._ledger = None

    # -- discovery ---------------------------------------------------------
    @classmethod
    def find(cls, start=None):
        """Walk up from `start` (default: cwd) to the folder holding .coursework/,
        the way git finds .git/. So any course subfolder works as a cwd."""
        here = os.path.abspath(start or os.getcwd())
        while True:
            if os.path.isdir(os.path.join(here, STATE_DIRNAME)):
                return cls(here)
            parent = os.path.dirname(here)
            if parent == here:
                sys.exit("Not inside a coursework folder. Run `coursework init` in your "
                         "term folder first, or pass --root <folder>.")
            here = parent

    @classmethod
    def create(cls, root):
        ws = cls(root)
        os.makedirs(ws.state, exist_ok=True)
        if not os.path.exists(ws.config_file):
            save_json(ws.config_file, DEFAULT_CONFIG)
        return ws

    # -- state ---------------------------------------------------------------
    @property
    def config(self):
        if self._config is None:
            self._config = {**DEFAULT_CONFIG, **load_json(self.config_file, {})}
        return self._config

    def save_config(self):
        save_json(self.config_file, self.config)

    @property
    def ledger(self):
        if self._ledger is None:
            self._ledger = load_json(self.ledger_file, {})
        return self._ledger

    def save_ledger(self):
        save_json(self.ledger_file, self.ledger)

    def abspath(self, rel):
        return os.path.join(self.root, rel)

    def relpath(self, path):
        return os.path.relpath(path, self.root)

    def resolve_course(self, arg):
        """Course id, or a (partial) folder name -> configured course id."""
        courses = self.config["courses"]
        if arg.isdigit():
            if arg not in courses:
                sys.exit(f"Course {arg} is not set up here. Add it with `coursework add {arg}`.")
            return arg
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        key = norm(arg)
        exact = [cid for cid, c in courses.items()
                 if key and norm(c["folder"].rsplit("/", 1)[-1]) == key]
        if len(exact) == 1:
            return exact[0]
        hits = [cid for cid, c in courses.items() if key and key in norm(c["folder"])]
        if not hits:  # initials: "pm" -> Product Management, "tip" -> Trade and Industrial Policies
            initials = lambda f: "".join(w[0] for w in re.findall(r"[A-Za-z]+", f.rsplit("/", 1)[-1])
                                         if w.lower() not in ("and", "of", "the", "for", "in")).lower()
            hits = [cid for cid, c in courses.items() if initials(c["folder"]) == key]
        if len(hits) != 1:
            known = ", ".join(c["folder"] for c in courses.values()) or "none yet"
            sys.exit(f"'{arg}' matches {len(hits)} courses. Set up here: {known}")
        return hits[0]


# -- helpers -------------------------------------------------------------------
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return default


def save_json(path, data):
    """Write atomically, so a crash mid-run never leaves half a ledger."""
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)


def write_secret(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def read_token():
    token = os.environ.get("CANVAS_TOKEN", "").strip()
    if not token and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as fh:
            token = fh.read().strip()
    return token or None
