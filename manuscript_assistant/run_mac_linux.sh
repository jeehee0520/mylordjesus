#!/usr/bin/env sh
# Installs packages on the first run (and when requirements.txt changes), then opens the app in the browser.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "Python 3.10+ (python3) is required."; exit 1; }
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
  .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt || exit 1
  cp requirements.txt .venv/requirements.installed
fi
exec .venv/bin/python launcher.py
