#!/usr/bin/env sh
# 처음 한 번 패키지를 설치하고, 이후에는 바로 실행합니다.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/streamlit run app.py
