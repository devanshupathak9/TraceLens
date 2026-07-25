"""
Ambient correlation ids.

The whole point of auto-instrumentation is that `openai.chat.completions.create`
is called without any TraceLens argument. So the conversation and user a call
belongs to can't be passed in — they have to be picked up from the surrounding
context.

`contextvars` rather than thread-locals: they follow `await` boundaries and are
copied into each asyncio task, so concurrent requests in one event loop don't
read each other's ids. A thread-local would be shared by every coroutine on that
thread and silently mislabel everything.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

_conversation_id: ContextVar[str | None] = ContextVar("tracelens_conversation_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("tracelens_session_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("tracelens_user_id", default=None)
_request_id: ContextVar[str | None] = ContextVar("tracelens_request_id", default=None)
_metadata: ContextVar[dict[str, object] | None] = ContextVar("tracelens_metadata", default=None)


@contextmanager
def trace_context(
    *,
    conversation_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
    **metadata: object,
) -> Iterator[None]:
    """
    Tag every instrumented call made inside this block.

        with trace_context(conversation_id=str(conv.id), user_id=str(user.id)):
            stream = await client.chat.completions.create(...)

    Only the arguments you pass are set, so nesting adds detail without clearing
    what an outer block established. Tokens are reset in a finally, so an
    exception can't leak ids into the next request handled by this task.
    """
    tokens = []

    if conversation_id is not None:
        tokens.append((_conversation_id, _conversation_id.set(conversation_id)))
    if session_id is not None:
        tokens.append((_session_id, _session_id.set(session_id)))
    if user_id is not None:
        tokens.append((_user_id, _user_id.set(user_id)))
    if request_id is not None:
        tokens.append((_request_id, _request_id.set(request_id)))
    if metadata:
        merged = {**(_metadata.get() or {}), **metadata}
        tokens.append((_metadata, _metadata.set(merged)))

    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def current_context() -> dict[str, object]:
    """Snapshot of the active ids, for attaching to an event."""
    return {
        "conversation_id": _conversation_id.get(),
        "session_id": _session_id.get(),
        "user_id": _user_id.get(),
        "request_id": _request_id.get(),
        "metadata": dict(_metadata.get() or {}),
    }
