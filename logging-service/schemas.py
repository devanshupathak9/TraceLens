from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class InferenceEvent(BaseModel):
    """One LLM call as reported by the tracelens SDK."""

    service: str = "unknown"
    conversation_id: int | None = None
    provider: str = "openai"
    model: str
    input_text: str = ""
    output_text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int
    status: Literal["success", "failed"] = "success"
    error: str | None = None
    # When the call happened, as stamped by the SDK; forwarded to the queue and
    # stored as inference_logs.created_at. Timezone-aware on purpose — the old
    # datetime.utcnow default was naive, so a client that omitted the field got
    # a timestamp Postgres then read as local time in a TIMESTAMPTZ column.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestResponse(BaseModel):
    status: str = "ok"
    received: int
