"""coursework: keep a term folder in sync with Canvas.

  coursework init                 set up this folder (asks for your token, picks courses)
  coursework sync                 pull everything new; safe to run any time
  coursework sync --dry-run       show what would change, download nothing
  coursework verify               check the folder is complete (run after a sync)
  coursework next                 what you need for each course's next class
  coursework courses              list your Canvas courses this term
  coursework add <id> [--as NAME] start syncing a course
  coursework rename <course> NEW  rename a course folder (do this, not Finder)
  coursework drop <course>        stop syncing a course (keeps its files)
  coursework ignore <file>        never re-download this file (e.g. an old version)
  coursework token                save or replace your Canvas token
  coursework echo360 ...          lecture transcripts (optional add-on; see README)
"""

import argparse
import getpass
import os
import sys
from collections import Counter

from . import sync as S
from .canvas import Canvas
from .naming import course_folder_name, sanitize
from .workspace import DEFAULT_CONFIG, TOKEN_FILE, Workspace, read_token, write_secret


def canvas_for(ws):
    token = read_token()
    if not token:
        sys.exit("No Canvas token yet. Run `coursework token` in a terminal.")
    return Canvas(ws.config["canvas_url"], token)


def get_ws(args):
    return Workspace.find(args.root)


# -----------------------------------------------------------------------------
# token / init / courses / add / drop
# -----------------------------------------------------------------------------

def _clipboard(clear=False):
    """Read (or clear) the system clipboard without ever printing it."""
    import shutil
    import subprocess
    if sys.platform == "darwin":
        read, write = ["pbpaste"], ["pbcopy"]
    elif shutil.which("wl-paste"):
        read, write = ["wl-paste", "-n"], ["wl-copy"]
    else:
        read, write = ["xclip", "-selection", "clipboard", "-o"], ["xclip", "-selection", "clipboard"]
    if clear:
        subprocess.run(write, input=b"", check=False)
        return None
    return subprocess.run(read, capture_output=True, check=False).stdout.decode().strip()


def cmd_token(args):
    """Save the Canvas token, checking it with Canvas first.

    --from-clipboard is the reliable way: copy the token in Canvas, then run it.
    Nothing is ever printed, and the clipboard is cleared afterwards. (Pasting
    into a hidden prompt fails silently in some terminals.)"""
    from_clip = getattr(args, "from_clipboard", False)
    if from_clip:
        token = "".join((_clipboard() or "").split())
    else:
        print("Make a token in Canvas: Account → Settings → scroll to 'Approved\n"
              "Integrations' → + New Access Token. Paste it below (it won't be shown).")
        token = "".join(getpass.getpass("Canvas token: ").split())
    if not token:
        sys.exit("No token found" + (" on the clipboard. Copy it in Canvas first." if from_clip
                                     else ". Try `coursework token --from-clipboard` instead."))
    if len(token) < 20:
        sys.exit("That doesn't look like a Canvas token (too short). Copy the whole token and try again.")
    base = DEFAULT_CONFIG["canvas_url"]
    try:
        base = Workspace.find(args.root).config["canvas_url"]
    except SystemExit:
        pass
    resp = Canvas(base, token).s.get(f"{base}/api/v1/courses", params={"per_page": 1}, timeout=30)
    if resp.status_code == 401:
        sys.exit("Canvas rejected that token (copied only part of it, or it was deleted). Nothing saved.")
    write_secret(TOKEN_FILE, token)
    if from_clip:
        _clipboard(clear=True)
    print(f"Token saved ({len(token)} characters) and accepted by Canvas."
          + (" Clipboard cleared." if from_clip else ""))


def pick_term(courses):
    """The term of your most recent courses, ignoring Canvas's catch-all terms."""
    real = [c for c in courses if c["term"] and "default" not in c["term"].lower()]
    if not real:
        return None
    latest = max(c["term_start"] for c in real)
    return Counter(c["term"] for c in real if c["term_start"] == latest).most_common(1)[0][0]


def cmd_init(args):
    root = os.path.abspath(args.folder or os.getcwd())
    ws = Workspace.create(root)
    print(f"Coursework folder: {root}")
    if args.canvas_url:
        ws.config["canvas_url"] = args.canvas_url.rstrip("/")
    if args.max_mb is not None:
        ws.config["max_mb"] = args.max_mb
        ws.save_config()
        print(f"Size cap for this folder: {args.max_mb:g} MB" if args.max_mb else
              "Size cap for this folder: none")
    if not read_token():
        if not sys.stdin.isatty():
            sys.exit("No Canvas token yet. Run `coursework token` in a terminal, then "
                     "re-run init.")
        cmd_token(args)
    c = canvas_for(ws)
    courses = c.courses()
    ws.config["term"] = args.term or ws.config.get("term") or pick_term(courses)
    ws.save_config()
    print(f"Term: {ws.config['term']}  (change with `coursework init --term \"Spring 2027\"`)")
    this_term = [x for x in courses if x["term"] == ws.config["term"]]
    from .terms import infer_buckets
    buckets = infer_buckets(c, [x["id"] for x in this_term])
    if args.group_by_term is not None:
        ws.config["group_by_term"] = args.group_by_term
        ws.save_config()
        regroup(ws, buckets)
    show_courses(ws, this_term, buckets)

    to_add = []
    if args.add == "all":
        to_add = [x for x in this_term if "student" in x["roles"]]
    elif args.add:
        wanted = set(args.add.split(","))
        to_add = [x for x in this_term if x["id"] in wanted]
        for cid in wanted - {x["id"] for x in to_add}:
            print(f"  ! {cid} is not one of your {ws.config['term']} courses; skipped")
    elif sys.stdin.isatty():
        print("\nWhich courses should sync here? Course ids separated by spaces, "
              "'all' for every course you're a student in, or Enter to skip.")
        ans = input("> ").strip()
        if ans == "all":
            to_add = [x for x in this_term if "student" in x["roles"]]
        elif ans:
            wanted = set(ans.replace(",", " ").split())
            to_add = [x for x in this_term if x["id"] in wanted]
            for cid in wanted - {x["id"] for x in to_add}:
                print(f"  ! {cid} is not in the list above; skipped")
    for x in to_add:
        add_course(ws, x, bucket=buckets.get(x["id"]))
    ws.save_config()
    if ws.config["courses"]:
        print("\nNext: `coursework sync --dry-run` to preview, then `coursework sync`.")
    else:
        print("\nNo courses yet. Add one with `coursework add <id>`.")


def show_courses(ws, courses, buckets=None):
    buckets = buckets or {}
    print(f"\n{'id':>7}  {'role':<9} {'when':<10} {'set up as':<34} name")
    for x in sorted(courses, key=lambda x: x["name"]):
        cfg = ws.config["courses"].get(x["id"])
        here = (cfg["folder"] + (" (dropped)" if cfg.get("skip") else "")) if cfg else "—"
        when = buckets.get(x["id"]) or "?"
        print(f"{x['id']:>7}  {','.join(x['roles']):<9} {when:<10} {here[:34]:<34} {x['name'][:56]}")
    if any("ta" in x["roles"] or "teacher" in x["roles"] for x in courses):
        print("\nNote: in courses where you're a TA, only course materials are ever "
              "read — student work, names and grades are blocked in the code.")
    if buckets:
        print("'when' is worked out from the class dates on the calendar ('?' = no dated "
              "sessions). With --group-by-term, folders go under A-term/, B-term/, "
              "Full Term/ or Block Week/.")


def add_course(ws, x, folder=None, bucket=None):
    folder = folder or course_folder_name(x["name"])
    if ws.config.get("group_by_term") and "/" not in folder and bucket:
        folder = f"{bucket}/{folder}"
    ws.config["courses"][x["id"]] = {"folder": folder, "canvas_name": x["name"],
                                     "roles": x["roles"], "routes": [], "when": bucket}
    os.makedirs(ws.abspath(folder), exist_ok=True)
    print(f"  + {folder}  (Canvas {x['id']})")


def cmd_courses(args):
    ws = get_ws(args)
    courses = canvas_for(ws).courses()
    if not args.all:
        courses = [x for x in courses if x["term"] == ws.config.get("term")]
    show_courses(ws, courses)


def cmd_add(args):
    ws = get_ws(args)
    courses = {x["id"]: x for x in canvas_for(ws).courses()}
    for cid in args.ids:
        if cid not in courses:
            sys.exit(f"Course {cid} isn't one of your active Canvas courses "
                     f"(see `coursework courses --all`).")
        if cid in ws.config["courses"]:
            ws.config["courses"][cid].pop("skip", None)
            print(f"  = {ws.config['courses'][cid]['folder']} (already set up; re-enabled)")
            continue
        bucket = args.when
        if not bucket and ws.config.get("group_by_term"):
            from .terms import infer_buckets
            bucket = infer_buckets(canvas_for(ws), [cid]).get(cid)
        add_course(ws, courses[cid], args.as_name if len(args.ids) == 1 else None, bucket)
    ws.save_config()


def rename_course(ws, cid, new):
    """Move a course folder and update every record that points into it.

    Works whether or not you've already moved it yourself (in Finder or Drive):
    if the old folder is gone and the new one exists, only the records change."""
    cfg = ws.config["courses"][cid]
    old = cfg["folder"]
    new = "/".join(sanitize(p) for p in new.split("/") if p.strip())
    if not new or new == old:
        return old
    src, dst = ws.abspath(old), ws.abspath(new)
    if os.path.exists(src) and os.path.exists(dst):
        sys.exit(f"Can't rename to '{new}': that folder already exists.")
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        parent = os.path.dirname(src)
        if parent != ws.root and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)  # an emptied A-term/ etc.
    elif not os.path.exists(dst):
        print(f"  note: neither '{old}' nor '{new}' exists yet; only the records change")
    from .workspace import load_json, save_json
    for led_file, led in ((ws.ledger_file, ws.ledger), (ws.echo_ledger_file, load_json(ws.echo_ledger_file, {}))):
        for e in led.values():
            if e.get("course_id") == cid or e.get("course") == old:
                e["course"] = new
                sp = e.get("saved_to") or ""
                if sp == old or sp.startswith(old + "/"):
                    e["saved_to"] = new + sp[len(old):]
        save_json(led_file, led)
    ws._ledger = None
    cfg["folder"] = new
    ws.save_config()
    print(f"  {old}  →  {new}")
    return new


def regroup(ws, buckets):
    for cid, cfg in ws.config["courses"].items():
        name = cfg["folder"].rsplit("/", 1)[-1]
        bucket = cfg.get("when") or buckets.get(cid)
        if ws.config.get("group_by_term"):
            if bucket and "/" not in cfg["folder"]:
                cfg["when"] = bucket
                rename_course(ws, cid, f"{bucket}/{name}")
        elif cfg["folder"].split("/", 1)[0] in ("A-term", "B-term", "Full Term", "Block Week"):
            rename_course(ws, cid, name)


def cmd_rename(args):
    ws = get_ws(args)
    rename_course(ws, ws.resolve_course(args.course), args.new_name)


def cmd_drop(args):
    ws = get_ws(args)
    cid = ws.resolve_course(args.course)
    ws.config["courses"][cid]["skip"] = True
    ws.config["courses"][cid]["skip_reason"] = args.reason or "dropped"
    ws.save_config()
    print(f"Stopped syncing {ws.config['courses'][cid]['folder']}. Its files and history "
          f"are kept; `coursework add {cid}` resumes it.")


# -----------------------------------------------------------------------------
# sync / verify / ignore
# -----------------------------------------------------------------------------

def selected_courses(ws, names):
    cfgs = ws.config["courses"]
    if names:
        return list(dict.fromkeys(ws.resolve_course(n) for n in names))
    return [cid for cid, c in cfgs.items() if not c.get("skip")]


def run_sync(ws, names, dry_run, max_mb=None, quiet=False):
    run = S.Run(ws, canvas_for(ws), dry_run=dry_run, max_mb=max_mb, quiet=quiet)
    if not ws.config["courses"]:
        sys.exit("No courses set up yet: `coursework courses`, then `coursework add <id>`.")
    for cid in selected_courses(ws, names):
        cfg = ws.config["courses"][cid]
        run.say(f"\n=== {cfg['folder']}")
        S.sync_course(run, cid, cfg)
    S.write_change_log(run)
    return run


def summarize(run):
    kinds = Counter(k for _, k, _ in run.changes)
    print("\n" + "=" * 60)
    print("changes this run: " + (", ".join(f"{v} {k.lower()}" for k, v in sorted(kinds.items()))
                                  or "none"))
    for folder, kind, detail in run.notes:
        print(f"  note  {kind:<10} {folder}: {detail}")
    print(f"full log: {run.ws.relpath(run.ws.change_log)}")


def cmd_sync(args):
    ws = get_ws(args)
    run = run_sync(ws, args.courses, args.dry_run, args.max_mb)
    summarize(run)
    if args.dry_run:
        for folder, kind, detail in run.changes:
            print(f"  {kind:<12} {detail}")


def cmd_verify(args):
    """Passes only when a fresh dry run finds nothing to do AND every file the
    ledger says you have is actually on disk."""
    ws = get_ws(args)
    print("Checking Canvas for anything not yet synced…")
    run = run_sync(ws, args.courses, dry_run=True, quiet=True)
    pending = run.changes
    missing = S.missing_on_disk(ws)
    if missing and args.fix:
        fixed, missing = S.relink(ws, missing)
        for p in fixed:
            print(f"  relinked (you had moved or renamed it): {p}")
    ok = not pending and not missing
    print(f"\n1. nothing left to sync:   {'PASS' if not pending else f'FAIL ({len(pending)})'}")
    for _, kind, detail in pending[:20]:
        print(f"     {kind:<12} {detail}")
    print(f"2. every file is on disk:  {'PASS' if not missing else f'FAIL ({len(missing)} missing)'}")
    for _fid, e in missing[:20]:
        print(f"     missing  {e['saved_to']}")
    gone = [c["folder"] for c in ws.config["courses"].values()
            if not c.get("skip") and not os.path.isdir(ws.abspath(c["folder"]))]
    for f in gone:
        print(f"   The folder '{f}' is gone. Renamed it yourself? "
              f"`coursework rename \"{f}\" \"<new name>\"` reconnects it.")
    if missing and not args.fix:
        print("   Moved or renamed them? `coursework verify --fix` re-finds them.\n"
              "   Deleted on purpose? `coursework ignore <path>` so they stay gone.")
    if any(k == "WOULD-WRITE" for _, k, _ in pending):
        print("   (A pending Canvas_Assignments.md usually means a professor just edited "
              "a description. Run `coursework sync`.)")
    for folder, kind, detail in run.notes:
        print(f"   note  {kind:<10} {folder}: {detail}")
    print("\nVERIFIED" if ok else "\nNOT VERIFIED")
    sys.exit(0 if ok else 1)


def cmd_next(args):
    from . import upnext
    from .workspace import load_json
    ws = get_ws(args)
    cids = selected_courses(ws, args.courses)
    plan = upnext.build(canvas_for(ws), {cid: ws.config["courses"][cid] for cid in cids},
                        ws.ledger, load_json(ws.echo_ledger_file, {}), ws.root)
    print(upnext.render(plan, full=args.full))
    if args.save:
        path = ws.abspath("Up next.md")
        with open(path, "w") as fh:
            fh.write(upnext.render(plan, markdown=True))
        print(f"Saved to {ws.relpath(path)} (overwritten each time).")


def cmd_ignore(args):
    ws = get_ws(args)
    reason = args.reason or "excluded by hand"
    for path in args.paths:
        rel = ws.relpath(os.path.abspath(path))
        hits = [e for e in ws.ledger.values() if e.get("saved_to") == rel]
        if not hits:
            print(f"  not a synced file: {rel}")
            continue
        for e in hits:
            e.update(status="ignored", ignored_reason=reason)
        if args.delete and os.path.exists(ws.abspath(rel)):
            os.remove(ws.abspath(rel))
            print(f"  ignored and deleted: {rel}")
        else:
            print(f"  ignored: {rel}")
    ws.save_ledger()


# -----------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="coursework", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="the term folder (default: found from where you are)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="set up a term folder")
    p.add_argument("folder", nargs="?", help="default: the current folder")
    p.add_argument("--term", help='Canvas term name, e.g. "Spring 2027" (default: latest)')
    p.add_argument("--add", help="'all' or comma-separated course ids (skips the prompt)")
    p.add_argument("--canvas-url", help="only if your school is not Columbia")
    p.add_argument("--max-mb", type=float, help="this folder's size cap; 0 = none (default 30)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--group-by-term", dest="group_by_term", action="store_true", default=None,
                   help="put courses under A-term/, B-term/, Full Term/, Block Week/ (moves existing ones)")
    g.add_argument("--no-group-by-term", dest="group_by_term", action="store_false",
                   help="one flat folder per course (moves existing ones back)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("token", help="save your Canvas token")
    p.add_argument("--from-clipboard", action="store_true",
                   help="read it from the clipboard (never shown), then clear the clipboard")
    p.set_defaults(fn=cmd_token)

    p = sub.add_parser("courses", help="list Canvas courses")
    p.add_argument("--all", action="store_true", help="every term, not just this one")
    p.set_defaults(fn=cmd_courses)

    p = sub.add_parser("add", help="start syncing a course")
    p.add_argument("ids", nargs="+")
    p.add_argument("--as", dest="as_name", help='folder name, e.g. "PM" or "A-term/PM"')
    p.add_argument("--when", choices=["A-term", "B-term", "Full Term", "Block Week"],
                   help="which part of the term, when it can't be worked out")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("rename", help="rename (or move) a course folder, keeping its sync history")
    p.add_argument("course")
    p.add_argument("new_name", help='e.g. "PM" or "A-term/PM"')
    p.set_defaults(fn=cmd_rename)

    p = sub.add_parser("drop", help="stop syncing a course (keeps files)")
    p.add_argument("course")
    p.add_argument("--reason")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("sync", help="pull new and updated material")
    p.add_argument("courses", nargs="*", help="course ids or partial folder names")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-mb", type=float, help="this run only: skip bigger files, 0 = no limit "
                   "(the folder's own cap, default 30, is set with `init --max-mb`)")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("next", help="what you need for each course's next class")
    p.add_argument("courses", nargs="*")
    p.add_argument("--full", action="store_true", help="don't shorten long prep notes")
    p.add_argument("--save", action="store_true", help='also write "Up next.md" in the term folder')
    p.set_defaults(fn=cmd_next)

    p = sub.add_parser("verify", help="check nothing is missing")
    p.add_argument("courses", nargs="*")
    p.add_argument("--fix", action="store_true", help="re-find files you moved or renamed")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("ignore", help="never re-download these files")
    p.add_argument("paths", nargs="+")
    p.add_argument("--reason")
    p.add_argument("--delete", action="store_true", help="also delete the local copy")
    p.set_defaults(fn=cmd_ignore)

    p = sub.add_parser("echo360", help="lecture transcripts (optional add-on)")
    p.add_argument("action", choices=["login", "setup", "status", "pull"])
    p.add_argument("courses", nargs="*")
    p.add_argument("--group", help="your section/cohort, e.g. 001 (setup only)")
    p.add_argument("--keep-vtt", action="store_true", help="also keep the raw .vtt files")
    p.add_argument("--force", action="store_true", help="pull: check Echo360 even if no class has finished")
    p.set_defaults(fn=lambda a: __import__("coursework.echo360", fromlist=["x"]).main(a))

    args = ap.parse_args(argv)
    args.fn(args)
