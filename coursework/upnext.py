"""`coursework next`: what you need for each course's next class.

Two parts:
  Due in the next 7 days   every assignment and dated calendar item (exam windows,
                           gradebook closing), across all courses
  Next class, per course   the professor's own prep notes from the Canvas calendar,
                           with each linked Canvas file swapped for your local copy
                           (or flagged if it isn't synced yet), and a flag if you're
                           missing the last class's transcript

Printed by default. `--save` also writes "Up next.md" at the top of the term
folder, timestamped and overwritten each time, so there's only ever one.
"""

import os
import re
from datetime import datetime, timedelta, timezone

import requests

from .naming import session_number
from .sync import html_to_text

DUE_WINDOW = timedelta(days=7)
TERMINAL_LINES = 12
FILE_ANCHOR = re.compile(r'<a\b[^>]*href="(?:[^"]*/courses/\d+|)/files/(\d+)[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
TOOL_ANCHOR = re.compile(r'<a\b[^>]*href="[^"]*(?:/external_tools/|hbsp\.harvard\.edu)[^"]*"[^>]*>(.*?)</a>',
                         re.I | re.S)
SECTION_SUFFIX = re.compile(r"\s*\([A-Z]{4}B\d{4}_[^)]*\)\s*$")   # " (MRKTB8636_001_2026_3 - …)"


def _when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone() if iso else None


def _day(dt):
    return dt.strftime("%a %-d %b")


def _time(dt):
    return dt.strftime("%-I:%M%p").lower().replace(":00", "")


def class_title(title, course):
    """'Negotiations Session 7 - feedback' -> 'S7 feedback'; '13. Building X' -> 'S13 Building X'."""
    t = SECTION_SUFFIX.sub("", title or "").strip()
    n = session_number(t)
    if t.lower().startswith(course.lower()):
        t = t[len(course):].strip()
    t = re.sub(r"^\s*(?:(?:session|class|lecture|day)\s*#?\s*)?0*\d{1,2}\s*[:.\-–)_]*\s*", "",
               t, count=1, flags=re.I)
    return f"S{n} {t}".strip() if n else t


def read_calendar(canvas, cid, now):
    """(next class, last session held, other dated items in the due window).

    Canvas returns each event twice: a plain copy and a section-suffixed copy.
    Merged per date: times from the shorter event (the plain copy's end time is
    sometimes wrong), notes from whichever copy has them."""
    classes, others, last_held = {}, [], None
    for ev in canvas.paginate("/calendar_events", {"context_codes[]": f"course_{cid}",
                                                   "type": "event", "all_events": "true"}):
        start, end = _when(ev.get("start_at")), _when(ev.get("end_at"))
        if not start:
            continue
        n = session_number(SECTION_SUFFIX.sub("", ev.get("title") or ""))
        if (end or start) < now:
            if n and (last_held is None or n > last_held):
                last_held = n
            continue
        if not n:
            if start <= now + DUE_WINDOW:
                others.append({"name": SECTION_SUFFIX.sub("", ev.get("title") or ""), "due": end or start})
            continue
        cur = classes.setdefault((start.date(), n), {"title": ev.get("title"), "start": start,
                                                     "end": end, "html": "", "session": n})
        if end and (cur["end"] is None or end < cur["end"]):
            cur["end"] = end
        if len(ev.get("title") or "") < len(cur["title"] or ""):
            cur["title"] = ev.get("title")
        if len(ev.get("description") or "") > len(cur["html"]):
            cur["html"] = ev.get("description") or ""
    first = min(classes.values(), key=lambda e: e["start"]) if classes else None
    # Two dedup'd copies of a deadline event: keep one per name.
    others = list({o["name"]: o for o in others}.values())
    return first, last_held, others


def prep_notes(raw_html, ledger, root, course_folder):
    flags = {}

    def swap(m):
        fid, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        e = ledger.get(fid) or {}
        path = e.get("saved_to") or ""
        if e.get("status") == "downloaded" and os.path.exists(os.path.join(root, path)):
            flags[fid] = "📄 " + os.path.relpath(path, course_folder)
        elif e.get("status") == "unavailable":
            flags[fid] = "⚠ locked on Canvas"
        else:
            flags[fid] = "⚠ not synced yet: run `coursework sync`"
        return f"{label} [[{fid}]]"

    def tool(m):
        label = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return f"{label} (⚠ a Canvas/coursepack link, not a file: get it by hand, see Canvas_Links.md)"

    text = html_to_text(TOOL_ANCHOR.sub(tool, FILE_ANCHOR.sub(swap, raw_html)))
    for fid, flag in flags.items():
        text = text.replace(f"[[{fid}]]", f"({flag})")
    return [ln for ln in text.splitlines() if ln.strip()]


def assignments_due(canvas, cid, now):
    out = []
    try:
        for a in canvas.paginate(f"/courses/{cid}/assignments", {"bucket": "upcoming"}):
            due = _when(a.get("due_at"))
            if due and now <= due <= now + DUE_WINDOW:
                pts = a.get("points_possible")
                out.append({"name": (a.get("name") or "").strip(), "due": due,
                            "points": f"{pts:g}p" if pts else ""})
    except requests.HTTPError:
        pass
    return out


def build(canvas, courses, ledger, echo_ledger, root, now=None):
    now = now or datetime.now(timezone.utc).astimezone()
    classes, due = [], []
    for cid, cfg in courses.items():
        folder = cfg["folder"]
        name = folder.rsplit("/", 1)[-1]
        ev, last_held, others = read_calendar(canvas, cid, now)
        assigned = assignments_due(canvas, cid, now)
        # An exam often exists as both an assignment and a calendar event: keep one.
        times = {a["due"].replace(second=0, microsecond=0) for a in assigned}
        others = [o for o in others if o["due"].replace(second=0, microsecond=0) not in times]
        for d in assigned + others:
            due.append({**d, "course": name})
        if not ev:
            continue
        have = max([e.get("session") or 0 for e in echo_ledger.values()
                    if e.get("course_id") == cid] or [0])
        # A session a pull already gave up on (never recorded) isn't a gap.
        have = max(have, (echo_ledger.get(f"checked:{cid}") or {}).get("session", 0))
        classes.append({
            "course": name, "event": ev, "title": class_title(ev["title"], name),
            "notes": prep_notes(ev["html"], ledger, root, folder),
            "transcript_gap": last_held if cfg.get("echo360") and last_held and last_held > have else None,
        })
    return {"now": now, "due": sorted(due, key=lambda d: d["due"]),
            "classes": sorted(classes, key=lambda c: c["event"]["start"])}


def render(plan, markdown=False, full=False):
    now, out = plan["now"], []
    if markdown:
        out += ["# Up next", "", f"_Updated {_day(now)} at {_time(now)} by `coursework next`. "
                "Rewritten every time, so don't edit it._", ""]

    out.append("## Due in the next 7 days" if markdown else "DUE IN THE NEXT 7 DAYS")
    if not plan["due"]:
        out.append("Nothing." if markdown else "  nothing")
    for d in plan["due"]:
        pts = f" ({d['points']})" if d.get("points") else ""
        line = f"{_day(d['due'])} {_time(d['due'])} · {d['course']} · {d['name'][:90]}{pts}"
        out.append(f"- {line}" if markdown else f"  {line}")

    out += ["", "## Next class, per course" if markdown else "NEXT CLASS, PER COURSE"]
    if not plan["classes"]:
        out.append("No classes left on the calendar.")
    for c in plan["classes"]:
        ev = c["event"]
        when = f"{_day(ev['start'])}, {_time(ev['start'])}" + (f"–{_time(ev['end'])}" if ev["end"] else "")
        out += ["", f"### {c['course']} · {c['title']}", f"_{when}_", ""] if markdown else \
               ["", f"  {c['course']} · {c['title']} · {when}"]
        notes = c["notes"] or ["No prep notes on the Canvas calendar; check the syllabus."]
        if not markdown and not full and len(notes) > TERMINAL_LINES:
            notes = notes[:TERMINAL_LINES] + [f"… {len(notes) - TERMINAL_LINES} more lines "
                                              f"(`coursework next --full` shows everything)"]
        out += [n if markdown else "    " + n for n in notes]
        if c["transcript_gap"]:
            msg = f"⚠ Session {c['transcript_gap']} transcript not pulled yet (`coursework echo360 pull`)"
            out.append(("" if markdown else "    ") + msg)
    return "\n".join(out).strip() + "\n"
