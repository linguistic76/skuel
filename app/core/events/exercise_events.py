"""
Exercise Domain Events
========================

Lifecycle event for teacher exercise operations.

``ExerciseCreated`` is a STAGED hook (PLANNED_EVENTS in scripts/detect_bloat.py):
the teacher-assignment notification + calendar integration it triggers is not yet
wired (no publisher, no subscriber). Its sibling ``ExerciseSubmitted`` was deleted
(campaign 17) — the student-submission moment is now published live as
``UserEntryCreated`` after the ADR-054 UserEntry collapse routed ``/submit`` through
``UserEntryService.create_entry()``.

Formerly assignment_events.py — renamed per of Ku hierarchy refactoring.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from dataclasses import dataclass
from typing import Any, ClassVar

from core.events.base import BaseEvent


@dataclass(frozen=True)
class ExerciseCreated(BaseEvent):
    """
    Published when a teacher creates an assigned Exercise.

    Triggers:
    - Notification to group members
    - Calendar integration (due date)
    """

    exercise_uid: str
    teacher_uid: str
    group_uid: str
    exercise_name: str
    due_date: str | None = None  # ISO format date string
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "exercise.created"
