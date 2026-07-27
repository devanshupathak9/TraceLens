# TraceLens Logging Service

Ingests inference events from the tracelens SDK and publishes them to SQS.
That's all it does — it holds no state and never touches the database. The AWS
Lambda subscribed to the queue writes the `inference_logs` row.

```
backend (tracelens SDK) ──POST /api/v1/logs──▶ logging-service ──▶ SQS ──▶ Lambda ──▶ Postgres
```

Why a queue in the middle: ingestion stays fast and can't be slowed down by the
database, and a burst of events waits in SQS instead of piling up on the app.

## Endpoints

| Method | Path | |
|---|---|---|
| POST | `/api/v1/logs` | ingest one event |
| GET | `/health` | liveness — `{"status": "ok"}` |

### Input — `POST /api/v1/logs`

```json
{
  "service": "chatjippity-backend",
  "conversation_id": 42,
  "provider": "openai",
  "model": "gpt-4o",
  "input_text": "how do I center a div",
  "output_text": "Use flexbox...",
  "prompt_tokens": 18,
  "completion_tokens": 96,
  "total_tokens": 114,
  "latency_ms": 842,
  "status": "success",
  "error": null,
  "created_at": "2026-07-27T10:15:00Z"
}
```

Only `model` and `latency_ms` are required; everything else has a default (see
`schemas.py`). `input_text` / `output_text` arrive already truncated to 200
chars and PII-redacted by the SDK — no full message content is sent here.

`created_at` is **when the call happened**, stamped by the SDK in UTC and
carried through to `inference_logs.created_at`, so the dashboard buckets calls
by call time rather than by however long the queue took. An event that omits it
gets receipt time instead.

### Output

```json
{ "status": "ok", "received": 1 }
```

Always 200 once the body validates, whether or not the publish to SQS
succeeded. Observability must never break the app being observed, so publish
failures are logged and swallowed rather than returned. A malformed body is a
422 from FastAPI.

## Configuration

| Variable | |
|---|---|
| `QUEUE_URL` | SQS queue to publish to. **Unset = every event is dropped** (logged at startup and per event). |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | credentials for the send-only publisher user |
| `AWS_DEFAULT_REGION` | optional — parsed out of `QUEUE_URL` when unset |
| `PORT` | 8001 |

## Run

```bash
cp .env.example .env   # fill in QUEUE_URL + credentials
./run_local.sh         # venv + deps + uvicorn --reload on :8001

docker build -t tracelens-logging . && docker run -p 8001:8001 --env-file .env tracelens-logging
```

Every step prints to stdout, so `docker logs` / the Render log tail shows the
whole path of an event:

```
[startup] event sink: sqs -> https://sqs.ap-south-1.amazonaws.com/.../tracelens-events
[ingest] chatjippity-backend openai/gpt-4o conversation=42 status=success latency=842ms tokens=18/96/114
[bus] publishing -> {...}
[bus] queued MessageId=4f2c...
```

Binds `::` rather than `0.0.0.0` — the private network it is reached over is
IPv6-only, and the SDK swallows connection errors, so an IPv4-only listener
would lose events with nothing in any log.
