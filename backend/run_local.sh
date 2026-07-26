#!/usr/bin/env bash
# Run the API locally: venv + deps + migrations + uvicorn with reload.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit DATABASE_URL, DATABASE_URL_DIRECT and OPENAI_API_KEY, then rerun."
    exit 1
fi

# First run: no migration files yet, so generate the initial one.
if ! ls alembic/versions/*.py >/dev/null 2>&1; then
    alembic revision --autogenerate -m "initial schema"
fi
alembic upgrade head

uvicorn main:app --reload --port 8000
