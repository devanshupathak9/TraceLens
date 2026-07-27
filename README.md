# TraceLens

Two things in one repo:

- **ChatJippity** — a ChatGPT-style chatbot: multi-turn, streaming, conversation history.
- **TraceLens** — the observability around it. An SDK auto-instruments every LLM
  call, ships the metadata to an ingestion service, and a queue-backed worker
  persists it. The app's Dashboard reads it back.

The point of the split: the chat app never knows it is being observed. No call
site in the backend mentions logging, and nothing in the pipeline can slow the
chat down or break it.

---

## Architecture overview

<p align="center">
  <img src="architecture.png" alt="TraceLens Architecture" width="1000">
</p>

The chat path and the observability path share only the database. The chat-api
writes `messages`; the Lambda writes `inference_logs`. Neither writes the
other's table, so a fault anywhere in the pipeline cannot corrupt or delay a
chat turn — the worst case is a missing metric.

The queue is what decouples them: ingestion returns as soon as an event is
accepted, so write rate is independent of request rate, and the database can be
down without ingestion failing.

Ingestion flow, logging strategy, scaling and failure handling in detail:
**`ARCHITECTURE.md`**.

---

## The pieces

| | What it does |
|---|---|
| **`frontend/`** React 18 + TS + Vite | Chat UI and dashboard. SSE streaming with **stop generating**; conversations list/resume/rename/delete with optimistic updates; dashboard shows volume, success rate, latency, tokens, per-model breakdown and 24h throughput. |
| **`backend/`** FastAPI + async SQLAlchemy + Postgres | Auth (Argon2id + JWT), chat turns streaming and non-streaming, cancellation that stores no partial reply, dashboard aggregation. Providers are strategies — `claude-*` → Anthropic, else OpenAI; with no API key it falls back to echo mode, so the whole loop runs without spending anything. |
| **`sdk/`** `tracelens`, zero deps | `init()` monkey-patches the OpenAI and Anthropic clients, so every call is traced with no change at the call site. Records model, provider, latency, tokens, status and redacted previews. Ships from a daemon thread and swallows every error — a dead collector can't take the app down. |
| **`logging-service/`** FastAPI | Validates events and publishes them to SQS. Holds no state, never touches the database. Publish failures are logged and swallowed. |
| **`lambda/`** psycopg2 worker | SQS-triggered, batch size 10. Inserts one `inference_logs` row per record; repeated failures land in a DLQ instead of blocking the queue. Sample events in `lambda/test-events/`. |

---

## Endpoints

### Chat API — all under `/api/v1`

| Method | Path | Auth | Purpose | Notes |
|---|---|:---:|---|---|
| `POST` | `/users/register` | — | Create an account | `201` + JWT · `409` if the email exists |
| `POST` | `/users/login` | — | Exchange credentials for a token | `200` + JWT · `401` on bad credentials |
| `GET` | `/users/me` | ✔ | Resolve the token to a user | Called on boot to validate a stored token |
| `POST` | `/users/logout` | ✔ | Client-side sign-out | JWTs are stateless; nothing to revoke |
| `POST` | `/conversations` | ✔ | Start a conversation | Created lazily on first send |
| `GET` | `/conversations` | ✔ | List the caller's conversations | Ordered by `last_active_at` |
| `GET` | `/conversations/{id}` | ✔ | One conversation with its messages | `404` if not the caller's — never `403` |
| `PATCH` | `/conversations/{id}` | ✔ | Rename | |
| `DELETE` | `/conversations/{id}` | ✔ | Delete | `204`; messages and logs cascade |
| `GET` | `/conversations/{id}/messages` | ✔ | The transcript, oldest first | Used when resuming |
| `POST` | `/conversations/{id}/messages` | ✔ | One chat turn | `502` provider failure · `499` client gone |
| `POST` | `/conversations/{id}/messages/stream` | ✔ | The same turn over SSE | `delta` → `done` \| `error` frames |
| `GET` | `/dashboard` | ✔ | Deployment-wide inference stats | Aggregates only, no user or message ids |
| `GET` | `/health` | — | Liveness | |

### Ingestion service

| Method | Path | Auth | Purpose | Notes |
|---|---|:---:|---|---|
| `POST` | `/api/v1/logs` | — | Accept an event, publish to SQS | `200` on validation · `422` on a bad body |
| `GET` | `/health` | — | Liveness | |

Full request/response reference: `backend/README.md`.

---

## Schema

**users → conversations → messages**, with **inference_logs** hanging off
conversations. Every primary key is a surrogate `integer` `id`.

### `users`

| Column | Type | Key / index | Purpose |
|---|---|---|---|
| `id` | `integer` | **PK** | Identity |
| `name` | `varchar(100)` | | Display name |
| `email` | `varchar(320)` | **unique** `ix_users_email` | Login identity; the index enforces uniqueness and serves the login lookup |
| `password_hash` | `varchar(255)` | | Argon2id hash |
| `created_at` / `updated_at` | `timestamptz` | | Row audit |

### `conversations`

| Column | Type | Key / index | Purpose |
|---|---|---|---|
| `id` | `integer` | **PK** | Identity |
| `user_id` | `integer` | **FK** → `users.id` cascade | Owner; every query is scoped by it |
| `title` | `varchar(200)` | | Sidebar label |
| `model` | `varchar(100)` | | Model for this thread; picks the provider |
| `created_at` | `timestamptz` | | Start time |
| `last_active_at` | `timestamptz` | | Sidebar sort key, bumped every turn |
| | | **index** (`user_id`, `last_active_at`) | Serves the one hot query: this user's threads, newest first |

### `messages`

| Column | Type | Key / index | Purpose |
|---|---|---|---|
| `id` | `integer` | **PK** | Identity |
| `conversation_id` | `integer` | **FK** → `conversations.id` cascade | Parent thread |
| `role` | `varchar(16)` + CHECK | | `user` \| `assistant` |
| `content` | `text` | | The full message — never truncated or redacted |
| `created_at` | `timestamptz` | | Ordering within the thread |
| | | **index** (`conversation_id`, `created_at`) | Loads a transcript in one index scan |

### `inference_logs` — written only by the Lambda

| Column | Type | Key / index | Purpose |
|---|---|---|---|
| `id` | `integer` | **PK** | Identity |
| `conversation_id` | `integer` | **FK** cascade, **index** | Ties a call to its thread |
| `provider` | `varchar(50)` | **index** | `openai` \| `anthropic` |
| `model` | `varchar(100)` | **index** | Per-model breakdown and cost lookup key |
| `prompt_tokens` | `integer` | | Input usage; defaults to 0, never NULL |
| `completion_tokens` | `integer` | | Output usage |
| `total_tokens` | `integer` | CHECK `= prompt + completion` | Guards against an inconsistent row |
| `input_text` / `output_text` | `text` | | 200-char PII-redacted previews, **not** the transcript |
| `latency_ms` | `integer` | | Wall-clock duration of the call |
| `status` | `varchar(16)` + CHECK | | `success` \| `failed` |
| `created_at` | `timestamptz` | **index** | Call time, indexed because every dashboard query is a time-window scan |

**Design decisions:**

- **Messages are the transcript; inference_logs is the observability record.**
  Model, tokens, latency and failures describe the *call*, not the message — so
  a failed call leaves a log row and no message row.
- **`created_at` is call time**, stamped by the SDK and carried through the
  queue — not insert time, which would lag by the queue delay.
- **Cost is never stored.** Prices change; token counts don't. Spend is computed
  at read time, so a rate change needs no backfill.
- Enums are VARCHAR + CHECK (adding a value is a trivial migration); cascade
  deletes live in the database; token counts default to 0, never NULL.

---

## Setup

```bash
docker compose up --build
```

Frontend on :3000, chat API on :8000/docs, ingestion on :8001/health.

Without an API key the chat answers in echo mode, so the loop works with no
spend. Add `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) for real inference, and
`QUEUE_URL` + AWS credentials on the ingestion service for events to reach the
queue.

Running services individually:

```bash
cd backend && ./run_local.sh                # :8000, runs migrations first
cd logging-service && ./run_local.sh        # :8001
cd frontend && npm install && npm run dev   # :5173
```

## Tradeoffs made

- **Auto-instrumentation over explicit wrapping.** Patching the vendor class
  can't be forgotten at a call site; the cost is coupling to the vendor's
  internal module path.
- **Silent by design.** The SDK swallows every transport error, so a
  misconfigured collector looks identical to a working one from the app's side.
  A missing metric beats a failed response, but diagnosis has to start at the
  ingestion logs.
- **A managed queue (SQS) instead of Kafka/Redis Streams.** A DLQ, retries and a
  Lambda trigger with no infrastructure to run, at the price of lock-in and no
  replay of consumed events.
- **At-least-once delivery.** A batch where one record fails is retried whole,
  so already-inserted records are inserted twice. Acceptable for metrics; an
  idempotency key would fix it.
- **The Lambda contract is untyped** — a field renamed in
  `logging-service/schemas.py` must be renamed in `lambda_function.py` too, and
  nothing checks that.
- **Managed platforms, not Kubernetes** — Vercel + Railway + AWS Lambda.

## What I'd improve with more time

- **No tests.** The biggest gap. The pipeline seams — the SDK patch, the event
  contract, the Lambda's SQL — are exactly what a suite should pin down.
- **The ingest endpoint is unauthenticated.** `TRACELENS_API_KEY` exists in
  config but nothing reads it. Fine on a private network, not in the open.
- **Cancelled calls ship no event.** `CancelledError` isn't an `Exception`, so it
  skips the reporting path — tokens are spent but invisible.
- **A new provider client per request**, so each call builds its own connection
  pool. Fine at demo traffic; connection churn under load.
- **Cost tracking is built but hidden** — the backend computes per-model spend,
  the UI doesn't surface it.
- **Not deployed on Kubernetes** — see `ARCHITECTURE.md`.
