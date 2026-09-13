"""The shape of one ``Goal.progress_history`` entry.

Every progress writer appends one of these (``core/services/goals/
progress_history.py``); the report's ``goals_progressed`` counts them by
``date``. The node stores the list as one JSON string, so the fields are the
JSON-ready spellings: an ISO datetime and the figure written.
"""

from __future__ import annotations

from typing import TypedDict


class ProgressHistoryEntry(TypedDict):
    """One progress event: the figure written and when (ISO datetime)."""

    date: str
    progress_percentage: float | None


__all__ = ["ProgressHistoryEntry"]
