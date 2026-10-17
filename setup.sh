#!/usr/bin/env bash
# One-time setup. Safe to re-run (e.g. after `git pull`).
#   ./setup.sh            Canvas sync + the two Claude skills
#   ./setup.sh --echo360  also the Echo360 transcripts add-on (installs a browser)
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"

echo "1/3  Python package: requests"
pip_install() {  # --user first; Homebrew Pythons refuse that unless told it's fine
  python3 -m pip install --quiet --user -r "$1" 2>/dev/null \
    || python3 -m pip install --quiet --user --break-system-packages -r "$1" 2>/dev/null \
    || python3 -m pip install --quiet -r "$1"
}
python3 -c "import requests" 2>/dev/null || pip_install "$REPO/requirements.txt"

echo "2/3  The \`coursework\` command"
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO/bin/coursework" "$HOME/.local/bin/coursework"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) echo "     ok: run \`coursework\` from anywhere" ;;
  *) echo "     Add this line to ~/.zshrc, then open a new terminal:"
     echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
     echo "     (until then, use the full path: $REPO/bin/coursework)" ;;
esac

echo "3/3  Claude Code skills -> ~/.claude/skills/"
for s in coursework-sync master-takeaways; do
  mkdir -p "$HOME/.claude/skills/$s"
  sed "s|{{REPO}}|$REPO|g" "$REPO/skills/$s/SKILL.md" > "$HOME/.claude/skills/$s/SKILL.md"
  echo "     installed $s"
done

if [[ "${1:-}" == "--echo360" ]]; then
  echo "+    Echo360 add-on: Playwright + Chromium (~150 MB, outside your Drive)"
  pip_install "$REPO/requirements-echo360.txt"
  python3 -m playwright install chromium
fi

echo
echo "Done. Next, in the folder you want your courses in:"
echo "  cd \"<your term folder>\" && coursework init"
