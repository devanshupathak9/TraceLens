#!/usr/bin/env bash
# Run the logging service locally: venv + deps + uvicorn on port 8001.
#
# Needs a .env in this directory with QUEUE_URL and AWS credentials — every
# event goes to SQS, so without them ingestion still returns 200 but the events
# are dropped (the startup line says so).
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "warning: no .env here — set QUEUE_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
fi

uvicorn main:app --reload --port 8001
