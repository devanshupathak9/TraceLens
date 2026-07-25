"""
TraceLens ingestion service.

Receives inference events from the SDK, validates them, and (for now) keeps them
in memory so they can be inspected immediately.

**Storage is deliberately not implemented yet.** The next step is to publish each
accepted event to the event bus and let a worker persist it to Postgres; the
in-memory buffer below is a development aid so the SDK and dashboards have
something to talk to in the meantime. `_store_events()` is the single seam where
that swap happens — everything else stays as it is.
"""

import logging
import statistics
import sys
from collections import Counter, deque
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from config import Settings, get_settings
from schemas import (
    EventBatch,
    IngestResponse,
    InferenceEvent,
    RejectedEvent,
    StatsResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("tracelens.ingest")

settings = get_settings()

if settings.is_production and not settings.ingest_api_key:
    raise RuntimeError("INGEST_API_KEY must be set in production")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bounded ring buffer: oldest events are dropped once it's full, so a long-running
# process can't grow without limit. Not durable — a restart loses everything,
# which is exactly why it's a placeholder for the bus.
_buffer: deque[InferenceEvent] = deque(maxlen=settings.buffer_size)
_total_received = 0


# --- auth -----------------------------------------------------------------


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """
    Verify the SDK's shared secret.

    Skipped entirely when no key is configured, so local development needs no
    setup. Production without a key is refused at startup, above.
    """
    if settings.ingest_api_key is None:
        return

    if x_api_key != settings.ingest_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )


# --- storage seam ---------------------------------------------------------


def _store_events(events: list[InferenceEvent]) -> None:
    """
    Hand off validated events.

    Replace the body with a publish to the event bus. Everything upstream of this
    function — validation, partial-failure handling, auth — stays unchanged, which
    is the point of keeping it isolated.
    """
    global _total_received

    for event in events:
        _buffer.append(event)
        _total_received += 1

        logger.info(
            "event %s %s/%s status=%s latency=%dms tokens=%s conversation=%s",
            event.event_id,
            event.provider,
            event.model,
            event.status,
            event.latency_ms,
            event.total_tokens,
            event.conversation_id,
        )


# --- routes ---------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness. No dependencies, so it stays honest about the process only."""
    return {"status": "ok"}


@app.post(
    "/v1/events",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def ingest_events(batch: EventBatch) -> IngestResponse:
    """
    Ingest a batch of events.

    202, not 201: the events have been accepted for processing, not necessarily
    persisted. That distinction becomes real once a bus sits behind this.

    Validation happens twice on purpose. Pydantic rejects the request only if the
    envelope itself is unusable; each event is then re-checked individually so one
    malformed event is reported and skipped rather than failing its 49 valid
    neighbours — which would make the SDK retry the batch forever.
    """
    accepted: list[InferenceEvent] = []
    errors: list[RejectedEvent] = []

    for index, event in enumerate(batch.events):
        try:
            accepted.append(InferenceEvent.model_validate(event, strict=False))
        except ValidationError as exc:
            errors.append(RejectedEvent(index=index, error=_summarise(exc)))

    if accepted:
        _store_events(accepted)

    if errors:
        logger.warning("rejected %d of %d events", len(errors), len(batch.events))

    return IngestResponse(accepted=len(accepted), rejected=len(errors), errors=errors)


@app.post(
    "/v1/events/single",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_api_key)],
)
async def ingest_single_event(event: InferenceEvent) -> IngestResponse:
    """
    Ingest one event.

    A convenience for manual testing with curl; the SDK always batches.
    """
    _store_events([event])
    return IngestResponse(accepted=1)


@app.get("/v1/events", response_model=list[InferenceEvent])
async def list_events(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    model: str | None = None,
    event_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[InferenceEvent]:
    """
    Read back buffered events, newest first.

    Debugging aid only — it reads the in-memory buffer, so it's empty after a
    restart and shows nothing from other replicas.
    """
    events = list(reversed(_buffer))

    if model:
        events = [event for event in events if event.model == model]
    if event_status:
        events = [event for event in events if event.status == event_status]

    return events[:limit]


@app.get("/v1/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """
    Aggregate over the buffer: the numbers a latency/throughput/error dashboard
    needs, computed on the fly.

    This is fine over 1000 in-memory events and wrong as a long-term design — real
    dashboards should read pre-aggregated rollup tables, because scanning raw logs
    per request stops working the moment there are millions of them.
    """
    events = list(_buffer)

    if not events:
        return StatsResponse(
            total_events=_total_received,
            buffered_events=0,
            error_count=0,
            error_rate=0.0,
            avg_latency_ms=None,
            p95_latency_ms=None,
            by_model={},
            by_status={},
        )

    latencies = sorted(event.latency_ms for event in events)
    error_count = sum(1 for event in events if event.status == "error")

    return StatsResponse(
        total_events=_total_received,
        buffered_events=len(events),
        error_count=error_count,
        error_rate=round(error_count / len(events), 4),
        avg_latency_ms=round(statistics.fmean(latencies), 2),
        p95_latency_ms=float(_percentile(latencies, 0.95)),
        by_model=dict(Counter(event.model for event in events)),
        by_status=dict(Counter(event.status for event in events)),
    )


@app.delete("/v1/events", status_code=status.HTTP_204_NO_CONTENT)
async def clear_events(response: Response) -> None:
    """Empty the buffer. Development convenience; refused in production."""
    if settings.is_production:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not available")
    _buffer.clear()


# --- helpers --------------------------------------------------------------


def _percentile(sorted_values: list[int], fraction: float) -> float:
    """
    Nearest-rank percentile.

    Deliberately not interpolated: with a handful of samples an interpolated p95
    invents a latency nobody actually experienced.
    """
    if not sorted_values:
        return 0.0
    index = min(int(round(fraction * (len(sorted_values) - 1))), len(sorted_values) - 1)
    return float(sorted_values[index])


def _summarise(exc: ValidationError) -> str:
    """Flatten a Pydantic error into one line the SDK can log usefully."""
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(item) for item in error["loc"]) or "body"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
