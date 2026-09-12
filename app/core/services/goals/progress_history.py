"""The goal's progress history — every progress event, appended by its writer.

``Goal.progress_history`` is the persisted record a period report counts from:
``last_progress_update`` is a single stamp every later write overwrites, so a
September report generated in October would read zero for a goal progressed in
both months. Each writer that moves ``progress_percentage`` — the manual door,
the milestone door, the habit- and task-completion propagations, and an intent
carrying a figure through the core update — appends one entry beside the
stamp, from the goal it pre-read (the append is a read-modify-write of one JSON
property; two writers racing the same goal last-writer-win on the list, a
personal record's acceptable odds).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.goal.goal import Goal


def progress_entry(figure: float | None, at: datetime) -> dict[str, Any]:
    """One progress event: the figure written and when."""
    return {"date": at.isoformat(), "progress_percentage": figure}


def with_progress_entry(
    goal: Goal | None, figure: float | None, at: datetime
) -> list[dict[str, Any]]:
    """The goal's history with this event appended — the list the write persists.

    ``goal`` is the writer's pre-read (``None`` when it had none, which starts
    the history); its entries are read-only views and are copied out.
    """
    existing = [dict(entry) for entry in (goal.progress_history if goal is not None else ())]
    return [*existing, progress_entry(figure, at)]


__all__ = ["progress_entry", "with_progress_entry"]
