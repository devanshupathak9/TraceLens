import logging

from fastapi import FastAPI

from bus import describe_mode, publish_event
from schemas import InferenceEvent, IngestResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("tracelens")

app = FastAPI(title="TraceLens Logging Service", version="0.1.0")


@app.on_event("startup")
async def log_mode() -> None:
    # Without this, "why didn't my event reach SQS?" means reading env vars by
    # hand — a missing queue URL silently falls back to the direct write.
    logger.info("event sink: %s", describe_mode())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Sync handler on purpose: FastAPI runs it in a threadpool, so the blocking
# DB write in the lambda can't stall the event loop.
@app.post("/api/v1/logs", response_model=IngestResponse)
def ingest(event: InferenceEvent) -> IngestResponse:
    logger.info(
        "[%s] %s/%s status=%s latency=%dms tokens=%d/%d/%d input=%r output=%r",
        event.service,
        event.provider,
        event.model,
        event.status,
        event.latency_ms,
        event.prompt_tokens,
        event.completion_tokens,
        event.total_tokens,
        event.input_text[:200],
        event.output_text[:200],
    )
    if event.error:
        logger.info("[%s] error: %s", event.service, event.error)

    publish_event(event)
    return IngestResponse(received=1)
