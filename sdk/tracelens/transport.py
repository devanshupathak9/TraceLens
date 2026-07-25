"""
Ships events to the ingestion service.

Two properties matter more than anything else here:

1. **It must never slow down the caller.** Logging is not the user's request. The
   public `send()` only appends to an in-memory queue and returns immediately;
   all HTTP happens on a background thread.

2. **It must never break the caller.** If the ingestion service is down, slow, or
   returning garbage, the application must carry on. Every failure path ends in a
   dropped event and a log line, never a raised exception.

A background *thread* rather than an asyncio task, deliberately: the SDK gets
imported into sync and async applications alike, and a thread works in both
without needing a running event loop or caring which one it is.
"""

import atexit
import logging
import queue
import threading
import time
from typing import Any

import httpx

from .events import InferenceEvent

logger = logging.getLogger("tracelens.transport")


class Transport:
    """Batching, non-blocking event shipper."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str | None = None,
        batch_size: int = 50,
        flush_interval: float = 2.0,
        queue_size: int = 10_000,
        timeout: float = 5.0,
        max_retries: int = 2,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.timeout = timeout
        self.max_retries = max_retries

        # Bounded on purpose. An unbounded queue turns an ingestion outage into
        # unbounded memory growth in the application — the SDK would take down the
        # app it is meant to observe. Full queue means drop, and say so.
        self._queue: queue.Queue[InferenceEvent] = queue.Queue(maxsize=queue_size)

        self._stop = threading.Event()
        self._dropped = 0
        self._sent = 0
        self._failed = 0

        self._client = httpx.Client(timeout=timeout)

        # daemon=True so a forgotten shutdown() can't hang interpreter exit; the
        # atexit hook below is what actually flushes in the normal case.
        self._worker = threading.Thread(
            target=self._run, name="tracelens-transport", daemon=True
        )
        self._worker.start()

        atexit.register(self.shutdown)

    # --- public API -------------------------------------------------------

    def send(self, event: InferenceEvent) -> None:
        """
        Enqueue an event. Never blocks, never raises.

        `put_nowait` rather than `put`: blocking here would make a slow ingestion
        service into slow chat responses, which is the exact failure this design
        exists to prevent.
        """
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._dropped += 1
            # Logged sparsely — one line per event would itself become the problem
            # under sustained backpressure.
            if self._dropped % 100 == 1:
                logger.warning(
                    "tracelens queue full, dropped %d events so far", self._dropped
                )

    def flush(self, timeout: float = 5.0) -> None:
        """
        Block until the queue drains or `timeout` elapses.

        Useful in tests and before a deliberate exit. Not needed in normal
        operation.
        """
        deadline = time.monotonic() + timeout
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.02)

    def shutdown(self, timeout: float = 5.0) -> None:
        """
        Flush what's queued and stop the worker.

        Idempotent: registered with atexit and also callable directly, so it has to
        tolerate being run twice.
        """
        if self._stop.is_set():
            return

        self.flush(timeout=timeout)
        self._stop.set()

        if self._worker.is_alive():
            self._worker.join(timeout=timeout)

        self._client.close()

        if self._dropped:
            logger.warning("tracelens dropped %d events in total", self._dropped)

    @property
    def stats(self) -> dict[str, int]:
        """Counters for debugging. Not shipped anywhere."""
        return {
            "sent": self._sent,
            "failed": self._failed,
            "dropped": self._dropped,
            "queued": self._queue.qsize(),
        }

    # --- worker -----------------------------------------------------------

    def _run(self) -> None:
        """
        Drain the queue in batches until told to stop.

        Sends when the batch is full or `flush_interval` has passed, whichever
        comes first — so a busy app batches efficiently and a quiet one still
        reports promptly, which is what "near real time" requires.
        """
        batch: list[InferenceEvent] = []
        last_flush = time.monotonic()

        while not self._stop.is_set() or not self._queue.empty():
            timeout = max(0.05, self.flush_interval - (time.monotonic() - last_flush))

            try:
                batch.append(self._queue.get(timeout=timeout))
            except queue.Empty:
                pass

            due = time.monotonic() - last_flush >= self.flush_interval
            if batch and (len(batch) >= self.batch_size or due):
                self._post(batch)
                batch = []
                last_flush = time.monotonic()

        if batch:
            self._post(batch)

    def _post(self, batch: list[InferenceEvent]) -> None:
        """
        POST one batch, retrying transient failures.

        Retries only what could plausibly succeed on a second attempt: network
        errors and 5xx. A 4xx means the payload is wrong, and resending it
        unchanged would fail identically forever, so it's dropped and logged.

        This is at-most-once delivery. Genuine durability would need a disk-backed
        queue; for observability data, dropping under sustained failure is the
        right trade against risking the host application.
        """
        payload: dict[str, Any] = {
            "events": [event.model_dump(mode="json") for event in batch]
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        url = f"{self.endpoint}/v1/events"

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)

                if response.status_code < 300:
                    self._sent += len(batch)
                    return

                if response.status_code < 500:
                    self._failed += len(batch)
                    logger.warning(
                        "tracelens ingest rejected %d events: %d %s",
                        len(batch),
                        response.status_code,
                        response.text[:200],
                    )
                    return

                # 5xx: fall through to the retry backoff.
                logger.debug("tracelens ingest %d, retrying", response.status_code)

            except httpx.HTTPError as exc:
                logger.debug("tracelens ingest transport error: %s", exc)

            if attempt < self.max_retries:
                # Exponential backoff. No jitter because there is one client per
                # process and a handful of retries — a thundering herd isn't the
                # failure mode here.
                time.sleep(0.5 * (2**attempt))

        self._failed += len(batch)
        logger.warning("tracelens dropped %d events after %d attempts", len(batch), self.max_retries + 1)
