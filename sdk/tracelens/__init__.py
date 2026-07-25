"""
TraceLens SDK — inference logging for LLM applications.

Two lines to install it:

    import tracelens
    tracelens.init(service="chat-api", endpoint="http://localhost:8001")

From then on every `openai` chat completion — sync or async, streamed or not — is
recorded and shipped in the background. No call sites change.

Tag calls with the conversation they belong to:

    from tracelens import trace_context

    with trace_context(conversation_id=str(conversation.id), user_id=str(user.id)):
        stream = await client.chat.completions.create(...)
"""

import logging
from dataclasses import dataclass

from .context import current_context, trace_context
from .events import InferenceEvent
from .instrument import instrument_openai, uninstrument_openai
from .redaction import make_preview, redact
from .transport import Transport

__version__ = "0.1.0"

__all__ = [
    "init",
    "shutdown",
    "flush",
    "trace_context",
    "current_context",
    "InferenceEvent",
    "Transport",
    "redact",
    "make_preview",
    "stats",
    "__version__",
]

logger = logging.getLogger("tracelens")


@dataclass
class Config:
    """Resolved SDK configuration, held by the active client."""

    service: str
    transport: Transport
    sdk_version: str = __version__
    preview_limit: int = 500
    redact_pii: bool = True


_config: Config | None = None


def init(
    *,
    service: str = "unknown",
    endpoint: str = "http://localhost:8001",
    api_key: str | None = None,
    instrument: bool = True,
    redact_pii: bool = True,
    preview_limit: int = 500,
    batch_size: int = 50,
    flush_interval: float = 2.0,
    queue_size: int = 10_000,
) -> Config:
    """
    Start the SDK.

    Call once at application startup, before any LLM client is used.

    Args:
        service: Name recorded on every event, so multiple services are
            distinguishable in one dashboard.
        endpoint: Base URL of the ingestion service. `/v1/events` is appended.
        api_key: Sent as `X-API-Key` when the ingestion service requires it.
        instrument: Patch the OpenAI client automatically. Set False to record
            calls manually instead.
        redact_pii: Strip recognised identifiers from previews before they leave
            the process. Leave this on.
        preview_limit: Characters kept from prompt and completion. Previews only —
            full prompts are never sent.

    Returns the resolved config. Calling twice returns the existing one rather than
    starting a second transport thread.
    """
    global _config

    if _config is not None:
        logger.debug("tracelens already initialised")
        return _config

    transport = Transport(
        endpoint=endpoint,
        api_key=api_key,
        batch_size=batch_size,
        flush_interval=flush_interval,
        queue_size=queue_size,
    )

    _config = Config(
        service=service,
        transport=transport,
        preview_limit=preview_limit,
        redact_pii=redact_pii,
    )

    if instrument:
        instrument_openai(_config)

    logger.info("tracelens initialised (service=%s, endpoint=%s)", service, endpoint)
    return _config


def shutdown(timeout: float = 5.0) -> None:
    """
    Flush queued events and stop the background thread.

    Registered with atexit automatically, so this is only needed for a deliberate
    early shutdown — for example a FastAPI lifespan teardown.
    """
    global _config

    if _config is None:
        return

    _config.transport.shutdown(timeout=timeout)
    uninstrument_openai()
    _config = None


def flush(timeout: float = 5.0) -> None:
    """Block until queued events are sent. Useful in tests."""
    if _config is not None:
        _config.transport.flush(timeout=timeout)


def stats() -> dict[str, int]:
    """Transport counters — sent, failed, dropped, queued."""
    if _config is None:
        return {"sent": 0, "failed": 0, "dropped": 0, "queued": 0}
    return _config.transport.stats
