# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

TraceLens is a lightweight LLM observability platform: a ChatGPT-style chat app whose LLM calls are instrumented by an SDK, with a separate service ingesting the resulting logs for analytics.

**Current state (important):** the repo is scaffolded but only partially built. The **frontend** (`frontend/`) is fully implemented. The **backend**, **logging-service**, and **sdk** exist as directory trees of *empty* Python files — the intended module layout is in place, but there is no implementation yet. Their contract is visible in three places: the frontend's `src/api/` layer (the chat API the backend must serve), `docker-compose.yml` service names, and each service's directory structure. When implementing a Python service, treat the frontend API modules as the source of truth for request/response shapes.

## The four services

- **frontend/** — React 18 + TypeScript + Vite SPA. Chat UI with auth, conversation management, and SSE streaming. Served by nginx in production.
- **backend/** (`chat-api`) — FastAPI chat API: auth, conversations, and streaming chat completions via pluggable LLM providers. Uses SQLAlchemy + Alembic. *Not yet implemented.*
- **logging-service/** — FastAPI service that ingests trace/log events over an internal event bus (`app/bus/`) and persists them. *Not yet implemented.*
- **sdk/** (`tracelens` Python package) — auto-instrumentation SDK that wraps LLM clients (e.g. OpenAI), redacts sensitive fields, and ships events to the logging-service via `transport.py`. *Not yet implemented.*

Data flow: SDK instruments the backend's LLM calls → emits events → logging-service ingests them. The backend streams chat responses to the frontend over SSE.

## Commands

All frontend commands run from `frontend/`:

```bash
npm install          # install deps
npm run dev          # Vite dev server on :5173, proxies /api → localhost:8000
npm run build        # tsc -b && vite build
npm run typecheck    # tsc --noEmit  — run this to check TS; there is no separate lint/test setup
npm run preview      # preview the production build
```

There is no test runner, linter, or formatter wired into the frontend yet. `npm run typecheck` is the only automated check. TypeScript is strict (`strict`, `noUnusedLocals`, `noUnusedParameters`).

Python services are packaged with `requirements.txt` (all currently empty). Once implemented, expect `pytest` (test dirs exist at `backend/tests/`, `logging-service/tests/`, `sdk/tests/`) and Alembic migrations under `backend/alembic/`.

`docker-compose.yml` is currently empty; the intended topology (from `nginx.conf`) routes the frontend's `/api/` to the `chat-api` service on port 8000.

## Frontend architecture

Path alias: `@/` → `src/` (configured in both `vite.config.ts` and `tsconfig.json`).

**Two-layer state via React Context, no external state library:**

- `AuthProvider` (`context/AuthContext.tsx`) — wraps the whole app in `App.tsx`. Owns the `User` and the login/register/guest/upgrade/logout actions. On boot it validates the stored token via `/auth/me` before rendering (the `initialising` flag prevents a login-screen flash).
- `ChatProvider` (`context/ChatContext.tsx`) — mounted only once a user exists. Owns conversations, the active conversation's messages, and all send/cancel/rename/delete logic.

**Auth token handling is deliberately outside React** (`api/client.ts`): the bearer token lives in a module-level variable (mirrored to `localStorage`) so any `api/` module can call `request()` without importing the auth context — avoiding a context ↔ api cycle. A global 401 handler, registered by `AuthContext`, drops the user to the sign-in screen on any expired-token response. Pass `skipAuthRedirect: true` for auth endpoints that must not trigger this.

**API layer** (`src/api/`): `client.ts` is the shared `fetch` wrapper (adds auth header, normalizes FastAPI `detail` errors into `ApiError`). `auth.ts`, `conversations.ts`, `chat.ts` are thin per-domain wrappers. These modules define the exact backend contract — `/auth/*`, `/conversations`, `/conversations/{id}/messages` — so keep them and the backend in lockstep.

**Streaming chat** is the most subtle part:
- `chat.ts` uses raw `fetch` (not the shared `request()`) because it consumes an SSE stream and needs an `AbortSignal` for "stop generating". The browser's `EventSource` can't send an `Authorization` header, which is why SSE is parsed by hand.
- `lib/sse.ts` is a hand-rolled SSE frame parser (handles CRLF, multi-line `data:`, keepalive comments, trailing frames).
- `chat.ts`'s `toStreamEvent` is intentionally lenient: it accepts named events *or* a `type` discriminator in the payload, tolerates `delta`/`token`/`message` event names, and treats non-JSON frames as raw tokens. This lets the client work against several plausible backend SSE conventions.
- `ChatContext.submitMessage` accumulates deltas into a local `let` (not state) to avoid a same-tick re-render race, patches an assistant placeholder message in place as tokens arrive, and reconciles the local optimistic message id with the server's id on the `done` event.

**Optimistic UI patterns to preserve:** conversations are created lazily on first send (an abandoned "New chat" leaves no empty row); delete/rename update immediately and roll back from a snapshot on server error; a monotonic `loadToken` ref discards stale conversation-history fetches when the user clicks through the sidebar quickly.

**Guest accounts** (`lib/device.ts`): a guest is backed by a random UUID stored in `localStorage` (`getDeviceId`) — explicitly *not* a fingerprint, so it's disposable. The `/auth/guest` endpoint is expected to be idempotent per device id. `logout` intentionally keeps the device id so a returning guest lands back in the same account; `upgradeGuest` converts a guest to a permanent account keeping their conversations.

**Persistence** (`lib/storage.ts`): every `localStorage` access is try/caught because Safari private mode and some webviews throw. Losing storage degrades to "signed out on reload" rather than crashing. Keys: `tracelens.token`, `tracelens.device_id`, `tracelens.theme`.
