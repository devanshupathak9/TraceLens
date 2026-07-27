"""Event publishing.

Two modes, chosen by whether a queue URL is configured:

  queue set   → send to SQS; AWS Lambda receives the batch and writes the row.
  queue unset → call the bundled lambda_function directly (local, docker-compose).

Same event either way, so the lambda code is identical in both paths.
"""

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from lambda_function import lambda_handler

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
        import boto3

        region = (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or _region_from(QUEUE_URL)
        )
        _sqs = boto3.client("sqs", region_name=region)
        logger.info("publishing events to SQS (region=%s)", region)
    return _sqs


def publish_event(event: InferenceEvent) -> None:
    try:
        payload = event.model_dump(mode="json")

        if QUEUE_URL:
            response = _queue().send_message(
                QueueUrl=QUEUE_URL, MessageBody=json.dumps(payload)
            )
            logger.info("queued event %s", response.get("MessageId"))
            return

        result = lambda_handler(payload)
        if result.get("statusCode") != 200:
            logger.warning("event not stored: %s", result.get("body"))
    except Exception:
        # Storage problems must not fail ingestion — the SDK already got its 200.
        logger.exception("failed to publish event")


def describe_mode() -> str:
    """Logged at startup so it's obvious which path is live."""
    if QUEUE_URL:
        return f"sqs → {QUEUE_URL}"
    return "direct (bundled lambda_function)"
