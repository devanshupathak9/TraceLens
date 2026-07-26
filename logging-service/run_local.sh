#!/usr/bin/env bash
# Run the logging service locally: venv + deps + uvicorn on port 8001.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

# The lambda writes inference_logs into the same DB the backend uses.
if [ -f ../backend/.env ]; then
    set -a
    source ../backend/.env
    set +a
fi

uvicorn main:app --reload --port 8001
