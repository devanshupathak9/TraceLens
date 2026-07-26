# ChatJippity API

FastAPI backend for ChatJippity, the TraceLens demo chat app: authentication,
conversations, and chat completions, with every LLM call recorded in
`inference_logs`. (TraceLens is the observability SDK that instruments this
backend; ChatJippity is the chat product it observes.)

## Layout

```
backend/
├── main.py                  app factory, middleware, error handlers, /health
├── config.py                settings from env vars / .env
├── database.py              async engine, session factory, get_session dependency
├── models.py                SQLAlchemy models (the schema below)
├── schemas.py               ALL Pydantic request/response validation
├── security.py              password hashing, JWT, get_current_user
├── routers/                 thin HTTP layer — parse, delegate, map errors
│   ├── users.py
│   ├── conversations.py
│   └── chat.py
├── services/                the actual logic, no HTTP in here
│   ├── user_service.py
│   ├── conversation_service.py
│   └── chat_service.py
└── alembic/                 migrations
```

Pattern: **routers validate with Pydantic and translate service exceptions into
HTTP status codes; services own the logic and talk to the database.** Services
raise their own exceptions (`EmailAlreadyRegistered`, `ConversationNotFound`,
`LLMCallFailed`) so they stay usable outside FastAPI.

## Run

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # then edit

alembic revision --autogenerate -m "initial schema"   # first time only
alembic upgrade head

uvicorn main:app --reload --port 8000
```

Interactive docs at http://localhost:8000/docs (disabled in production).

Without `OPENAI_API_KEY` set, chat runs in **echo mode** — the assistant
replies `(echo) <your message>` so the full loop is testable without a key.

## API

All routes are under `/api/v1`. Everything except register/login/health
requires `Authorization: Bearer <token>`.

### Authentication

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/register` | `{name, email, password}` | 201 `{access_token, token_type, user}` |
| POST | `/users/login` | `{email, password}` | `{access_token, token_type, user}` |
| POST | `/users/logout` | — | `{status: "ok"}` |
| GET | `/users/me` | — | `{id, name, email, created_at}` |

- Password: 8–128 chars. Hashed with Argon2id; never stored raw.
- Emails are lowercased on write and lookup, and unique — duplicate registration
  is a 409.
- Login failure is always the same 401, whether the email exists or the
  password is wrong, so account existence can't be probed.
- Tokens are JWTs (`sub` = user id); logout is client-side since JWTs are
  stateless.

### Conversations

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/conversations` | `{title?, model?}` | 201 summary |
| GET | `/conversations` | — | list of summaries, most recently active first |
| GET | `/conversations/{id}` | — | summary + `messages[]` |
| PATCH | `/conversations/{id}` | `{title?}` | updated summary |
| DELETE | `/conversations/{id}` | — | 204 |

Summary shape: `{id, title, model, created_at, last_active_at, message_count}`.

- `title` defaults to "New chat" and is renamed automatically by the first
  message; `model` defaults to the server's `DEFAULT_MODEL`.
- Every query is scoped to the authenticated user — someone else's conversation
  returns 404 (never 403, which would confirm the id exists).
- DELETE cascades to messages and inference logs at the database level.

### Messages (Chat)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/conversations/{id}/messages` | `{content}` | `{user_message, assistant_message}` |
| GET | `/conversations/{id}/messages` | — | transcript, oldest first |

Message shape: `{id, conversation_id, role, content, created_at}`.

One POST is one chat turn: the user message is stored, the LLM is called with
the system prompt plus the last `MAX_CONTEXT_MESSAGES` turns, the reply is
stored, and both come back. Non-streaming for now — SSE streaming is planned.

If the LLM call fails: the user message is kept, a `failed` row lands in
`inference_logs`, and the endpoint returns 502.

## Database schema

Postgres, async SQLAlchemy 2.0, Alembic migrations. Chain:
**users → conversations → messages**, with **inference_logs** alongside.

### users

| Column | Type | Constraints |
|---|---|---|
| id | INT | PK, autoincrement |
| name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(320) | NOT NULL, UNIQUE |
| password_hash | VARCHAR(255) | NOT NULL |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL, set by the DB |

### conversations

| Column | Type | Constraints |
|---|---|---|
| id | INT | PK, autoincrement |
| user_id | INT | FK → users, NOT NULL, ON DELETE CASCADE |
| title | VARCHAR(200) | NOT NULL, server default "New chat" |
| model | VARCHAR(100) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |
| last_active_at | TIMESTAMPTZ | NOT NULL — the sidebar sort key |

Composite index `(user_id, last_active_at)` — covers the sidebar query
("my conversations, most recent first") in one index.

### messages

| Column | Type | Constraints |
|---|---|---|
| id | INT | PK, autoincrement |
| conversation_id | INT | FK → conversations, NOT NULL, CASCADE |
| role | VARCHAR(16) | NOT NULL, CHECK: `system` / `user` / `assistant` |
| content | TEXT | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

Composite index `(conversation_id, created_at)` — covers loading a transcript
in order and building the LLM context window.

### inference_logs

| Column | Type | Constraints |
|---|---|---|
| id | INT | PK, autoincrement |
| conversation_id | INT | FK → conversations, NOT NULL, CASCADE, indexed |
| provider | VARCHAR(50) | NOT NULL, indexed |
| model | VARCHAR(100) | NOT NULL, indexed |
| prompt_tokens / completion_tokens | INT | NOT NULL, default 0 |
| total_tokens | INT | NOT NULL, CHECK `= prompt_tokens + completion_tokens` |
| latency_ms | INT | NOT NULL |
| status | VARCHAR(16) | NOT NULL, CHECK: `success` / `failed` |
| created_at | TIMESTAMPTZ | NOT NULL, indexed |

### Design decisions

- **Messages are lean transcript rows; inference_logs is the observability
  record.** Model, tokens, latency, and failures describe the *call*, not the
  message, so they live in their own table. A failed call leaves a log row with
  no message row — nothing half-written pollutes the transcript.
- **Messages are append-only** (no `updated_at`) — editing a turn would
  invalidate every reply after it.
- **Enums are VARCHAR + CHECK, not native Postgres enums** — adding a value is
  a trivial migration instead of `ALTER TYPE`.
- **Cascade deletes live in the database** (`ON DELETE CASCADE` +
  `passive_deletes`), so deleting a user or conversation is one statement.
- **Token counts default to 0, not NULL**, so aggregates over inference_logs
  never reason about missing values.

## Configuration

Set via environment or `.env` (see `.env.example`). The important ones:

| Variable | Default | |
|---|---|---|
| `DATABASE_URL` | local postgres | asyncpg URL |
| `JWT_SECRET` | dev placeholder | **must** change in production — startup refuses otherwise |
| `OPENAI_API_KEY` | unset | unset = echo mode |
| `DEFAULT_MODEL` | `gpt-4.1-mini` | per-conversation override via POST /conversations |
| `MAX_CONTEXT_MESSAGES` | 20 | context window cap, bounds the token bill |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated |
