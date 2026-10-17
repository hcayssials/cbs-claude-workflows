"""coursework: keep a term folder in sync with Canvas.

  coursework init                 set up this folder (asks for your token, picks courses)
  coursework sync                 pull everything new; safe to run any time
  coursework sync --dry-run       show what would change, download nothing
  coursework verify               check the folder is complete (run after a sync)
  coursework next                 what you need for each course's next class
  coursework courses              list your Canvas courses this term
  coursework add <id> [--as NAME] start syncing a course
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
from .naming import course_folder_name
from .workspace import TOKEN_FILE, Workspace, read_token, write_secret


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

def cmd_token(args):
    print("Make a token in Canvas: Account → Settings → scroll to 'Approved\n"
          "Integrations' → + New Access Token. Paste it below (it won't be shown).")
    token = getpass.getpass("Canvas token: ").strip()
    if not token:
        sys.exit("Nothing pasted; token unchanged.")
    write_secret(TOKEN_FILE, token)
    print(f"Saved to {TOKEN_FILE} (readable only by you, outside your Drive).")


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
    show_courses(ws, this_term)

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
        add_course(ws, x)
    ws.save_config()
    if ws.config["courses"]:
        print("\nNext: `coursework sync --dry-run` to preview, then `coursework sync`.")
    else:
        print("\nNo courses yet. Add one with `coursework add <id>`.")


def show_courses(ws, courses):
    print(f"\n{'id':>7}  {'role':<9} {'set up as':<34} name")
    for x in sorted(courses, key=lambda x: x["name"]):
        cfg = ws.config["courses"].get(x["id"])
        here = (cfg["folder"] + (" (dropped)" if cfg.get("skip") else "")) if cfg else "—"
        print(f"{x['id']:>7}  {','.join(x['roles']):<9} {here[:34]:<34} {x['name'][:60]}")
    if any("ta" in x["roles"] or "teacher" in x["roles"] for x in courses):
        print("\nNote: in courses where you're a TA, only course materials are ever "
              "read — student work, names and grades are blocked in the code.")


def add_course(ws, x, folder=None):
    folder = folder or course_folder_name(x["name"])
    ws.config["courses"][x["id"]] = {"folder": folder, "canvas_name": x["name"],
                                     "roles": x["roles"], "routes": []}
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
        add_course(ws, courses[cid], args.as_name if len(args.ids) == 1 else None)
    ws.save_config()


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
    p.set_defaults(fn=cmd_init)

    sub.add_parser("token", help="save your Canvas token").set_defaults(fn=cmd_token)

    p = sub.add_parser("courses", help="list Canvas courses")
    p.add_argument("--all", action="store_true", help="every term, not just this one")
    p.set_defaults(fn=cmd_courses)

    p = sub.add_parser("add", help="start syncing a course")
    p.add_argument("ids", nargs="+")
    p.add_argument("--as", dest="as_name", help='folder name, e.g. "PM" or "A-term/PM"')
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("drop", help="stop syncing a course (keeps files)")
    p.add_argument("course")
    p.add_argument("--reason")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("sync", help="pull new and updated material")
    p.add_argument("courses", nargs="*", help="course ids or partial folder names")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-mb", type=float, help="skip bigger files; 0 = no limit (default 30)")
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
