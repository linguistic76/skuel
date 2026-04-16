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
from typing import Any

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


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
    user_uid: UserUID
    entity_type: str  # EntityType enum value
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
    user_uid: UserUID
    processor_type: str
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
    user_uid: UserUID
    entity_type: str
    has_processed_content: bool
    processing_duration_seconds: float | None
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
    user_uid: UserUID
    error_message: str
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
    user_uid: UserUID
    entity_type: str
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "submission.deleted"


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
    See: /docs/architecture/REPORT_ARCHITECTURE.md
    """

    subject_uid: str  # User whose activity data was accessed
    admin_uid: str  # Admin who accessed the data
    time_period: str  # Time window reviewed (e.g. "7d")

    @property
    def event_type(self) -> str:
        return "activity.snapshot_accessed"
