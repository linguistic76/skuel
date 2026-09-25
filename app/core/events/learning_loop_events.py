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
from typing import Any, ClassVar

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

    event_type: ClassVar[str] = "submission.report_submitted"


@dataclass(frozen=True)
class EntryReportGenerated(BaseEvent):
    """Published when an AI EntryReport is persisted for an exercise turn-in.

    The AI-report counterpart of ``ReportSubmitted`` (which stays
    teacher-specific — its notification semantics say "your teacher reviewed
    this"). Subscribers that care about "a report now exists" regardless of
    author — e.g. the ADR-051 InteractionResult handler — listen to both.

    ``source`` carries the ``ReportSource`` enum value (``llm`` today; the
    journal-response path does not publish — journal entries are not
    turn-ins and have no Interaction record).
    """

    entry_uid: str
    report_uid: str
    student_uid: str
    source: str
    metadata: dict[str, Any] | None = None

    event_type: ClassVar[str] = "entry_report.generated"


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

    event_type: ClassVar[str] = "user_entry.approved"


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

    event_type: ClassVar[str] = "user_entry.revision_requested"


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

    event_type: ClassVar[str] = "revised_exercise.created"


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

    event_type: ClassVar[str] = "activity.snapshot_accessed"


@dataclass(frozen=True)
class ActivityReportWritten(BaseEvent):
    """Published when an admin writes an activity report about a user.

    The report is owned by its subject (Submit & Share arc R11); this event rings the
    subject's bell. It is not ``ReportSubmitted`` — that event is a teacher's
    EntryReport on a turn-in, and its subscribers (learning-loop tracking, the
    Interaction result handler) read turn-in identity this report has none of.

    See: /docs/roadmap/submission-sharing-arc.md (R10, R11); /docs/decisions/ADR-088-submit-and-share.md §1
    """

    report_uid: str  # the ActivityReport
    subject_uid: str  # the user the report is about — its owner, and who is rung
    author_uid: str  # the admin who wrote it (``created_by`` on the report)
    time_period: str  # the report-period token reviewed

    event_type: ClassVar[str] = "activity.report_written"
