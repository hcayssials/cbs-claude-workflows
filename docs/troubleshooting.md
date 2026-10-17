# Troubleshooting

Problems hit while running this for a full term, and what fixes them.

| You see | What it means | Do this |
|---|---|---|
| `Canvas said 401` | Token missing or expired | Make a new token, `coursework token` |
| `Not inside a coursework folder` | You're outside your term folder | `cd` into it, or pass `--root "<folder>"` |
| `note NO-ACCESS … Files tab returned 403` | You dropped the course, or the professor hid the Files tab | `coursework drop "<course>"` if you dropped it |
| `note LOCKED … not downloadable` | A professor linked a file students can't open | Nothing; ask the professor if you need it |
| `note TOO-LARGE` | Over 100 MB (usually a slide deck with video) | `coursework sync "<course>" --max-mb 0` |
| `note FLATTENED` | Canvas folders deeper than 3 levels were collapsed | Add a route (README → Routing) |
| `verify`: `WOULD-WRITE Canvas_Assignments.md` | A professor edited an assignment description since your last sync | `coursework sync`. That's real, not a bug |
| `verify`: files missing | You moved, renamed or deleted them | Moved/renamed: `coursework verify --fix`. Deleted on purpose: `coursework ignore "<path>"` |
| Two near-identical copies of a reading | The professor uploaded it twice (Files tab and a hidden link, or a re-upload) | Keep one, `coursework ignore "<other>" --delete` |
| A required case isn't there | It's on the Harvard/HBP coursepack tool, which the Canvas API can't reach | Download it from the course page by hand |
| Hidden readings named "Session 7_ …" in a session-9 slot | The professor reused last year's file names | Trust the Canvas calendar, not the file name |
| `Your Echo360 login has expired` | Logins last roughly 2–4 days | `coursework echo360 login`, **then press Enter** in the terminal |
| `echo360 setup`: `no Echo360 recordings` | The course uses Zoom, or nothing is recorded yet | Try again after the first class |
| `echo360 setup`: `split by section: 001, 002` | Recordings are per section | Re-run with `--group 001` (your section) |
| Transcript has a Session number off by one from the syllabus | Echo360 numbers by recording, not course session | The Master Takeaways skill maps them; check the calendar |
