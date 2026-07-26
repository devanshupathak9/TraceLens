"""Event publishing.

Placeholder for the internal event bus: later this will hand events to a queue
or worker for persistence and analytics. For now ingestion just prints, and
this is a no-op.
"""

from schemas import InferenceEvent


def publish_event(event: InferenceEvent) -> None:
    pass
