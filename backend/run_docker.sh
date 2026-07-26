#!/usr/bin/env bash
# Build the image and run it with the env from .env.
# Migrations are not run in the container — run ./run_local.sh (or
# `alembic upgrade head`) once first so the schema exists.
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo ".env not found — copy .env.example and fill in DATABASE_URL and OPENAI_API_KEY first."
    exit 1
fi

docker build -t chatjippity-api .
docker run --rm -p 8000:8000 --env-file .env chatjippity-api
