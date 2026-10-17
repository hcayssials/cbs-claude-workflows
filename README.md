# CBS Claude workflows

Most AI use at school is "ask a question, get an answer". This repo is the other
kind: **a workflow that runs every week and does the boring part for you**, so the
AI's time goes to the part that's actually worth it.

```
Canvas ──coursework sync──▶ your term folder ──Echo360 add-on──▶ Transcripts/ ──Claude──▶ Master Takeaways_<Class>.md
 (files, hidden readings,    (one tidy folder         (lecture transcripts,          (one living study doc
  assignment descriptions)    per course)              plain text)                     per class)
```

1. **`coursework sync`** pulls everything from Canvas into one folder per course:
   files, the readings professors link from the calendar or a page without putting
   them on the Files tab, and every assignment description. Run it whenever you like:
   it only fetches what's new.
2. **Echo360 add-on** (optional): pulls lecture transcripts as plain text.
3. **Two Claude skills**: one so Claude can run all of this for you ("sync my
   classes"), and one that turns a course folder into a `Master Takeaways` study doc
   and keeps it updated as transcripts arrive.

Built for Columbia CourseWorks. It works for any Canvas school with one setting change
(see [Not at Columbia?](#not-at-columbia)).

---

## Setup (5 minutes, once)

You need a Mac (or Linux) with Python 3.9+ (`python3 --version`) and git.

```bash
git clone https://github.com/hcayssials/cbs-claude-workflows.git ~/cbs-claude-workflows
```

```bash
~/cbs-claude-workflows/setup.sh
```

Then go to the folder you want your courses in (a new folder, or your existing term
folder in Google Drive) and initialise it:

```bash
cd "$HOME/Library/CloudStorage/GoogleDrive-<you>/My Drive/School/B-term"
```

```bash
coursework init
```

`init` asks for a **Canvas token** the first time. To make one, go to CourseWorks →
Account → Settings → *Approved Integrations* → **+ New Access Token** and paste it in.
It's stored in `~/.config/coursework/`, outside your Drive, readable only by you. Then
`init` lists your courses for the current term and asks which ones to sync.

That's all the setup. Nothing in this repo needs editing.

### Prefer to let Claude do it?

After `setup.sh`, open Claude Code in your term folder and say:

> Set up coursework sync in this folder for my B-term classes.

The `coursework-sync` skill knows the steps. It will ask **you** to paste the token in
the terminal (agents never handle your token or your Duo login) and ask before adding
each course.

---

## Every week

```bash
coursework sync --dry-run    # optional: preview what would land
```

```bash
coursework sync
```

```bash
coursework verify            # VERIFIED = nothing left on Canvas, nothing missing on disk
```

Or just tell Claude "sync my classes". A new course turns up mid-term?
`coursework courses`, then `coursework add <id>`. Dropped one? `coursework drop "<name>"`
(your files are kept).

## What do I need for my next class?

```bash
coursework next              # or: coursework next pm
```

For each course's next class: the professor's prep notes from the Canvas calendar, with
every linked reading shown as **your local file** (or flagged if it isn't synced yet),
plus everything due in the next 7 days across all courses. Or ask Claude "what do I need
for Thursday?". `--save` also writes it to `Up next.md` (one file, overwritten each time).

```
DUE IN THE NEXT 7 DAYS
  Tue 20 Oct 5pm · US Healthcare · Final Exam (100p)

NEXT CLASS, PER COURSE
  Transforming Healthcare Services · S1 The Business of Healthcare · Tue 27 Oct, 10:50am–12:20pm
    Required Reading: US Healthcare System Profile (📄 Class 1_ …/Commonwealth Fund.pdf) …
  Negotiations · S7 feedback / interpersonal styles · Wed 28 Oct, 9am–12:15pm
    No prep notes on the Canvas calendar; check the syllabus.
```

## What your folder looks like

Your term folder holds your course folders and one hidden `.coursework/` folder.
No scripts, no config files, no clutter.

```
B-term/
  .coursework/                         sync state; don't edit
  Product Management/
    Canvas_Assignments.md              every assignment description, kept current
    Course Slides/…                    the professor's folders, mirrored
    Readings/S03 Pitney Bowes.pdf      readings linked from the calendar, prefixed by session
    Assignments/Answer Key PS1.pdf     files linked only from an assignment description
    Transcripts/S07 Transcript.txt     (Echo360 add-on)
    Master Takeaways_Product Management.md   (Claude)
```

Naming rules (applied for you):

- **Course folders** use the real course name, without the professor or term code,
  even if you've nicknamed the course in Canvas.
- **`S03 …` prefixes** only when a Canvas calendar event for session 3 links that exact
  file. Never guessed. Each sync says how many files it prefixed per course; the list,
  with the calendar event each one came from, is in `.coursework/changes.log`.
- **Lecture videos** are never downloaded. Files over 30 MB (usually slide decks with
  video in them) are skipped and named in the summary; `coursework sync "<course>" --max-mb 0`
  gets them.
- **Rename, move or delete freely.** The sync remembers every file by its Canvas id: it
  won't re-download what you deleted, and a professor's update overwrites your renamed
  copy instead of creating a second one. After moving files, run `coursework verify --fix`.
- **Old versions:** `coursework ignore "<file>" --delete` removes a superseded syllabus
  and stops a re-upload from bringing it back.

## Lecture transcripts (optional add-on)

Echo360 sits behind your UNI + Duo login, so this part can't run unattended. It's kept
separate on purpose: an expired login never blocks the file sync.

```bash
~/cbs-claude-workflows/setup.sh --echo360          # once: installs a headless browser
```

```bash
coursework echo360 login                           # UNI + Duo, then press Enter in the terminal
```

```bash
coursework echo360 setup "Product Management"      # once per course
```

After class:

```bash
coursework echo360 pull
```

`pull` checks the Canvas calendar **before** touching Echo360. If no class has finished
(at least 2 hours ago) since your last transcript, it stops there: no browser, no login.
Pulled Tuesday, asking Wednesday, next class Thursday? It says so and does nothing. If a
class was never recorded, it stops asking about it a day later. `coursework echo360 status`
shows the same check without pulling. The login lasts a few days, and `pull` tells you
when it has expired. Some courses use Zoom and have no Echo360 at all.

## Master Takeaways

`setup.sh` installs the skill. In Claude Code, from your term folder:

> Make the master takeaways for Product Management.

> Add this week's transcripts to the PM takeaways.

You get one living doc per class with a fixed structure (big ideas, concepts explained
from scratch with worked examples, cases, gaps and an update log), updated in place
rather than as a pile of versions. Using the Claude desktop or web app instead? Zip
`skills/master-takeaways/` and upload it as a custom skill in Claude's settings.

---

## Safe by design

- **Read-only.** It never submits, posts or changes anything on Canvas.
- **No student data, even if you're a TA.** Submissions, grades, rosters and
  enrollments are blocked in code (`coursework/canvas.py`), not just unused.
- **No secrets in your Drive.** The token and the Echo360 login live in
  `~/.config/coursework/`; the browser profile lives in `~/Library/Caches/`.
- **Share the tool, not the material.** Course files and transcripts are for your own
  study. Don't commit or post them, and respect sessions a course marks off the record.

## Routing (optional, rarely needed)

By default the professor's Canvas folders are mirrored up to 3 levels deep (`unfiled`
dumps go to the course root). If a professor's layout is a mess, add `routes` to that
course in `.coursework/config.json`, tried in order:

```json
"routes": [
  {"prefix": "Required Reading", "target": "Readings"},
  {"prefix": "depot", "ext": [".pdf"], "target": "Slides"},
  {"name_match": "Section[ _]?2", "target": null}
]
```

`target: null` means never download. Or just ask Claude: "file PM's Required Reading
folder under Readings".

## Not at Columbia?

The one setting: when you `init`, pass your school's Canvas address:

```bash
coursework init --canvas-url https://canvas.yourschool.edu
```

The Echo360 add-on assumes Echo360 is set up as a Canvas tool. If yours has a different
tool id, change `echo360_tool_id` in `.coursework/config.json`.

## Commands

| | |
|---|---|
| `coursework init [folder]` | set up a term folder (token, term, courses) |
| `coursework token` | save or replace your Canvas token |
| `coursework courses [--all]` | your Canvas courses, and which are set up here |
| `coursework add <id> [--as NAME]` | start syncing a course |
| `coursework drop <course>` | stop syncing a course (keeps files) |
| `coursework sync [course…] [--dry-run] [--max-mb N]` | pull new and updated material |
| `coursework verify [--fix]` | confirm nothing's left on Canvas and nothing's missing |
| `coursework next [course…] [--full] [--save]` | prep notes and deadlines for each next class |
| `coursework ignore <file…> [--delete]` | never re-download these |
| `coursework echo360 login\|setup\|status\|pull [--force]` | lecture transcripts |

Problems? See [docs/troubleshooting.md](docs/troubleshooting.md).
