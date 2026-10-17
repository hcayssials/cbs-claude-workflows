"""Which part of the term a course runs in, from its class dates on the calendar.

CBS terms split into A-term (first half), B-term (second half), Full Term and
Block Week. Canvas records none of that (term and course dates are blank or
padded), but the class sessions on the calendar give it away:

  classes span 7 days or less    -> Block Week
  classes span 10 weeks or more  -> Full Term
  otherwise                      -> A-term or B-term, by which half of the
                                    term (across all your courses) they fall in

A course with no numbered classes on its calendar comes back as None: ask.
"""

from datetime import date

from .naming import session_number

BUCKETS = ("A-term", "B-term", "Full Term", "Block Week")


def class_span(canvas, cid):
    days = set()
    try:
        for ev in canvas.paginate("/calendar_events", {"context_codes[]": f"course_{cid}",
                                                       "type": "event", "all_events": "true"}):
            if ev.get("start_at") and session_number(ev.get("title")):
                days.add(date.fromisoformat(ev["start_at"][:10]))
    except Exception:
        return None
    return (min(days), max(days)) if days else None


def infer_buckets(canvas, cids):
    spans = {cid: class_span(canvas, cid) for cid in cids}
    known = [s for s in spans.values() if s]
    if not known:
        return {cid: None for cid in cids}
    term_start = min(s[0] for s in known)
    term_end = max(s[1] for s in known)
    mid = term_start + (term_end - term_start) / 2
    out = {}
    for cid, span in spans.items():
        if not span:
            out[cid] = None
            continue
        first, last = span
        length = (last - first).days
        if length <= 7:
            out[cid] = "Block Week"
        elif length >= 70:
            out[cid] = "Full Term"
        elif last <= mid + (mid - term_start) / 4:
            out[cid] = "A-term"
        elif first >= mid - (term_end - mid) / 4:
            out[cid] = "B-term"
        else:
            out[cid] = None
    return out
