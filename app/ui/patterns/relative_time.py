"""Relative-time label for share/attribution lines ("just now", "3h ago").

One formatter for every surface that renders "when did this happen" next to
an attribution — group Recent Shares tiles, the Shared With Me inbox. Accepts
the three shapes timestamps arrive in from the persistence layer (ISO string,
Neo4j DateTime, native datetime) and degrades to "" rather than raising. The
age and the date come from the stored-instant helpers (``age_of``,
``shown_in``), in the request's zone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.utils.timestamp_helpers import age_of, parse_stamp, shown_in
from core.utils.zone_context import current_zone


def format_relative_time(value: Any) -> str:
    """Render a timestamp (ISO string or Neo4j DateTime) as a relative-ish label."""
    dt = parse_stamp(value)
    if not isinstance(dt, datetime):
        return ""

    age = age_of(dt)
    if age is None:
        return shown_in(dt, current_zone()).strftime("%b %d")

    seconds = int(age.total_seconds())
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
    return shown_in(dt, current_zone()).strftime("%b %d")


__all__ = ["format_relative_time"]
