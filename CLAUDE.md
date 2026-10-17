# Working on this repo

This file is for agents changing the code. Agents *using* the tool to sync someone's
courses should follow `skills/coursework-sync/SKILL.md` instead.

- Layout: `bin/coursework` (launcher) → `coursework/cli.py` (commands) →
  `sync.py` (files, linked files, assignments), `canvas.py` (API + guard),
  `naming.py` (every naming rule), `workspace.py` (paths, state, secrets),
  `echo360.py` (add-on; imports Playwright lazily, so the core never needs it).
- Dependencies: `requests` only for the core. Keep it that way.
- **Never widen or remove `FORBIDDEN` / `guard()` in `canvas.py`.** Users include TAs;
  those endpoints return other students' work.
- Secrets live in `~/.config/coursework/`, never in the workspace (which is usually in
  a synced Drive). Nothing user-specific belongs in the repo: no ids, names, paths.
- State files are written atomically (`save_json`). Ledger entries are keyed by Canvas
  file id and store `saved_to` relative to the workspace root, so a whole term folder
  can be moved without breaking anything. Don't store absolute paths.
- Session prefixes (`S03 …`) come only from a calendar event linking that exact file.
  Don't add inference.
- Test against a scratch folder: `coursework init /tmp/x --add <id>`, then `cd /tmp/x`, then
  `sync --dry-run`, `sync`, `verify` (must print VERIFIED), and a second `verify`.
