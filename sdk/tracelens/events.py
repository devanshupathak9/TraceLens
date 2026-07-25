"""
The event the SDK ships.

Mirrors `logging-service/schemas.py`. Duplicated rather than shared because the
SDK is installed inside someone else's application: a shared package would tie
their dependency tree to the ingestion service's release cycle.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["success", "error", "cancelled"]


class InferenceEvent(BaseModel):
    """One observed LLM call."""

    # Generated here so retries are idempotent — the consumer can upsert on this
    # and a re-delivered event won't be counted twice.
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    service: str = "unknown"
    sdk_version: str = "0.1.0"

    provider: str
    model: str
    operation: str = "chat.completions"
    streaming: bool = False

    status: Status
    error_type: str | None = None
    error_message: str | None = None

    started_at: datetime
    ended_at: datetime
    latency_ms: int
    time_to_first_token_ms: int | None = None

    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    conversation_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None

    input_preview: str | None = None
    output_preview: str | None = None
    message_count: int | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)


def utc_now() -> datetime:
    """Timezone-aware UTC. Naive datetimes are ambiguous once they cross a wire."""
    return datetime.now(timezone.utc)


def elapsed_ms(start: float, end: float) -> int:
    """
    Milliseconds between two `time.perf_counter()` readings.

    perf_counter rather than subtracting wall-clock timestamps: it's monotonic, so
    an NTP correction mid-request can't produce a negative latency.
    """
    return max(int((end - start) * 1000), 0)
