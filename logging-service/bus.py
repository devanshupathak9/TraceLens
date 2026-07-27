"""Event publishing.

SQS is the only sink: every ingested event is forwarded to the queue, and the
AWS Lambda subscribed to it does the database write. This service never touches
Postgres itself.

Publishing failures are logged and swallowed — the SDK already got its 200, and
observability must never break the app being observed.
"""

import json
import logging
import os

import boto3

from schemas import InferenceEvent

logger = logging.getLogger("tracelens")

QUEUE_URL = os.environ.get("QUEUE_URL", "")


def _region_from(queue_url: str) -> str | None:
    """Pull the region out of an SQS URL: https://sqs.<region>.amazonaws.com/...

    Saves configuring AWS_REGION separately; boto3 can't sign a request without
    a region and the resulting NoRegionError is not an obvious error to read.
    """
    parts = queue_url.split("/")
    if len(parts) > 2:
        host = parts[2].split(".")
        if len(host) > 2 and host[0] == "sqs":
            return host[1]
    return None


_sqs = None


def _queue():
    global _sqs
    if _sqs is None:
        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or _region_from(QUEUE_URL)
        )
        _sqs = boto3.client("sqs", region_name=region)
        print(f"[bus] sqs client ready (region={region})", flush=True)
    return _sqs


def publish_event(event: InferenceEvent) -> None:
    if not QUEUE_URL:
        print("[bus] QUEUE_URL is not set — dropping event", flush=True)
        return

    try:
        payload = event.model_dump(mode="json")
        print(f"[bus] publishing -> {payload}", flush=True)

        response = _queue().send_message(
            QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload)
        )
        print(f"[bus] queued MessageId={response.get('MessageId')}", flush=True)
    except Exception as exc:
        print(f"[bus] publish FAILED: {type(exc).__name__}: {exc}", flush=True)
        logger.exception("failed to publish event")


def describe_mode() -> str:
    """Logged at startup so a missing queue URL is obvious immediately."""
    if QUEUE_URL:
        return f"sqs -> {QUEUE_URL}"
    return "NO QUEUE_URL SET — events will be dropped"
