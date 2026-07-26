"""Ships events to the logging service without slowing down the traced call."""

import json
import threading
import urllib.request


def send_event(endpoint: str, event: dict) -> None:
    """Fire-and-forget POST on a daemon thread; the caller never waits."""
    threading.Thread(target=_post, args=(endpoint, event), daemon=True).start()


def _post(endpoint: str, event: dict) -> None:
    try:
        request = urllib.request.Request(
            f"{endpoint.rstrip('/')}/api/v1/logs",
            data=json.dumps(event).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=3)
    except Exception:
        # Observability must never break the app being observed.
        pass
