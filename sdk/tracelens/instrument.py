"""
Auto-instrumentation for the OpenAI client.

`instrument_openai()` patches the client's `create` methods so existing code is
recorded without changing a single call site. That is the whole value proposition:
adding observability shouldn't mean editing every place the model is called.

The patch wraps four entry points — sync and async, streaming and not. Streaming is
the interesting case: the method returns immediately with an iterator, so the call
isn't finished when it returns. The event can only be emitted once the *stream* is
exhausted, which means wrapping the iterator too.
"""

import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any, Callable

from .context import current_context
from .events import InferenceEvent, elapsed_ms, utc_now
from .redaction import make_preview, preview_messages

logger = logging.getLogger("tracelens.instrument")

_patched = False
_originals: dict[str, Callable[..., Any]] = {}


def instrument_openai(client_config: "Any") -> None:
    """
    Patch `openai` so every chat completion is recorded.

    Called once from `tracelens.init()`. Idempotent — patching twice would wrap the
    wrapper and emit two events per call.

    Patches the *class* methods rather than an instance, so clients constructed
    later are instrumented too.
    """
    global _patched

    if _patched:
        logger.debug("openai already instrumented, skipping")
        return

    try:
        from openai.resources.chat import completions
    except ImportError:
        logger.warning("openai is not installed; skipping instrumentation")
        return

    _originals["sync"] = completions.Completions.create
    _originals["async"] = completions.AsyncCompletions.create

    completions.Completions.create = _wrap_sync(_originals["sync"], client_config)
    completions.AsyncCompletions.create = _wrap_async(_originals["async"], client_config)

    _patched = True
    logger.info("tracelens: openai chat.completions instrumented")


def uninstrument_openai() -> None:
    """Restore the original methods. Mainly for tests."""
    global _patched

    if not _patched:
        return

    from openai.resources.chat import completions

    completions.Completions.create = _originals["sync"]
    completions.AsyncCompletions.create = _originals["async"]

    _patched = False


# --- wrappers -------------------------------------------------------------


def _wrap_async(original: Callable[..., Any], config: Any) -> Callable[..., Any]:
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        recorder = _Recorder(config, kwargs)

        try:
            result = await original(self, *args, **kwargs)
        except BaseException as exc:
            # BaseException so CancelledError is recorded too — a user hitting
            # "stop" is a real outcome worth measuring, not an absence of one.
            recorder.finish_error(exc)
            raise

        if recorder.streaming:
            # Not awaited to completion here: hand back a wrapper that records as
            # the caller consumes it.
            return _instrumented_async_stream(result, recorder)

        recorder.finish_response(result)
        return result

    return wrapper


def _wrap_sync(original: Callable[..., Any], config: Any) -> Callable[..., Any]:
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        recorder = _Recorder(config, kwargs)

        try:
            result = original(self, *args, **kwargs)
        except BaseException as exc:
            recorder.finish_error(exc)
            raise

        if recorder.streaming:
            return _instrumented_sync_stream(result, recorder)

        recorder.finish_response(result)
        return result

    return wrapper


async def _instrumented_async_stream(stream: Any, recorder: "_Recorder") -> AsyncIterator[Any]:
    """
    Pass chunks through while observing them.

    Yields every chunk unchanged, so the caller cannot tell the difference. The
    event is emitted in the `finally`, which is what guarantees it fires whether
    the stream completed, raised, or was abandoned part-way.
    """
    try:
        async for chunk in stream:
            recorder.observe_chunk(chunk)
            yield chunk
    except BaseException as exc:
        recorder.finish_error(exc)
        raise
    else:
        recorder.finish_stream()


def _instrumented_sync_stream(stream: Any, recorder: "_Recorder") -> Iterator[Any]:
    try:
        for chunk in stream:
            recorder.observe_chunk(chunk)
            yield chunk
    except BaseException as exc:
        recorder.finish_error(exc)
        raise
    else:
        recorder.finish_stream()


# --- recorder -------------------------------------------------------------


class _Recorder:
    """
    Accumulates one call's metadata and emits the event exactly once.

    Every method swallows its own exceptions. A bug in instrumentation must not
    break the application being instrumented — a missing metric is a far better
    outcome than a failed chat response.
    """

    def __init__(self, config: Any, kwargs: dict[str, Any]) -> None:
        self.config = config
        self.model = str(kwargs.get("model", "unknown"))
        self.streaming = bool(kwargs.get("stream", False))
        self.messages = kwargs.get("messages") or []

        self.started_at = utc_now()
        self.start = time.perf_counter()
        self.first_token_at: float | None = None

        self.chunks: list[str] = []
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.finish_reason: str | None = None
        self.emitted = False

    # --- observation --------------------------------------------------------

    def observe_chunk(self, chunk: Any) -> None:
        """Extract text and usage from a streamed chunk."""
        try:
            if self.first_token_at is None:
                self.first_token_at = time.perf_counter()

            # The final usage-bearing chunk has an EMPTY choices list, so indexing
            # unconditionally raises IndexError at the very end of every stream.
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    self.chunks.append(content)

                reason = getattr(choices[0], "finish_reason", None)
                if reason:
                    self.finish_reason = reason

            # Present only when the caller passed
            # stream_options={"include_usage": True}. Without it token counts are
            # simply absent and every streamed call logs null usage.
            usage = getattr(chunk, "usage", None)
            if usage:
                self.prompt_tokens = getattr(usage, "prompt_tokens", None)
                self.completion_tokens = getattr(usage, "completion_tokens", None)
        except Exception:
            logger.debug("tracelens: failed to read chunk", exc_info=True)

    # --- completion ---------------------------------------------------------

    def finish_response(self, response: Any) -> None:
        """Record a non-streamed response."""
        try:
            choices = getattr(response, "choices", None) or []
            if choices:
                message = getattr(choices[0], "message", None)
                content = getattr(message, "content", None) if message else None
                if content:
                    self.chunks.append(content)
                self.finish_reason = getattr(choices[0], "finish_reason", None)

            usage = getattr(response, "usage", None)
            if usage:
                self.prompt_tokens = getattr(usage, "prompt_tokens", None)
                self.completion_tokens = getattr(usage, "completion_tokens", None)

            self._emit("success")
        except Exception:
            logger.debug("tracelens: failed to record response", exc_info=True)

    def finish_stream(self) -> None:
        self._emit("success")

    def finish_error(self, exc: BaseException) -> None:
        """
        Record a failure or cancellation.

        Cancellation is reported as its own status rather than as an error: a user
        pressing stop is not a fault, and folding the two together would make the
        error-rate dashboard useless.
        """
        import asyncio

        cancelled = isinstance(exc, asyncio.CancelledError) or isinstance(
            exc, KeyboardInterrupt
        )
        self._emit(
            "cancelled" if cancelled else "error",
            error_type=type(exc).__name__,
            error_message=str(exc)[:2000] or None,
        )

    def _emit(
        self,
        status: str,
        *,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        # Guard against double emission: a stream that raises after yielding would
        # otherwise be recorded twice.
        if self.emitted:
            return
        self.emitted = True

        try:
            end = time.perf_counter()
            context = current_context()

            event = InferenceEvent(
                service=self.config.service,
                sdk_version=self.config.sdk_version,
                provider="openai",
                model=self.model,
                streaming=self.streaming,
                status=status,  # type: ignore[arg-type]
                error_type=error_type,
                error_message=error_message,
                started_at=self.started_at,
                ended_at=utc_now(),
                latency_ms=elapsed_ms(self.start, end),
                time_to_first_token_ms=(
                    elapsed_ms(self.start, self.first_token_at)
                    if self.first_token_at is not None
                    else None
                ),
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
                message_count=len(self.messages) if self.messages else None,
                input_preview=preview_messages(
                    self.messages,
                    limit=self.config.preview_limit,
                    redact_pii=self.config.redact_pii,
                )
                or None,
                output_preview=make_preview(
                    "".join(self.chunks),
                    limit=self.config.preview_limit,
                    redact_pii=self.config.redact_pii,
                )
                or None,
                conversation_id=context["conversation_id"],  # type: ignore[arg-type]
                session_id=context["session_id"],  # type: ignore[arg-type]
                user_id=context["user_id"],  # type: ignore[arg-type]
                request_id=context["request_id"],  # type: ignore[arg-type]
                metadata={
                    **context["metadata"],  # type: ignore[dict-item]
                    **({"finish_reason": self.finish_reason} if self.finish_reason else {}),
                },
            )

            self.config.transport.send(event)
        except Exception:
            logger.debug("tracelens: failed to emit event", exc_info=True)
