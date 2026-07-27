
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from lambda_function import lambda_handler

from schemas import InferenceEvent
logger = logging.getLogger("tracelens")


def publish_event(event: InferenceEvent) -> None:
    try:
        print("Event received!!")
        result = lambda_handler(event.model_dump(mode="json"))
        print(result)
        if result.get("statusCode") != 200:
            logger.warning("event not stored: %s", result.get("body"))
    except Exception:
        logger.exception("failed to store event")
