# Set up with Claude

**For you:** put this file in an empty folder where you want your courses (for example
`My Drive/School/B-term`). Open that folder in the Claude desktop app's **Code** tab and
say:

> Set up my courses using "Set up with Claude.md".

Claude will ask you a few things along the way. It takes about 10 minutes. You'll need
your Columbia login for CourseWorks.

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
   (Step 3). If they paste it in the chat anyway, don't repeat it or use it. Tell them to
   delete that token in Canvas (Account → Settings → Approved Integrations) and make a new one.
2. **Ask before** adding courses, before the first real download, and before editing any
   file outside this folder and `~/cbs-claude-workflows` (for example `~/.zshrc`).
3. **Never delete anything**, and never request student data. The tool blocks grades,
   submissions and rosters in code. Don't work around that, even for courses where the
   user is a TA.
4. Only say something worked once you've checked it: `coursework verify` must print `VERIFIED`.
5. Skip Echo360 (lecture transcripts) entirely during this setup. Step 8 mentions it.

### Step 1: Check the computer

```bash
python3 --version && git --version
```

- Python must be 3.9 or newer. On a Mac, if either command is missing, run
  `xcode-select --install`. The user must click **Install** in the window that appears,
  so tell them, then wait for them to say it's done and check again.
- This guide assumes macOS or Linux. On Windows, stop and tell the user it isn't
  supported yet.

### Step 2: Get the tool

If `~/cbs-claude-workflows` already exists, update it:

```bash
git -C ~/cbs-claude-workflows pull --ff-only
```

Otherwise:

```bash
git clone https://github.com/hcayssials/cbs-claude-workflows.git ~/cbs-claude-workflows
```

If the clone fails with an authentication or "not found" error, the repository is
private and this user hasn't been given access. Stop and tell them to ask the person who
sent them this file to add their GitHub username, or to send them the tool as a zip. If
they have a zip, unzip it so the files sit at `~/cbs-claude-workflows/README.md`, etc.

Then install it:

```bash
~/cbs-claude-workflows/setup.sh
```

This installs one Python package (`requests`), puts a `coursework` command in
`~/.local/bin`, and installs two Claude skills in `~/.claude/skills/`.

- If it prints a line telling them to add `~/.local/bin` to their PATH, **ask** whether you
  may add it to `~/.zshrc`. Either way, for the rest of this setup call the tool by its
  full path: `~/cbs-claude-workflows/bin/coursework`. Below, `coursework` means that path.
- If `pip` fails with "externally-managed-environment", run
  `python3 -m pip install --user --break-system-packages requests` and carry on.

### Step 3: The Canvas token (the user does this, not you)

Explain to the user, in roughly these words:

> To read your courses, the tool needs a Canvas access token, a kind of password just for
> this tool. In CourseWorks: click **Account** (top left) → **Settings** → scroll down to
> **Approved Integrations** → **+ New Access Token**. For Purpose, write "coursework sync".
> Leave the expiry blank or set it to the end of term, then click **Generate Token** and
> copy it. Don't paste it here in the chat. I'll open a terminal for you to paste it into.

Then open a terminal tab for them, in this folder, running:

```bash
~/cbs-claude-workflows/bin/coursework token
```

(Use the app's run-in-terminal tool if you have one. Otherwise ask them to open the
Terminal app, paste that command, and press Enter.) It asks them to paste the token,
which isn't shown as they paste, and press Enter. It saves it to
`~/.config/coursework/canvas_token`, outside their Drive.

Wait for them to say it's done. To check it worked, run Step 4. A `401` error means the
token didn't save or was copied incompletely: repeat this step.

### Step 4: Find their courses

From this folder:

```bash
coursework init
```

This creates the hidden `.coursework/` folder, detects the current term, and prints the
user's courses for that term with their role in each. Because you aren't at an
interactive terminal, it won't add any courses itself. That's intended.

Show the user the list as a short table (course name and role) and ask which to sync.
Suggest "all the ones where you're a student". Point out any **TA** courses: syncing
them is allowed (only course materials are read), but most TAs don't want them, so ask.

If the term looks wrong (for example last term's courses), ask which term they mean and
run `coursework init --term "Spring 2027"` (using the term name exactly as Canvas lists it).

### Step 5: Add the courses

```bash
coursework add <id> <id> …
```

Folder names default to the official course name without the professor or term code
("Product Management"). If the user wants a shorter name for one, use
`coursework add <id> --as "PM"`, one course per command.

### Step 6: Preview, then download

```bash
coursework sync --dry-run
```

Summarise per course: how many files would land, and anything in the notes. Then ask:
"Ready to download?"

- `TOO-LARGE`: files over 30 MB are skipped (usually slide decks with video). Name them
  and ask whether they want them; if yes, `coursework sync "<course>" --max-mb 0` after
  the main sync.
- `PREFIXED`: some files will be named `S03 …` because the Canvas calendar assigns them
  to session 3. Mention it in one line.
- `LOCKED`: a professor linked a file students can't download. Nothing to do.

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
- That nothing else was added to their folder, except a hidden `.coursework/` folder they
  should leave alone, and this file.
- **What they can say from now on.** The skills load in new Claude sessions, so they work
  from their next conversation:
  - "Sync my classes": pulls anything new (safe any time).
  - "What do I need for my next class?": readings, prep notes and deadlines.
  - "Make the master takeaways for <course>": a study doc for the class.
- Optional later: lecture transcripts from Echo360 (needs their UNI + Duo). Say
  "set up Echo360 transcripts" another time.

Finally, ask whether they want to keep this file. It's also in `~/cbs-claude-workflows`,
so it's safe to delete if they'd like the folder clean.

### If something goes wrong

| Symptom | Fix |
|---|---|
| `command not found: coursework` | Use the full path `~/cbs-claude-workflows/bin/coursework` |
| `Canvas said 401` | The token is wrong or expired: Step 3 again |
| `No module named requests` | `python3 -m pip install --user requests` (add `--break-system-packages` if pip refuses) |
| `Not inside a coursework folder` | You're running from the wrong place: `cd` into this folder, or add `--root "<this folder>"` |
| A course is missing from the list | It may be under another term: `coursework courses --all` |
| Anything else | `~/cbs-claude-workflows/docs/troubleshooting.md` |
