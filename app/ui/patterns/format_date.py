"""Absolute-date display formatter for UI surfaces.

One ``format_date`` for every page that renders a stored timestamp as a plain
date label (submission cards, report headers). Accepts the shapes timestamps
arrive in from the persistence layer (native datetime, Neo4j DateTime, ISO
string) and degrades to a trimmed string rather than raising. For relative
labels ("3h ago") use ``ui.patterns.relative_time.format_relative_time``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def format_date(value: Any, fmt: str = "%d %b %Y", *, empty: str = "") -> str:
    """Render a timestamp-ish value with ``fmt``; ``empty`` when falsy."""
    if not value:
        return empty
    to_native = getattr(value, "to_native", None)
    try:
        if callable(to_native):
            dt = to_native()
        elif isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value))
        if isinstance(dt, datetime):
            return dt.strftime(fmt)
    except (ValueError, TypeError):  # fmt: skip
        pass
    return str(value)[:16].replace("T", " ")
