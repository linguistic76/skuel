"""The exercise-and-version label of a turn-in — "The Gentle Return · v3".

The title of a turn-in is the student's (Submit & Share arc PR 7 ruling); which
exercise it answers, and which attempt it is, is read from the turn-in snapshot
(``turn_in_exercise_title`` / ``turn_in_revision``, or a row's
``exercise_title`` / ``revision``) and printed beside the title by every surface
that lists or opens a turn-in. One renderer, so the words are the same on the
teacher's queue, the review page, the student's history, the GradeBook page, the
PathStep page and the recipient card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import Span

from ui.feedback import Badge, BadgeT
from ui.layout import Size

if TYPE_CHECKING:
    from fasthtml.common import FT

VERSION_SEPARATOR = " · "


def turn_in_label(exercise_title: str | None, revision: int | None) -> str | None:
    """ "<exercise> · v<N>", the exercise alone, or ``None`` when the row is not a turn-in."""
    title = (exercise_title or "").strip()
    if not title:
        return None
    if revision is None:
        return title
    return f"{title}{VERSION_SEPARATOR}v{revision}"


def TurnInBadge(exercise_title: str | None, revision: int | None, *, cls: str = "") -> FT | str:
    """The label as an outline badge, or nothing for a row that is not a turn-in."""
    label = turn_in_label(exercise_title, revision)
    if label is None:
        return ""
    return Badge(label, variant=BadgeT.outline, size=Size.sm, cls=cls)


def TurnInNote(exercise_title: str | None, revision: int | None, *, cls: str = "") -> Span | str:
    """The label as a muted inline note ("for The Gentle Return · v3"), or nothing."""
    label = turn_in_label(exercise_title, revision)
    if label is None:
        return ""
    return Span(f"for {label}", cls=f"text-xs text-muted-foreground {cls}".strip())


__all__ = ["VERSION_SEPARATOR", "TurnInBadge", "TurnInNote", "turn_in_label"]
