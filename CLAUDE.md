# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two products in one repo:

- **ChatJippity** — a ChatGPT-style chat app (`frontend/` + `backend/`).
- **TraceLens** — the observability around it: an SDK that auto-instruments the LLM calls (`sdk/`), a service that ingests the events (`logging-service/`), and a worker that persists them (`lambda/`). The chat app's Dashboard reads the result back.

All four Python/TS services are implemented and deployed. `backend/README.md` (full API + schema reference), `sdk/README.md`, and `DEPLOY.md` (Vercel + Render + Supabase + SQS/Lambda topology) are current — read them before changing contracts.

## Commands

There is **no test runner, linter, or formatter anywhere in this repo**. `npm run typecheck` is the only automated check that exists.

```bash
# frontend/ (Vite dev server on :5173, proxies /api → localhost:8000)
npm install && npm run dev
npm run typecheck          # tsc --noEmit — strict, plus noUnusedLocals/noUnusedParameters
npm run build              # tsc -b && vite build

# backend/ — venv + deps + alembic upgrade head + uvicorn --reload on :8000
./run_local.sh             # needs backend/.env (copies .env.example and exits on first run)
alembic revision --autogenerate -m "..."   # after editing models.py
alembic upgrade head -x db_url=postgresql+asyncpg://...   # override the URL ad hoc

# logging-service/ — uvicorn on :8001, needs its own .env (QUEUE_URL + AWS keys)
./run_local.sh

# whole stack: postgres + migrate job + chat-api + logging-service + frontend
docker compose up --build  # frontend :3000, chat-api :8000/docs, logging :8001/health

# lambda/ — deployed by hand: build the zip, upload it in the AWS console
./build.sh                 # ARCH=arm64 for a Graviton function
```

Without `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, chat falls back to **echo mode** (`(echo) <your message>`), so the full loop is testable with no key and no spend — but no inference events are shipped.

## The observability pipeline

This is the part that spans the most files:

```
backend LLM call → tracelens monkey-patch → daemon-thread POST /api/v1/logs
  → logging-service bus.publish_event → SQS → AWS Lambda
  → INSERT into inference_logs → backend GET /api/v1/dashboard reads it back
```

**SQS is the only sink.** The logging service has no local write path — with
`QUEUE_URL` unset it accepts and logs events, then drops them, so a local stack
without a queue produces no `inference_logs` rows at all (the startup line says
`NO QUEUE_URL SET`). See `logging-service/README.md`.

Load-bearing details:

- **The backend never writes `inference_logs`.** `chat_service.py` only writes `messages`. If a row is missing, the bug is in the SDK, the logging service, or the Lambda — not in the chat path.
- **`sdk/tracelens/__init__.py` patches vendor classes at `init()`** (`openai …Completions.create`, `anthropic …Messages.create`, sync + async). Call sites stay unmodified. `tracelens.set_meta(conversation_id=…)` is a contextvar, so the conversation id rides along without touching any call signature.
- **Streaming is the exception the patch can't handle** — `create(stream=True)` returns an iterator before any token exists, so the patch passes it straight through and `providers.py` calls `tracelens.record()` itself once the stream ends (`_record_stream`). That is also where token counts arrive: OpenAI needs `stream_options={"include_usage": True}`; Anthropic carries usage on the final message. **A new streaming provider that forgets `_record_stream` silently logs nothing.**
- **Nothing in this pipeline may break or slow the app.** `transport.py` fires from a daemon thread and swallows every error; `bus.publish_event` swallows storage failures after the SDK already got its 200.
- **Only 200-char PII-redacted previews leave the process** (`_preview` in the SDK). `inference_logs.input_text/output_text` are debugging previews, *not* the transcript — a failed call has a log row and no message row.
- **`lambda/` is deployed only to AWS.** Nothing in the repo imports it at runtime; the logging service reaches it through the queue. Its contract is the JSON event body, so a field renamed in `logging-service/schemas.py` must be renamed in `lambda_function.py` too — nothing type-checks that seam.

## Backend (`backend/`, the `chat-api` service)

Routers are thin: parse with Pydantic, delegate, translate service exceptions (`EmailAlreadyRegistered`, `ConversationNotFound`, `LLMCallFailed`, `ClientDisconnected`) into status codes. Services own the logic and never import FastAPI concepts beyond `Request`. All routes live under `settings.api_prefix` (`/api/v1`).

- **Two database session paths.** `get_session` (the FastAPI dependency) commits on return; the SSE endpoint must **not** use it — a `StreamingResponse` body runs after the handler returns, so the request-scoped session would pin a pooled connection for the whole generation. `routers/chat.py` opens its own via `session_scope()`.
- **Two database URLs.** `DATABASE_URL` (runtime, `postgresql+asyncpg://`) vs `DATABASE_URL_DIRECT` (migrations/DDL — Supabase's pooler can't hold advisory locks). `Settings.migration_url` picks between them and `alembic/env.py` reads it. Set `DB_TRANSACTION_POOLER=true` only behind a transaction-mode pooler (port 6543): it switches to `NullPool` and `statement_cache_size=0`, without which asyncpg raises `prepared statement "__asyncpg_stmt_N__" already exists`.
- **Migrations never run at startup** — replicas would race the migration lock. Compose has a one-shot `migrate` job; `run_local.sh` runs `alembic upgrade head` before uvicorn.
- **Cancellation is implemented twice.** Streaming: the client's disconnect throws `CancelledError` into `stream_message`'s generator. Non-streaming: `_complete_or_cancel` races the provider call against a `request.is_disconnected()` poller. Both keep the user message and store **no** reply, so a cancelled answer can't reappear on reload.
- **Providers are strategies** (`providers.py`). `provider_for(model, settings)` routes `claude-*` → Anthropic, everything else → OpenAI, and returns `None` when the key is missing (→ echo mode). `chat_service` never names a vendor; adding one is a class plus a line in `provider_for`.
- **Cost is derived, never stored.** `pricing.py` holds USD-per-1M-token rates and `DashboardService` computes spend at read time from the stored token counts, so a rate change doesn't need a backfill. An unlisted model reports `cost_usd: null` and lands in `unpriced_models` rather than counting as $0. Rates were last checked 2026-07-27; Claude Sonnet 5 leaves introductory pricing on 2026-09-01.
- **Ownership checks are 404, never 403** — a 403 would confirm the id exists. Every conversation query is scoped by `user_id` in `ConversationService`.
- **Schema conventions** (`models.py`, `database.py`): explicit constraint `NAMING_CONVENTION` (settled before the first migration — changing it means renaming every existing constraint); enums are VARCHAR + CHECK, not native Postgres enums; cascade deletes live in the DB (`ON DELETE CASCADE` + `passive_deletes`); token counts default to 0, never NULL.
- Errors must always render as `{"detail": …}` (string or FastAPI validation list) — including the catch-all 500 handler — because `frontend/src/api/client.ts` parses exactly that shape.

## Frontend (`frontend/`)

React 18 + TS + Vite, no state library, path alias `@/` → `src/`. `AuthProvider` wraps everything and validates the stored token via `/users/me` before rendering (the `initialising` flag prevents a login-screen flash); `ChatProvider` mounts only once a user exists. `App.tsx` toggles between the chat view and the Dashboard.

- **The bearer token lives outside React** (`api/client.ts`, a module-level variable mirrored to `localStorage`) so `api/` modules never import the auth context — that would be a cycle. A global 401 handler registered by `AuthContext` drops the user to sign-in; auth endpoints pass `skipAuthRedirect: true`.
- **`api/` is the backend contract.** `client.ts` defaults `BASE_URL` to `/api/v1` — the dev proxy and nginx both forward `/api` to the chat-api, so paths in `auth.ts`/`conversations.ts`/`chat.ts` are `/users/*`, `/conversations*`, `/dashboard`. Keep these in lockstep with the routers. (Note `frontend/.env.example` suggests `VITE_API_BASE_URL=/api`, which is stale — leaving it unset is correct.)
- **Streaming** (`api/chat.ts`): raw `fetch`, not `request()`, because it consumes an SSE body and needs an `AbortSignal` for "stop generating" — `EventSource` can't send an `Authorization` header, hence the hand-rolled parser in `lib/sse.ts`. Frames are `event: delta` `{text}`, one `event: done` `{user_message, assistant_message}`, or `event: error` `{detail}`. Releasing the reader in `finally` is what tears the connection down and signals the backend to stop.
- **`ChatContext.submitMessage`** accumulates deltas into a local `let` (not state — two deltas can land in one tick), patches an assistant placeholder in place, then swaps both optimistic messages for the server's stored pair on `done`. On abort it keeps whatever streamed (status `cancelled`) or drops the empty bubble.
- **Optimistic patterns to preserve:** conversations are created lazily on first send (an abandoned "New chat" leaves no row); delete/rename apply immediately and roll back from a snapshot on error; a monotonic `loadToken` ref discards stale history fetches when clicking quickly through the sidebar.
- **`lib/storage.ts`** guards every `localStorage` access (Safari private mode throws); losing storage degrades to "signed out on reload". Keys: `chatjippity.token`, `chatjippity.theme`. There is **no guest/device-id flow** — it was removed.
- SSE needs proxy buffering off end to end: `X-Accel-Buffering: no` from the backend, `proxy_buffering off` in `nginx.conf`.

## Repo-wide gotchas

- **`backend/Dockerfile` must be built from the repo root** (`docker build -f backend/Dockerfile .`) because it installs `-e ../sdk`; Render is configured with only a Dockerfile path for this reason. `logging-service/Dockerfile` is self-contained and builds from its own directory.
- The logging service binds `::`, not `0.0.0.0` — the target PaaS private network is IPv6-only, and the SDK swallows connection errors, so an IPv4-only listener loses events with nothing in any log.
- The Lambda uses plain `psycopg2` + `postgresql://` (it strips `+asyncpg` itself); its zip must be built with `--platform manylinux2014_*`, or it fails at import with `No module named 'psycopg2._psycopg'`.
- `routers/conversations.py` exports `converstation_router` (typo, imported under that name in `main.py`) and declares paths as `""` rather than `"/"` to avoid redirects.
