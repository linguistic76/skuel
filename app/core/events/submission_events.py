"""
Submission Domain Events
========================

Events published when submission operations occur.

These events enable:
- Processing pipeline trigger when submissions are created
- User context updates when content is processed
- Submission lifecycle tracking
- Cross-service coordination

Version: 2.0.0
Date: 2026-02-16
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class SubmissionCreated(BaseEvent):
    """
    Published when a new submission file is created.

    Triggers:
    - Processing pipeline to start processing the file
    - User activity tracking
    - Submission lifecycle monitoring
    """

    submission_uid: str
    user_uid: str
    entity_type: str  # EntityType enum value
    occurred_at: datetime
    # File fields - optional (journals don't have files)
    processor_type: str | None = None  # ProcessorType enum value
    file_size: int | None = None
    file_type: str | None = None
    original_filename: str | None = None
    fulfills_exercise_uid: str | None = (
        None  # Exercise UID when submission fulfills an assigned exercise
    )
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.created"


@dataclass(frozen=True)
class SubmissionProcessingStarted(BaseEvent):
    """
    Published when processing begins for a submission.

    Triggers:
    - User notification that processing has started
    - Progress tracking updates
    """

    submission_uid: str
    user_uid: str
    processor_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.processing_started"


@dataclass(frozen=True)
class SubmissionProcessingCompleted(BaseEvent):
    """
    Published when processing completes successfully.

    Triggers:
    - User notification that content is ready
    - User context invalidation (new journal/content available)
    - Related entity creation (journals, transcripts, etc.)
    """

    submission_uid: str
    user_uid: str
    entity_type: str
    has_processed_content: bool
    processing_duration_seconds: float | None
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.processing_completed"


@dataclass(frozen=True)
class SubmissionProcessingFailed(BaseEvent):
    """
    Published when processing fails.

    Triggers:
    - User notification of failure
    - Error logging and monitoring
    - Retry scheduling (if applicable)
    """

    submission_uid: str
    user_uid: str
    error_message: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.processing_failed"


@dataclass(frozen=True)
class SubmissionDeleted(BaseEvent):
    """
    Published when a submission is deleted.

    Triggers:
    - File cleanup operations
    - User context updates
    - Storage reclamation
    """

    submission_uid: str
    user_uid: str
    entity_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.deleted"


@dataclass(frozen=True)
class ReportSubmitted(BaseEvent):
    """
    Published when a teacher submits written feedback on a submission.

    Distinct from SubmissionApproved: this fires when the teacher writes
    feedback text (creating a SUBMISSION_REPORT entity) but the submission
    is not necessarily approved. The student is informed their work has
    been reviewed and feedback is waiting.

    Triggers:
    - "feedback_received" notification to student
    - Submission status set to COMPLETED (teacher reviewed)

    report_uid is first-class (not buried in metadata) because it is
    the primary reference the notification handler needs.

    See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
    """

    submission_uid: str
    teacher_uid: str
    student_uid: str
    report_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.report_submitted"


@dataclass(frozen=True)
class SubmissionApproved(BaseEvent):
    """
    Published when a teacher explicitly approves a submission.

    Distinct from ReportSubmitted: approval is the definitive "this
    work is good enough" signal. It triggers mastery updates for any
    Ku nodes linked via APPLIES_KNOWLEDGE and carries mastered_ku_count
    so the notification handler can produce a richer message when the
    student has levelled up.

    Triggers:
    - "submission_approved" notification to student (with mastery count)
    - Submission status set to COMPLETED
    - MASTERED relationships updated (score=0.8) for linked Ku nodes

    See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
    """

    submission_uid: str
    teacher_uid: str
    student_uid: str
    occurred_at: datetime
    mastered_ku_count: int = 0
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.approved"


@dataclass(frozen=True)
class AssessmentCreated(BaseEvent):
    """
    Published when a teacher creates an assessment for a student.

    Triggers:
    - Student notification
    - Auto-sharing with student
    """

    submission_uid: str
    teacher_uid: str
    subject_uid: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.assessment_created"


@dataclass(frozen=True)
class ActivitySnapshotAccessed(BaseEvent):
    """
    Published when an admin accesses a user's activity snapshot for review.

    Enables:
    - Audit trail of admin data access (when, who accessed, whose data)
    - Future user notification when Messaging system is implemented
    - Trust and transparency: users can query their own audit log

    See: ADR-042 (Privacy as First-Class Citizen)
    See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
    """

    subject_uid: str  # User whose activity data was accessed
    admin_uid: str  # Admin who accessed the data
    time_period: str  # Time window reviewed (e.g. "7d")
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "activity.snapshot_accessed"


@dataclass(frozen=True)
class SubmissionRevisionRequested(BaseEvent):
    """
    Published when a teacher requests revision on a submission.

    Triggers:
    - Student notification
    - Submission status update to REVISION_REQUESTED

    See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
    """

    submission_uid: str
    teacher_uid: str
    student_uid: str
    occurred_at: datetime
    revision_notes: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.revision_requested"


@dataclass(frozen=True)
class RevisedExerciseCreated(BaseEvent):
    """
    Published when a teacher creates a RevisedExercise for a student.

    Triggers:
    - Student notification that revision instructions are available
    - Learning loop progression tracking
    """

    revised_exercise_uid: str
    teacher_uid: str
    student_uid: str
    original_exercise_uid: str
    report_uid: str
    revision_number: int
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "revised_exercise.created"
