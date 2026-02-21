"""
Exercise Domain Events
========================

Events published when teacher exercise operations occur.

Formerly assignment_events.py — renamed per Phase 3 of Ku hierarchy refactoring.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    occurred_at: datetime
    due_date: str | None = None  # ISO format date string
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "exercise.created"


@dataclass(frozen=True)
class ExerciseSubmitted(BaseEvent):
    """
    Published when a student submits a report for an exercise.

    Triggers:
    - Teacher notification (new submission in review queue)
    - Progress tracking
    """

    report_uid: str
    exercise_uid: str
    student_uid: str
    teacher_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "exercise.submitted"
