---
name: coursework-sync
description: Sync the user's Canvas (CourseWorks) courses into their term folder and pull Echo360 lecture transcripts, using the `coursework` tool. Use whenever the user asks to sync, download or refresh course files, check for new readings or assignments, add or drop a course, set up a new term folder, or get the latest lecture transcripts. Do NOT use for writing class summaries (that is master-takeaways) or for anything involving grades, submissions or other students.
---

# Coursework sync

The tool is `coursework` (installed at `{{REPO}}/bin/coursework`; if `coursework`
isn't on PATH, call that full path). It works on a **term folder**, recognised by the
hidden `.coursework/` folder inside it, and finds it by walking up from the current
directory. Pass `--root "<folder>"` when you're running from somewhere else.

## Hard rules

1. **Never handle the Canvas token or the Echo360 login yourself.** Both need the user
   at a terminal: ask them to run `coursework token` (paste the token) or
   `coursework echo360 login` (UNI + Duo, **then press Enter** in the terminal, or the
   login isn't saved). Don't ask them to paste a token into the chat.
2. **Preview, then sync, then verify.** Run `coursework sync --dry-run` first and show the
   user what would land, then `coursework sync`, then `coursework verify`. Only call a run
   successful when `verify` prints `VERIFIED`. Never claim a file was downloaded
   without checking it's on disk.
3. **Ask before adding or dropping a course.** New courses appear on Canvas mid-term;
   list them with `coursework courses` and let the user choose.
4. **Never delete course files.** If the user wants an old version gone, run
   `coursework ignore "<path>" --reason "<why>" --delete` (they asked, so it's their call).
   That also keeps a future re-upload from bringing it back.
5. **Don't edit `.coursework/config.json` or `ledger.json` by hand** unless the user asks;
   back both up first if you do.
6. **Never touch student data.** The tool blocks submissions, grades, rosters and
   enrollments in code. Don't work around that, even in courses where the user is a TA.

## Common tasks

| User says | Run |
|---|---|
| "set up my B-term folder" | `cd` there, then `coursework init` (the user pastes the token if asked) |
| "sync my classes" / "anything new?" | `coursework sync --dry-run`, then `coursework sync`, then `coursework verify` |
| "just PM" | `coursework sync "Product Management"` (a partial name works) |
| "add Negotiations" | `coursework courses`, confirm the id, `coursework add <id>` |
| "I dropped X" | `coursework drop "X"` (keeps the files) |
| "get the big slide deck" | `coursework sync "<course>" --max-mb 0` |
| "I moved some files, verify fails" | `coursework verify --fix` |
| "what do I need for Thursday?" / "what's next?" | `coursework next` (or `coursework next pm`). Read it back briefly, then offer: "Want me to save this as Up next.md?" (`--save`) |
| "new transcripts?" | `coursework echo360 pull`. It checks the Canvas calendar first and opens no browser if no class has finished since the last transcript. Only ask the user to log in if `pull` says the login has expired. Don't use `--force` unless they ask. |

## Reading the output

- `note LOCKED`: a professor linked a file that students can't download. Nothing to fix.
- `note TOO-LARGE`: skipped because it's over 30 MB. Name the file and offer `--max-mb 0`.
- `note PREFIXED`: new files were named `S03 …` from the Canvas calendar. Say how many,
  and offer to show the list: `grep PREFIXED .coursework/changes.log | tail -40`.
- `note FLATTENED`: Canvas folders deeper than 3 levels were collapsed. Offer to add a
  `routes` entry for that course (see the README's "Routing" section).
- `note NO-ACCESS` on a course's Files tab: usually a dropped course. Offer `coursework drop`.
- A pending `Canvas_Assignments.md` between two runs usually means the professor
  edited a description. That's real, not a bug: just sync.

## Where things land

```
<term folder>/
  .coursework/                 state (don't edit)
  <Course>/
    Canvas_Assignments.md      every assignment description, rewritten each sync
    Readings/S03 ….pdf         files linked from calendar events and pages
    Assignments/….pdf          files linked only from assignment descriptions
    Transcripts/S07 Transcript.txt
    …professor's own folders, mirrored from the Files tab
```

`S03` prefixes come only from a Canvas calendar event for session 3 that links that
exact file. Never add or "correct" a session number yourself; ask the user.
