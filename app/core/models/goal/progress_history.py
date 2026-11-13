"""The shape of one ``Goal.progress_history`` entry.

Every progress writer appends one of these (``core/services/goals/
progress_history.py``); the report's ``goals_progressed`` counts its progress
events by ``date``, and the goal page lists them all. The node stores the list
as one JSON string, so the fields are the JSON-ready spellings: an ISO datetime,
the figure, and the learner's note when they wrote one.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class ProgressHistoryEntry(TypedDict):
    """One entry: when (ISO datetime), the figure, and the learner's note.

    ``note`` is present only where the learner wrote one, on the progress form.
    ``note_only`` is present, and true, only on an entry recording a note written
    without moving the figure: ``progress_percentage`` is the figure as it stood,
    and the entry is something the learner said, not a progress event, so the
    report does not count it. ``progress_percentage`` is ``None`` on an entry the
    2026-09 history seed wrote for a goal stamped with no figure.
    """

    date: str
    progress_percentage: float | None
    note: NotRequired[str]
    note_only: NotRequired[bool]


__all__ = ["ProgressHistoryEntry"]
