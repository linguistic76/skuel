"""Absolute-date display formatter for UI surfaces.

One ``format_date`` for every page that renders a stored timestamp as a plain
date label (submission cards, report headers). Accepts the shapes timestamps
arrive in from the persistence layer (native datetime, Neo4j DateTime, ISO
string) and degrades to a trimmed string rather than raising. An instant is
shown in the request's zone (``shown_in``); a calendar day — a ``date``, or a
date-only string — is never converted. For relative labels ("3h ago") use
``ui.patterns.relative_time.format_relative_time``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.utils.timestamp_helpers import parse_stamp, shown_in
from core.utils.zone_context import current_zone


def format_date(value: Any, fmt: str = "%d %b %Y", *, empty: str = "") -> str:
    """Render a timestamp-ish value with ``fmt``; ``empty`` when falsy."""
    if not value:
        return empty
    stamp = parse_stamp(value)
    if isinstance(stamp, datetime):
        return shown_in(stamp, current_zone()).strftime(fmt)
    if isinstance(stamp, date):
        return stamp.strftime(fmt)
    return str(value)[:16].replace("T", " ")
