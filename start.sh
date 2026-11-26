#!/usr/bin/env bash
# Start blackbook on Linux and macOS. The first start sets everything up inside this folder.
set -u
cd "$(dirname "$0")" || exit 1

fail() {
    echo
    echo "blackbook could not start: $1"
    echo "Press Enter to close this window."
    read -r _
    exit 1
}

if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    fail "Python 3 is missing. Install it with your package manager (package python3), then start again."
fi

if [ ! -x .venv/bin/blackbook ]; then
    echo "First start: setting up blackbook inside this folder. This takes a few minutes and needs internet."
fi
"$PY" bootstrap.py --if-needed || fail "the setup failed, see the messages above."

.venv/bin/blackbook "$@" || fail "see the messages above."
