"""Lightweight SSE event formatting for stage-level streaming.

Usage::

    await event_sink(sse_event("stage", {"stage": "Retrieval", "status": "running"}))

Frontend parses these as ``text/event-stream`` chunks via ``fetch`` +
``ReadableStream``.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def sse_event(event_type: str, payload: Dict[str, Any]) -> str:
    """Return one SSE frame: ``data: {json}\\n\\n``.

    The ``type`` field is always included as the first key so the frontend
    can dispatch to the correct handler.
    """
    body = {"type": event_type, **payload}
    return "data: " + json.dumps(body, ensure_ascii=False, default=str) + "\n\n"
