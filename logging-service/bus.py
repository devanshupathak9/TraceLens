import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

from lambda_function import lambda_handler

from schemas import InferenceEvent

logger = logging.getLogger("tracelens")

# When set, events go to SQS and AWS Lambda does the storing. When empty
# (local/docker-compose), the bundled lambda_function is called directly.
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")

_sqs = None


def _queue():
    global _sqs
    if _sqs is None:
        import boto3

        _sqs = boto3.client("sqs")
    return _sqs


def publish_event(event: InferenceEvent) -> None:
    try:
        payload = event.model_dump(mode="json")
        if SQS_QUEUE_URL:
            _queue().send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(payload))
            return
        result = lambda_handler(payload)
        if result.get("statusCode") != 200:
            logger.warning("event not stored: %s", result.get("body"))
    except Exception:
        logger.exception("failed to publish event")
