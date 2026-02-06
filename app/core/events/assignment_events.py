"""
Assignment Domain Events
=========================

Events published when teacher assignment operations occur.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class AssignmentCreated(BaseEvent):
    """
    Published when a teacher creates an assigned ReportProject.

    Triggers:
    - Notification to group members
    - Calendar integration (due date)
    """

    project_uid: str
    teacher_uid: str
    group_uid: str
    project_name: str
    occurred_at: datetime
    due_date: str | None = None  # ISO format date string
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.created"


@dataclass(frozen=True)
class AssignmentSubmitted(BaseEvent):
    """
    Published when a student submits a report for an assignment.

    Triggers:
    - Teacher notification (new submission in review queue)
    - Progress tracking
    """

    report_uid: str
    project_uid: str
    student_uid: str
    teacher_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.submitted"
