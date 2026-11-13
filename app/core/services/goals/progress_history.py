"""The goal's progress history — every progress event, appended by its writer.

``Goal.progress_history`` is the persisted record a period report counts from:
``last_progress_update`` is a single stamp every later write overwrites, so a
September report generated in October would read zero for a goal progressed in
both months. Each writer that moves ``progress_percentage`` — the manual door,
the milestone door, the habit- and task-completion propagations, an intent
carrying a figure through the core update, the reopen reset (a completed goal
whose percentage is the measure, back to non-terminal: 100% → 0%) and the
reopen recompute (any other type, back to its measure's figure) — appends one
entry beside the stamp, from the goal it read (the append is a read-modify-write
of one JSON property; a writer that plans under the goal's lock keeps a racing
append, and the core update's pre-read last-writer-wins, a personal record's
acceptable odds). The manual door dates its entry at the ``update_date`` the
caller supplies, so a correction entered later lands in the period it belongs
to, and carries the note the learner wrote on the progress form. A note written
without moving the figure is an entry marked ``note_only``: something the
learner said, which the report does not count as progress.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from core.models.goal.progress_history import ProgressHistoryEntry

if TYPE_CHECKING:
    from core.models.goal.goal import Goal


def progress_entry(
    figure: float | None, at: datetime, note: str = "", *, note_only: bool = False
) -> ProgressHistoryEntry:
    """One entry: the figure, when, the learner's note if any, and whether it records
    the note alone (the figure unmoved)."""
    entry = ProgressHistoryEntry(date=at.isoformat(), progress_percentage=figure)
    if note:
        entry["note"] = note
    if note_only:
        entry["note_only"] = True
    return entry


def is_progress_event(entry: ProgressHistoryEntry) -> bool:
    """Whether an entry records the figure moving, the event a report counts; a note
    written alone is not one."""
    return not entry.get("note_only", False)


def with_progress_entry(
    goal: Goal | None,
    figure: float | None,
    at: datetime,
    note: str = "",
    *,
    note_only: bool = False,
) -> list[ProgressHistoryEntry]:
    """The goal's history with this event appended — the list the write persists.

    ``goal`` is the writer's read (``None`` when it had none, which starts the
    history); its entries were written in this record shape and are carried as
    read-only views, so they are copied out into plain records. ``note_only``
    marks a note written without moving the figure (``figure`` is then the
    figure as it stood).
    """
    existing = [
        cast("ProgressHistoryEntry", dict(entry))
        for entry in (goal.progress_history if goal is not None else ())
    ]
    return [*existing, progress_entry(figure, at, note, note_only=note_only)]


__all__ = ["is_progress_event", "progress_entry", "with_progress_entry"]
