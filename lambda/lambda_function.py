import json
import os
import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/chatjippity",
).replace("+asyncpg", "")


def lambda_handler(event: dict, context=None) -> dict:
    records = event.get("Records")
    if records is None:
        return _store(event)
    for record in records:
        _store(json.loads(record["body"]))
    return {"statusCode": 200, "body": f"stored {len(records)}"}


def _store(event: dict) -> dict:
    print("Event received:", event)

    conversation_id = event.get("conversation_id")
    print(f"conversation_id: {conversation_id}")

    model = event.get("model")
    provider = event.get("provider")
    latency_ms = event.get("latency_ms")
    prompt_tokens = int(event.get("prompt_tokens") or 0)
    completion_tokens = int(event.get("completion_tokens") or 0)
    # Previews, already truncated + PII-redacted by the SDK. Columns are NOT NULL,
    # so an event without them stores an empty string rather than failing.
    input_text = event.get("input_text") or ""
    output_text = event.get("output_text") or ""

    if conversation_id is None or model is None or latency_ms is None:
        print("skipped: missing conversation_id, model or latency_ms")
        return {"statusCode": 400, "body": "missing conversation_id, model or latency_ms"}

    connection = psycopg2.connect(DATABASE_URL)
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO inference_logs
                    (conversation_id, provider, model, prompt_tokens,
                     completion_tokens, total_tokens, latency_ms, status,
                     input_text, output_text)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(conversation_id),
                    provider or "openai",
                    str(model),
                    prompt_tokens,
                    completion_tokens,
                    prompt_tokens + completion_tokens,
                    int(latency_ms),
                    event.get("status", "success"),
                    input_text,
                    output_text,
                ),
            )
    finally:
        connection.close()

    return {"statusCode": 200, "body": "stored"}
