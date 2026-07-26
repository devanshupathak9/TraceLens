"""tracelens — minimal inference logging for LLM calls.

Wrap a chat-completions call with `trace_call` / `trace_call_async`: the
response comes back unchanged, and latency, tokens, input and output text are
shipped to the logging service in the background.

    import tracelens
    tracelens.init(service="chatjippity-backend", endpoint="http://localhost:8001")

    response = await tracelens.trace_call_async(
        client.chat.completions.create,
        model="gpt-4o",
        messages=messages,
    )
"""

import json
import time

from tracelens.transport import send_event

_config = {
    "service": "unknown",
    "endpoint": "http://localhost:8001",
}


def init(service: str, endpoint: str = "http://localhost:8001") -> None:
    _config["service"] = service
    _config["endpoint"] = endpoint


def trace_call(fn, /, *args, **kwargs):
    """Call `fn(*args, **kwargs)`, record the call, return the response unchanged."""
    start = time.perf_counter()
    try:
        response = fn(*args, **kwargs)
    except Exception as exc:
        _ship(kwargs, None, start, error=exc)
        raise
    _ship(kwargs, response, start)
    return response


async def trace_call_async(fn, /, *args, **kwargs):
    """Async variant of trace_call for AsyncOpenAI clients."""
    start = time.perf_counter()
    try:
        response = await fn(*args, **kwargs)
    except Exception as exc:
        _ship(kwargs, None, start, error=exc)
        raise
    _ship(kwargs, response, start)
    return response


def _ship(call_kwargs, response, start, error=None) -> None:
    event = {
        "service": _config["service"],
        "provider": "openai",
        "model": str(call_kwargs.get("model", "unknown")),
        "input_text": json.dumps(call_kwargs.get("messages", []), default=str),
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }

    if error is not None:
        event["status"] = "failed"
        event["error"] = str(error)
    else:
        event["status"] = "success"
        usage = getattr(response, "usage", None)
        choices = getattr(response, "choices", None)
        if choices:
            event["output_text"] = getattr(choices[0].message, "content", "") or ""
        event["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
        event["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
        event["total_tokens"] = event["prompt_tokens"] + event["completion_tokens"]

    send_event(_config["endpoint"], event)
