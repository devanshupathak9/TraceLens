import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from bus import describe_mode, publish_event
from schemas import InferenceEvent, IngestResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("tracelens")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    print(f"[startup] event sink: {describe_mode()}", flush=True)
    yield


app = FastAPI(title="TraceLens Logging Service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/logs", response_model=IngestResponse)
def ingest(event: InferenceEvent) -> IngestResponse:
    print(
        f"[ingest] {event.service} {event.provider}/{event.model} "
        f"conversation={event.conversation_id} status={event.status} "
        f"latency={event.latency_ms}ms "
        f"tokens={event.prompt_tokens}/{event.completion_tokens}/{event.total_tokens} "
        f"created_at={event.created_at.isoformat()}",
        flush=True,
    )
    print(f"[ingest] input={event.input_text[:200]!r}", flush=True)
    print(f"[ingest] output={event.output_text[:200]!r}", flush=True)
    if event.error:
        print(f"[ingest] error: {event.error}", flush=True)

    publish_event(event)
    return IngestResponse(received=1)
