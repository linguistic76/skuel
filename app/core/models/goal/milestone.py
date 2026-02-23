"""
Milestone — Goal Progress Checkpoint
======================================

A progress checkpoint within a Goal. Milestones divide a goal into
measurable sub-targets with dates.

Stored as a tuple on the Goal: `milestones: tuple[Milestone, ...]`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True)
class Milestone:
    """
    A progress checkpoint within a GOAL.

    Fields:
        uid: Unique identifier within the goal
        title: Short milestone description
        description: Detailed description (optional)
        target_date: When this milestone should be achieved
        target_value: Numeric target (optional, for measurable milestones)
        achieved_date: When actually achieved (None if not yet)
        is_completed: Whether this milestone is done
        required_knowledge_uids: KU UIDs needed to reach this milestone
        unlocked_knowledge_uids: KU UIDs unlocked by achieving this milestone
    """

    uid: str
    title: str
    description: str | None = None
    target_date: date | None = None
    target_value: float | None = None
    achieved_date: date | None = None  # type: ignore[assignment]
    is_completed: bool = False
    required_knowledge_uids: tuple[str, ...] = ()
    unlocked_knowledge_uids: tuple[str, ...] = ()
