#!/usr/bin/env bash
# Mac/Linux shortcut for install.py (which also works on Windows: `py install.py`).
exec python3 "$(cd "$(dirname "$0")" && pwd)/install.py" "$@"
