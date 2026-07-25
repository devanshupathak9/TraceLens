"""
Every HTTP endpoint, in one file.

Paths match `frontend/src/api/` exactly — that layer is the contract. Bodies raise
NotImplementedError; the signatures, status codes, and response models are the
structure.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from database import check_connection
from schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    ConversationUpdate,
    GuestRequest,
    LoginRequest,
    MessageCreate,
    RegisterRequest,
    TokenResponse,
    UpgradeGuestRequest,
    UserOut,
)
from security import CurrentUser, SessionDep, SettingsDep

router = APIRouter()


# =========================================================================
# health
# =========================================================================

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def liveness() -> dict[str, str]:
    """
    Is the process up?

    Deliberately does not touch the database. A liveness probe that fails on a
    database blip gets the container restarted, which fixes nothing and turns a
    recoverable dependency outage into a crash loop.
    """
    return {"status": "ok"}


@health_router.get("/health/ready")
async def readiness(response: Response) -> dict[str, object]:
    """
    Can this instance serve traffic?

    Returns 503 when the database is unreachable so a load balancer stops routing
    here, while leaving the process alive.
    """
    database_ok = await check_connection()
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database_ok else "degraded",
        "checks": {"database": "ok" if database_ok else "unreachable"},
    }


# =========================================================================
# auth
# =========================================================================

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """
    Create a registered user and return a token.

    Return 409 if the email exists. Rely on the unique index rather than a
    pre-check — two simultaneous registrations both pass a SELECT and only the
    index stops the duplicate, so catch IntegrityError and translate it.
    """
    raise NotImplementedError


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """
    Exchange credentials for a token.

    Return the same 401 for unknown email and wrong password — distinguishing
    them tells an attacker which emails are registered. Guests have a null
    password_hash and must never authenticate here.
    """
    raise NotImplementedError


@auth_router.post("/guest", response_model=TokenResponse)
async def login_as_guest(
    payload: GuestRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """
    Get or create the guest account for this device id.

    Must be idempotent: the same device id returns the same user, so a returning
    guest keeps their history. 200, not 201 — the frontend does not distinguish,
    and the row usually already exists.

    Note a device id whose user has since upgraded still resolves to that user,
    who is no longer a guest. Returning them is correct: it's the same person on
    the same browser.
    """
    raise NotImplementedError


@auth_router.post("/upgrade", response_model=TokenResponse)
async def upgrade_guest(
    payload: UpgradeGuestRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    """
    Attach credentials to the signed-in guest, keeping their conversations.

    Sets email/password_hash and flips is_guest to false on the *existing* row —
    no new user, no moving conversations. Return 409 if already registered, or if
    the email is taken. Issue a fresh token: the claims describe a different
    account state now.
    """
    raise NotImplementedError


@auth_router.get("/me", response_model=UserOut)
async def read_current_user(user: CurrentUser) -> UserOut:
    """
    Return the authenticated user.

    Called on every page load to validate a stored token, so keep it cheap — the
    dependency has already loaded the row.
    """
    raise NotImplementedError


# =========================================================================
# conversations
# =========================================================================

conversations_router = APIRouter(prefix="/conversations", tags=["conversations"])


@conversations_router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ConversationSummary]:
    """
    This user's conversations, newest first.

    Ordered by updated_at DESC to match how the frontend sorts locally after a
    reply. `message_count` needs an aggregate — do it as one query with a
    correlated subquery or a GROUP BY join, not a count per row.
    """
    raise NotImplementedError


@conversations_router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationSummary:
    """
    Create an empty conversation.

    The frontend calls this lazily on the first message, then immediately posts to
    the messages endpoint, so it must return the id.
    """
    raise NotImplementedError


@conversations_router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationDetail:
    """
    One conversation with its full message history, oldest first.

    Return 404 — never 403 — when it belongs to someone else. A 403 confirms the
    id exists, which is an enumeration oracle. Scope every query by user_id
    rather than filtering after loading.
    """
    raise NotImplementedError


@conversations_router.patch("/{conversation_id}", response_model=ConversationSummary)
async def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ConversationSummary:
    """Rename a conversation. 404 if it isn't this user's."""
    raise NotImplementedError


@conversations_router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> None:
    """
    Delete a conversation and its messages.

    Messages go via ON DELETE CASCADE. Must return an empty 204 body — the
    frontend's request() returns early on 204 and would choke on JSON.

    Telemetry rows are intentionally *not* deleted: inference logs have no foreign
    key to this table precisely so metrics outlive the chats they describe.
    """
    raise NotImplementedError


# =========================================================================
# chat (streaming)
# =========================================================================

chat_router = APIRouter(prefix="/conversations", tags=["chat"])


@chat_router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    user: CurrentUser,
    settings: SettingsDep,
) -> StreamingResponse:
    """
    Post a user message and stream the assistant reply as SSE.

    Emits, in order: `start` (with the assistant message id and model), any number
    of `delta`, then exactly one `done` — or a single `error`. Shapes are in
    schemas.py; each has `to_frame()`.

    Four things this route has to get right:

    1. **No `Depends(get_session)`.** The response outlives this function, so a
       request-scoped session would hold a pooled connection for the whole
       generation. Use `session_scope()` for two short sessions: one to load
       context and persist the user message before streaming, one to persist the
       assistant message after.

    2. **Validate ownership before streaming.** Once the first byte is sent the
       status code is fixed at 200 and a 404 can no longer be returned. Check the
       conversation belongs to this user *first*.

    3. **Handle client disconnect.** Cancellation surfaces as
       `asyncio.CancelledError` in the generator when the user hits stop. Save the
       partial text with status CANCELLED and re-raise — swallowing it leaks the
       upstream provider request.

    4. **Disable proxy buffering.** Return
       `headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}` and
       `media_type="text/event-stream"`. Without `X-Accel-Buffering`, nginx
       buffers the whole reply and the user sees it arrive in one lump —
       frontend/nginx.conf also sets `proxy_buffering off`, but the header is what
       covers ingress controllers you don't configure.

    Also bump the conversation's `updated_at` so it sorts to the top of the
    sidebar, and set its title from the first user message if still "New chat".
    """
    raise NotImplementedError


# =========================================================================
# assembly
# =========================================================================
# Mounted by main.py under settings.api_prefix (default "/api"), so nothing here
# repeats that prefix.

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(conversations_router)
router.include_router(chat_router)
