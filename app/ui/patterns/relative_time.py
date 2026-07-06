"""Relative-time label for share/attribution lines ("just now", "3h ago").

One formatter for every surface that renders "when did this happen" next to
an attribution — group Recent Shares tiles, the Shared With Me inbox. Accepts
the three shapes timestamps arrive in from the persistence layer (ISO string,
Neo4j DateTime, native datetime) and degrades to "" rather than raising.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def format_relative_time(value: Any) -> str:
    """Render a timestamp (ISO string or Neo4j DateTime) as a relative-ish label."""
    if value is None:
        return ""
    to_native = getattr(value, "to_native", None)
    try:
        if callable(to_native):
            dt = to_native()
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value)
        else:
            dt = value  # already datetime
    except (ValueError, TypeError):  # fmt: skip
        return ""

    if not isinstance(dt, datetime):
        return ""

    now = datetime.now(dt.tzinfo or UTC)
    try:
        delta = now - dt
    except TypeError:
        return dt.strftime("%b %d")

    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    return dt.strftime("%b %d")


__all__ = ["format_relative_time"]
