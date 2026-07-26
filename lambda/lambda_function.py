"""Persists inference events to Postgres.

Shaped like an AWS Lambda handler so it can be deployed behind a queue later.
For now there is no queue — the logging service imports this module and calls
`lambda_handler` directly, one event per call. Each call opens its own DB
connection, lambda-style.
"""

import os

import psycopg2

# Reuses the backend's DATABASE_URL; psycopg2 wants a plain postgresql:// scheme.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/chatjippity",
).replace("+asyncpg", "")


def lambda_handler(event: dict, context=None) -> dict:
    """Validate an inference event and insert it into inference_logs."""
    conversation_id = event.get("conversation_id")
    model = event.get("model")
    latency_ms = event.get("latency_ms")

    if conversation_id is None or model is None or latency_ms is None:
        return {"statusCode": 400, "body": "missing conversation_id, model or latency_ms"}

    prompt_tokens = int(event.get("prompt_tokens") or 0)
    completion_tokens = int(event.get("completion_tokens") or 0)

    connection = psycopg2.connect(DATABASE_URL)
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO inference_logs
                    (conversation_id, provider, model, prompt_tokens,
                     completion_tokens, total_tokens, latency_ms, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(conversation_id),
                    event.get("provider", "openai"),
                    str(model),
                    prompt_tokens,
                    completion_tokens,
                    prompt_tokens + completion_tokens,
                    int(latency_ms),
                    event.get("status", "success"),
                ),
            )
    finally:
        connection.close()

    return {"statusCode": 200, "body": "stored"}
