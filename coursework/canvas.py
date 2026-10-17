"""Canvas API client: read-only, polite, and unable to touch student data."""

import sys
import time

import requests

PER_PAGE = 100

# Never request these, in any course. If you are a TA, these endpoints would
# return other students' work, names or grades. Blocked here, not merely unused:
# do not widen or remove this list.
FORBIDDEN = ("/submissions", "/gradebook", "/enrollments", "/users", "/students",
             "/analytics", "/grading", "/quiz_submissions", "/gradeable_students",
             "/student_summaries", "/rubric_assessments")


class Canvas:
    def __init__(self, base_url, token):
        self.base = base_url.rstrip("/")
        self.api = self.base + "/api/v1"
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    def guard(self, url):
        if url.startswith(self.api):
            low = url.lower().split("?")[0]
            for bad in FORBIDDEN:
                if bad in low:
                    raise RuntimeError(f"blocked by student-data guardrail: {url}")

    def get(self, path_or_url, params=None):
        """GET with retry on rate limits and 5xx. Returns the Response."""
        url = path_or_url if path_or_url.startswith("http") else self.api + path_or_url
        self.guard(url)
        resp = None
        for attempt in range(5):
            resp = self.s.get(url, params=params, timeout=60)
            if resp.status_code == 401 and "/files/" not in url:
                sys.exit("Canvas said 401: your token is missing or expired.\n"
                         "Make a new one (Canvas → Account → Settings → + New Access "
                         "Token) and run `coursework token`.")
            if resp.status_code == 429 or (resp.status_code == 403
                                           and "Rate Limit Exceeded" in resp.text):
                time.sleep(2 ** (attempt + 1))
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            _throttle(resp)
            return resp
        return resp

    def json(self, path, params=None):
        resp = self.get(path, params)
        resp.raise_for_status()
        return resp.json()

    def paginate(self, path, params=None):
        params = dict(params or {})
        params["per_page"] = PER_PAGE
        url = self.api + path
        while url:
            resp = self.get(url, params)
            resp.raise_for_status()
            yield from resp.json()
            url = resp.links.get("next", {}).get("url")
            params = None  # the next-page URL already carries the query

    def download(self, url, dest_tmp):
        with self.s.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(dest_tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
            _throttle(resp)

    # -- higher level ----------------------------------------------------------
    def courses(self):
        """Every active enrollment: dicts with id, name, term, term_start, roles."""
        out = []
        for c in self.paginate("/courses", {"include[]": "term",
                                            "state[]": ["available", "completed"]}):
            if not isinstance(c, dict) or not c.get("name"):
                continue  # restricted courses come back without a name
            term = c.get("term") or {}
            out.append({
                "id": str(c["id"]),
                # If you've given a course a nickname in Canvas, `name` is your
                # nickname and `original_name` is the real title.
                "name": c.get("original_name") or c["name"],
                "term": term.get("name") or "",
                "term_start": term.get("start_at") or "",
                "roles": sorted({e.get("type", "?").replace("enrollment", "")
                                 for e in (c.get("enrollments") or [])}),
            })
        return out


def _throttle(resp):
    try:
        remaining = float(resp.headers.get("X-Rate-Limit-Remaining", 700))
    except ValueError:
        remaining = 700
    if remaining < 100:
        time.sleep(2)
    elif remaining < 300:
        time.sleep(0.5)
