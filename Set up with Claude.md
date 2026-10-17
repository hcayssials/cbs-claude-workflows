# Set up with Claude

**For you:** put this file in an empty folder where you want your courses (for example
`My Drive/School/B-term`). Open that folder in the Claude desktop app's **Code** tab and
say:

> Set up my courses using "Set up with Claude.md".

Claude will ask you a few things along the way. It takes about 10 minutes, on a Mac or
a Windows PC. You'll need your Columbia login for CourseWorks.

---

## Instructions for Claude

You are setting up the `coursework` tool so this folder becomes the user's **term folder**:
one folder per Canvas course, kept in sync. Follow the steps in order. Talk to the user in
plain language; assume they have never used a terminal. Don't show them raw command output
unless something fails; summarise it.

**This folder** (the one containing this file) is the term folder. The tool's code goes in
`~/cbs-claude-workflows`, **never** in this folder: the user wants nothing here but their
course folders.

### Rules, for the whole setup

1. **Never handle the Canvas token in the chat.** It gives full access to the user's
   Canvas account, and chat history is stored. The user pastes it into a terminal
   (Step 3); you never print, read or repeat it. If they paste it in the chat anyway, don't repeat it or use it. Tell them to
   delete that token in Canvas (Account → Settings → Approved Integrations) and make a new one.
2. **Ask before** adding courses, before the first real download, and before editing any
   file outside this folder and `~/cbs-claude-workflows` (for example `~/.zshrc`).
3. **Never delete anything**, and never request student data. The tool blocks grades,
   submissions and rosters in code. Don't work around that, even for courses where the
   user is a TA.
4. Only say something worked once you've checked it: `coursework verify` must print `VERIFIED`.
5. Skip Echo360 (lecture transcripts) entirely during this setup. Step 8 mentions it.

### Step 1: Check the computer

Works on **Mac and Windows** (and Linux). Find out which, then check Python 3.9+ and git.

**Mac:**

```bash
python3 --version && git --version
```

If either is missing, run `xcode-select --install`. The user must click **Install** in the
window that appears, so tell them, then wait for them to say it's done and check again.

**Windows** (Claude Code runs commands in Git Bash, so git is already there):

```bash
py --version || python --version
```

- If neither prints a version (or `python` opens the Microsoft Store), Python isn't
  installed. Ask the user to install it: either let you run
  `winget install -e --id Python.Python.3.12`, or download it from python.org and tick
  **"Add python.exe to PATH"** on the first installer screen. Then check again.
- Below, `PY` means whichever worked: `py`, `python` or (Mac) `python3`.
- Suggest a term folder near the top of their drive (e.g. `G:\My Drive\School\B-term`).
  Windows limits a file's full path to 260 characters. The tool shortens long file
  names to fit, but deep folders leave less room.

### Step 2: Get the tool

If `~/cbs-claude-workflows` already exists, update it:

```bash
git -C ~/cbs-claude-workflows pull --ff-only
```

Otherwise:

```bash
git clone https://github.com/hcayssials/cbs-claude-workflows.git ~/cbs-claude-workflows
```

Then install it. Before you run it, tell the user: *"I'm about to run the tool's
installer. Claude may ask you to approve this, because it runs code that was just
downloaded. That's expected: please approve it."*

```bash
PY ~/cbs-claude-workflows/install.py
```

This installs one Python package (`requests`), a `coursework` command, and three Claude
skills in `~/.claude/skills/`. It ends by printing **the exact command for this
computer**, also saved in `~/.config/coursework/command.txt`. For the rest of this setup,
`coursework` means that command: use it as printed (it works in Git Bash on Windows too).

If the installer is blocked and the user doesn't approve it, stop: nothing else works
without it.

### Step 3: The Canvas token (the user pastes it, you never see it)

Explain to the user, in roughly these words:

> To read your courses, the tool needs a Canvas access token, a kind of password just for
> this tool. In CourseWorks: click **Account** (top left) → **Settings** → scroll down to
> **Approved Integrations** → **+ New Access Token**. For Purpose, write "coursework sync".
> Leave the expiry blank or set it to the end of term, then click **Generate Token** and
> **copy** it. Don't paste it here in the chat. I'll open a terminal for you: paste it
> there and press Enter. Nothing appears as you paste; that's normal.

Open a terminal tab for them, in this folder, running the token command. Use the app's
run-in-terminal tool if you have one; otherwise ask them to open Terminal (Mac) or
PowerShell (Windows) and paste the command.

- Mac / Linux, or Git Bash on Windows: `~/.local/bin/coursework token`
- Windows PowerShell: `& "$env:USERPROFILE\.local\bin\coursework.cmd" token`

It strips invisible characters a copy can pick up, checks the token with Canvas, and,
if something's wrong (nothing pasted, partial copy, deleted token), says so and **asks
again**, up to three times. Once it prints `Token saved … accepted by Canvas`, go on.
It's stored in `~/.config/coursework/canvas_token`, outside their Drive.

If pasting keeps failing in that terminal, use the backup: ask them to copy the token
again and say "copied", then run `coursework token --from-clipboard` yourself. It reads
the clipboard without printing anything, checks it, saves it and clears the clipboard.

### Step 4: Find their courses

From this folder:

```bash
coursework init
```

This creates the hidden `.coursework/` folder, detects the current term, and prints the
user's courses for that term with their role in each. Because you aren't at an
interactive terminal, it won't add any courses itself. That's intended.

Show the user the list as a short table (course name, role, and the **when** column:
A-term, B-term, Full Term or Block Week, worked out from the class dates) and ask which
to sync. Suggest "all the ones where you're a student". Point out any **TA** courses:
syncing them is allowed (only course materials are read), but most TAs don't want them,
so ask.

If the term looks wrong (for example last term's courses), ask which term they mean and
run `coursework init --term "Spring 2027"` (using the term name exactly as Canvas lists it).

Ask about file size in the same message: *"Files over 30 MB (mostly slide decks with video)
are skipped and listed so you can grab them later. Keep 30 MB, or change it?"* If they
choose another limit, save it for the folder so every later sync and check uses it:
`coursework init --max-mb <N>` (`0` means no limit). Never pass `--max-mb` to `sync`
for this: that applies to one run only, and `verify` would then report the skipped files
as missing.

### Step 5: Folder layout, then add the courses

Ask two things in one message, showing the folder names they'd get:

1. **Group by term?** *"Want your courses grouped into A-term / B-term / Full Term /
   Block Week folders, or one flat folder per course?"* If grouped:
   `coursework init --group-by-term`. A course whose *when* is `?` needs one from them:
   add it with `--when "A-term"` (or B-term, Full Term, Block Week).
2. **Shorter names?** Folder names default to the official course name without the
   professor or term code, which can be long ("The U.S. Healthcare System_ Structure
   and Strategies"). Offer short names (e.g. "US Healthcare", "PM", "TIP") and use the
   ones they want.

Then add the courses:

```bash
coursework add <id> <id> …
```

For a course they want renamed: `coursework add <id> --as "US Healthcare"`, one course
per command. (With grouping on, the term folder is added for you.)

Tell them they can rename or regroup any time by asking you. It runs
`coursework rename "<course>" "<new name>"` so nothing re-downloads. If they rename a
folder in Finder or Drive themselves, that's fine too: the next `verify` notices and the
same command reconnects it.

### Step 6: Preview, then download

```bash
coursework sync --dry-run
```

Summarise per course: how many files would land, and anything in the notes. Then ask:
"Ready to download?"

- `TOO-LARGE`: files over the cap are skipped. Name them (or count them, if there are
  many) and ask whether they want any; if yes, `coursework sync "<course>" --max-mb 0`
  after the main sync. That's the one time a one-run `--max-mb` is right.
- `PREFIXED`: some files will be named `S03 …` because the Canvas calendar assigns them
  to session 3. Mention it in one line.
- `LOCKED`: a professor linked a file students can't download. Nothing to do.
- `LINKS`: readings that are links, not files, so they can't be downloaded. Always
  mention these, with the count per course, and say **Harvard coursepack** cases first:
  those need buying or downloading by hand from the Harvard link on Canvas. Every one is
  listed by session in that course's `Canvas_Links.md`, and gets a ✓ once the user saves
  the PDF into the course folder. Some courses have long *recommended* reading lists of
  web articles; say so rather than presenting them as missing.

On their go-ahead:

```bash
coursework sync
```

Large courses can take several minutes. Run it in the background if your tools allow,
and give a short progress update now and then.

### Step 7: Verify

```bash
coursework verify
```

It must end with `VERIFIED`. If it doesn't, read what it says (the notes explain each
case) and fix it, or explain it to the user. A pending `Canvas_Assignments.md` right
after a sync usually means a professor edited a description a moment ago: run
`coursework sync` once more.

### Step 8: Tell the user what they have

Keep it short:

- What landed: the course folders, roughly how many files each, and that each course has
  `Canvas_Assignments.md` with every assignment description.
- **What didn't, and why:** files over the cap (named), and readings that are only links
  (count per course, Harvard coursepack cases first). Point to `Canvas_Links.md`.
- That nothing else was added to their folder, except a hidden `.coursework/` folder they
  should leave alone, and this file.
- **What they can say from now on.** The skills load in new Claude sessions, so they work
  from their next conversation:
  - "Sync my classes": pulls anything new (safe any time).
  - "What do I need for my next class?": readings, prep notes and deadlines.
  - "Make the master takeaways for <course>": a study doc for the class.
  - "Audit my draft": checks a paper or deck before they submit it.
- Optional later: lecture transcripts from Echo360 (needs their UNI + Duo). Say
  "set up Echo360 transcripts" another time.

Finally, ask whether they want to keep this file. It's also in `~/cbs-claude-workflows`,
so it's safe to delete if they'd like the folder clean.

### If something goes wrong

| Symptom | Fix |
|---|---|
| `command not found: coursework` | Use the command in `~/.config/coursework/command.txt` |
| Windows: `python` opens the Microsoft Store | Python isn't installed: Step 1 |
| Windows: `PATH-TOO-LONG` note | The term folder is too deep: `coursework rename` the course to something shorter, or move the term folder nearer the top of the drive |
| `Canvas said 401` | The token is wrong or expired: Step 3 again |
| `verify` lists files as WOULD-ADD after a deliberate small cap | The cap wasn't saved: `coursework init --max-mb <N>`, then `verify` again |
| "Did it get everything?" | Yes, within the cap. Besides the Files tab, sync scans the Syllabus page, calendar events, pages, modules, announcements and assignment descriptions for linked files. It skips decorative images and duplicate uploads. `LOCKED` notes are files students can't download. |
| `No module named requests` | `python3 -m pip install --user requests` (add `--break-system-packages` if pip refuses) |
| `Not inside a coursework folder` | You're running from the wrong place: `cd` into this folder, or add `--root "<this folder>"` |
| A course is missing from the list | It may be under another term: `coursework courses --all` |
| Anything else | `~/cbs-claude-workflows/docs/troubleshooting.md` |
