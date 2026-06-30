"""Lightweight Agent Trace Console.

Enabled via ``AGENT_TRACE=true``.  Prints one compact line per pipeline
stage to the backend terminal so developers can follow request flow
without external monitoring tools.

Redaction rules (never bypass):
- API keys, tokens, passwords, secrets are always masked.
- Long strings are truncated at 100 chars.
- Lists are truncated to first 3 items.

Usage::

    from app.lg_agent.observability.trace import trace_event
    trace_event("Memory", {"raw_query": "...", "memory_used": True})
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List


_SENSITIVE_KEY_TOKENS = {
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "authorization",
    "credential",
}


def trace_event(stage: str, payload: Dict[str, Any]) -> None:
    """Emit one ``[AGENT TRACE]`` line if enabled, otherwise no-op."""

    if not _enabled():
        return

    parts = [f"[AGENT TRACE] {stage}"]

    for key, value in payload.items():
        rendered = _render(key, value)
        if rendered is None:
            continue
        parts.append(rendered)

    # Print to stderr so trace output does not contaminate stdout pipelines.
    print(" | ".join(parts), file=sys.stderr, flush=True)


# ── helpers ─────────────────────────────────────────────────────────────


def _enabled() -> bool:
    return os.getenv("AGENT_TRACE", "").strip().lower() == "true"


def _render(key: str, value: Any) -> str | None:
    if value is None or value == "":
        return None
    if _is_sensitive_key(key):
        return f"{key}=***REDACTED***"
    if isinstance(value, list) and value and isinstance(value[0], dict):
        # List of candidate/rec items — extract product_name only.
        return _render_product_list(key, value)
    if isinstance(value, list):
        return _render_list(key, value)
    if isinstance(value, bool):
        return f"{key}={str(value).lower()}"
    text = str(value)
    if len(text) > 100:
        text = text[:97] + "..."
    return f"{key}={text}"


def _render_list(key: str, items: list) -> str:
    texts = [str(v) for v in items[:3]]
    suffix = f"...+{len(items) - 3}" if len(items) > 3 else ""
    combined = ",".join(texts)
    if suffix:
        combined += suffix
    return f"{key}={combined}"


def _render_product_list(key: str, items: List[Dict[str, Any]]) -> str:
    names = [
        str(item.get("product_name") or item.get("ProductName") or "?")
        for item in items[:3]
    ]
    suffix = f"...+{len(items) - 3}" if len(items) > 3 else ""
    return f"{key}={','.join(names)}{suffix}"


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower().replace("-", "_").replace(" ", "_")
    return any(tok in lower for tok in _SENSITIVE_KEY_TOKENS)
