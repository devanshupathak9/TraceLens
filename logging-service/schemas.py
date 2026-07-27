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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestResponse(BaseModel):
    status: str = "ok"
    received: int
