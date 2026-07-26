"""Event publishing.

No Redis/Kafka yet: events are handed straight to the lambda function, which
validates them and writes inference_logs. Swapping this for a real queue later
only changes this file.
"""

import logging
import sys
from pathlib import Path

# `lambda` is a reserved word, so the folder can't be imported as a package —
# put it on the path and import the module directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from lambda_function import lambda_handler

from schemas import InferenceEvent

logger = logging.getLogger("tracelens")


def publish_event(event: InferenceEvent) -> None:
    try:
        result = lambda_handler(event.model_dump(mode="json"))
        if result.get("statusCode") != 200:
            logger.warning("event not stored: %s", result.get("body"))
    except Exception:
        # Storage problems must not fail ingestion.
        logger.exception("failed to store event")
