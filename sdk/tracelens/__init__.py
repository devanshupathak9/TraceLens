"""tracelens — minimal inference logging for LLM calls.

`init()` auto-instruments the openai library: every `chat.completions.create`
call (sync or async) is traced with no changes at the call site. Latency,
tokens and redacted input/output previews are shipped to the logging service
in the background.

    import tracelens
    tracelens.init(service="chatjippity-backend", endpoint="http://localhost:8001")

    tracelens.set_meta(conversation_id=42)   # optional extra event fields
    response = await client.chat.completions.create(model="gpt-4o", messages=messages)

`trace_call` / `trace_call_async` remain available to wrap non-OpenAI callables
explicitly.
"""

import contextvars
import re
import time
from datetime import datetime, timezone

from tracelens.transport import send_event

_config = {
    "service": "unknown",
    "endpoint": "http://localhost:8001",
}

# Extra event fields (e.g. conversation_id) for calls in the current task.
# A contextvar so auto-instrumented calls need no tracing kwargs at all.
_meta_var = contextvars.ContextVar("tracelens_meta", default=None)

# Re-entrancy guard: explicitly wrapping an already-patched method must not
# ship the same call twice.
_active = contextvars.ContextVar("tracelens_active", default=False)

# Only previews of the input/output leave the process, and PII is scrubbed
# from them first: observability logs are read by more people and retained
# longer than the app's own database.
_PREVIEW_CHARS = 200

_PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email addresses
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # card-like digit runs
    re.compile(r"\+?\d[\d -]{8,14}\d"),  # phone numbers
]


def _preview(text) -> str:
    text = str(text)
    for pattern in _PII_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:_PREVIEW_CHARS]


def init(service: str, endpoint: str = "http://localhost:8001") -> None:
    _config["service"] = service
    _config["endpoint"] = endpoint
    _auto_instrument()


def set_meta(**fields) -> None:
    """Attach extra fields (e.g. conversation_id=42) to events shipped from
    the current task/thread."""
    _meta_var.set(fields)


def record(
    *,
    provider: str,
    model: str,
    latency_ms: int,
    input_text: str = "",
    output_text: str = "",
    usage=None,
    status: str = "success",
    error=None,
) -> None:
    """Ship an event for a call the auto-patch can't measure.

    Streaming is the case that needs this: `create(stream=True)` returns an
    iterator immediately, so there is nothing to time or count tokens from at
    call time — only the caller knows when the stream ended. `usage` takes the
    provider's own usage object; token-name differences are normalised here.
    """
    prompt, completion = _token_counts_from(usage)
    event = {
        "service": _config["service"],
        "provider": provider,
        "model": str(model),
        "input_text": _preview(input_text),
        "output_text": _preview(output_text),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "latency_ms": latency_ms,
        "status": status,
        # Always UTC and timezone-aware: this is the call's own timestamp and it
        # is what ends up in inference_logs.created_at, so a naive value here
        # would be read back in whatever timezone the database assumes.
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is not None:
        event["error"] = str(error)

    context_meta = _meta_var.get()
    if isinstance(context_meta, dict):
        event.update(context_meta)

    send_event(_config["endpoint"], event)


def trace_call(fn, /, *args, **kwargs):
    """Call `fn(*args, **kwargs)`, record the call, return the response unchanged.

    Pass `_tracelens={...}` for extra event fields; it is stripped before the
    wrapped function is called.
    """
    meta = kwargs.pop("_tracelens", None)
    if _active.get():
        return fn(*args, **kwargs)
    token = _active.set(True)
    start = time.perf_counter()
    try:
        response = fn(*args, **kwargs)
    except Exception as exc:
        _ship(kwargs, None, start, meta, error=exc)
        raise
    finally:
        _active.reset(token)
    _ship(kwargs, response, start, meta)
    return response


async def trace_call_async(fn, /, *args, **kwargs):
    """Async variant of trace_call for AsyncOpenAI clients."""
    meta = kwargs.pop("_tracelens", None)
    if _active.get():
        return await fn(*args, **kwargs)
    token = _active.set(True)
    start = time.perf_counter()
    try:
        response = await fn(*args, **kwargs)
    except Exception as exc:
        _ship(kwargs, None, start, meta, error=exc)
        raise
    finally:
        _active.reset(token)
    _ship(kwargs, response, start, meta)
    return response


# --- auto-instrumentation -------------------------------------------------

_patched = False


def _auto_instrument() -> None:
    """Monkey-patch the vendor SDKs so every LLM call is traced.

    Idempotent, and a no-op for any vendor that isn't installed — tracelens
    itself stays dependency-free.
    """
    global _patched
    if _patched:
        return
    _patch_openai()
    _patch_anthropic()
    _patched = True


def _patch(owner, attribute, provider, is_async) -> None:
    """Replace `owner.attribute` with a traced version of itself.

    `is_async` is passed rather than detected: the vendor SDKs wrap `create` in
    a synchronous decorator, so the async variant doesn't look like a coroutine
    function even though it returns an awaitable.
    """
    original = getattr(owner, attribute)

    if is_async:

        async def patched(self, *args, **kwargs):
            if kwargs.get("stream"):
                # Returns an iterator, not a response: nothing to time or count
                # yet. The caller reports it with record() once the stream ends.
                return await original.__get__(self)(*args, **kwargs)
            kwargs["_tracelens"] = {"provider": provider}
            return await trace_call_async(original.__get__(self), *args, **kwargs)

    else:

        def patched(self, *args, **kwargs):
            if kwargs.get("stream"):
                return original.__get__(self)(*args, **kwargs)
            kwargs["_tracelens"] = {"provider": provider}
            return trace_call(original.__get__(self), *args, **kwargs)

    setattr(owner, attribute, patched)


def _patch_openai() -> None:
    try:
        from openai.resources.chat import completions
    except ImportError:
        return
    _patch(completions.Completions, "create", "openai", is_async=False)
    _patch(completions.AsyncCompletions, "create", "openai", is_async=True)


def _patch_anthropic() -> None:
    try:
        from anthropic.resources import messages
    except ImportError:
        return
    _patch(messages.Messages, "create", "anthropic", is_async=False)
    _patch(messages.AsyncMessages, "create", "anthropic", is_async=True)


def _output_text(response) -> str:
    """The reply text, from whichever shape the provider returned."""
    # OpenAI: choices[0].message.content
    choices = getattr(response, "choices", None)
    if choices:
        return getattr(choices[0].message, "content", "") or ""
    # Anthropic: a list of content blocks, only some of which are text
    content = getattr(response, "content", None)
    if isinstance(content, list):
        return "".join(
            getattr(block, "text", "") for block in content
            if getattr(block, "type", None) == "text"
        )
    return ""


def _token_counts(response) -> tuple[int, int]:
    return _token_counts_from(getattr(response, "usage", None))


def _token_counts_from(usage) -> tuple[int, int]:
    """(prompt, completion) tokens — OpenAI and Anthropic name these differently."""
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "input_tokens", 0)
    completion = getattr(usage, "completion_tokens", None)
    if completion is None:
        completion = getattr(usage, "output_tokens", 0)
    return int(prompt or 0), int(completion or 0)


def _ship(call_kwargs, response, start, meta=None, error=None) -> None:
    messages = call_kwargs.get("messages") or []
    last = messages[-1] if messages else {}
    input_text = last.get("content", "") if isinstance(last, dict) else last

    event = {
        "service": _config["service"],
        "provider": "unknown",
        "model": str(call_kwargs.get("model", "unknown")),
        "input_text": _preview(input_text),
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if error is not None:
        event["status"] = "failed"
        event["error"] = str(error)
    else:
        event["status"] = "success"
        event["output_text"] = _preview(_output_text(response))
        prompt, completion = _token_counts(response)
        event["prompt_tokens"] = prompt
        event["completion_tokens"] = completion
        event["total_tokens"] = prompt + completion

    context_meta = _meta_var.get()
    if isinstance(context_meta, dict):
        event.update(context_meta)
    if isinstance(meta, dict):
        event.update(meta)

    send_event(_config["endpoint"], event)
