"""
Learning Loop Events (ADR-054)
==============================

Events for the teacher-student feedback loop, relocated from the former
``core/events/submission_events.py`` during the UserEntry consolidation.
Kept events (``ReportSubmitted``, ``RevisedExerciseCreated``) retain their
names. Renamed events:

- ``SubmissionApproved`` → ``UserEntryApproved`` (``submission_uid`` →
  ``entity_uid``)
- ``SubmissionRevisionRequested`` → ``UserEntryRevisionRequested``
  (``submission_uid`` → ``entity_uid``)

Source these events from here or via ``core.events`` re-exports.
"""

from dataclasses import dataclass
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class ReportSubmitted(BaseEvent):
    """Published when a teacher writes feedback on a user entry.

    Field ``submission_uid`` is retained (not renamed to ``entity_uid``)
    for source-compatibility with the notification handler — ADR-054
    only renames the two events that took user-entry identity hits.

    See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
    """

    submission_uid: str
    teacher_uid: str
    student_uid: str
    report_uid: str
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.report_submitted"


@dataclass(frozen=True)
class UserEntryApproved(BaseEvent):
    """Published when a teacher explicitly approves a user entry.

    Renamed from ``SubmissionApproved``; ``submission_uid`` → ``entity_uid``.
    Triggers mastery updates and approval notifications.
    """

    entity_uid: str
    teacher_uid: str
    student_uid: str
    mastered_ku_count: int = 0
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "user_entry.approved"


@dataclass(frozen=True)
class UserEntryRevisionRequested(BaseEvent):
    """Published when a teacher requests revision on a user entry.

    Renamed from ``SubmissionRevisionRequested``; ``submission_uid`` →
    ``entity_uid``.
    """

    entity_uid: str
    teacher_uid: str
    student_uid: str
    revision_notes: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "user_entry.revision_requested"


@dataclass(frozen=True)
class RevisedExerciseCreated(BaseEvent):
    """Published when a teacher creates a ``RevisedExercise`` for a student."""

    revised_exercise_uid: str
    teacher_uid: str
    student_uid: str
    original_exercise_uid: str
    report_uid: str
    revision_number: int
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "revised_exercise.created"


@dataclass(frozen=True)
class AssessmentCreated(BaseEvent):
    """Published when a teacher creates an assessment for a student.

    Relocated from ``submission_events.py`` during ADR-054 pre-6b sweep;
    ``submission_uid`` → ``entity_uid`` since the subject is an
    EntryReport, not a submission.
    """

    entity_uid: str
    teacher_uid: str
    subject_uid: str
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assessment.created"


@dataclass(frozen=True)
class ActivitySnapshotAccessed(BaseEvent):
    """Published when an admin accesses a user's activity snapshot for review.

    Enables:
    - Audit trail of admin data access
    - Future user notification when Messaging system is implemented
    - Trust and transparency: users can query their own audit log

    Relocated from ``submission_events.py`` during ADR-054 pre-6b sweep.
    See: ADR-042 (Privacy as First-Class Citizen)
    """

    subject_uid: str  # User whose activity data was accessed
    admin_uid: str  # Admin who accessed the data
    time_period: str  # Time window reviewed (e.g. "7d")

    @property
    def event_type(self) -> str:
        return "activity.snapshot_accessed"
