"""
Assignment Domain Events
========================

Events published when assignment operations occur.

These events enable:
- Processing pipeline trigger when assignments are submitted
- User context updates when content is processed
- Assignment lifecycle tracking
- Cross-service coordination

Version: 1.0.0
Date: 2025-11-08
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class AssignmentSubmitted(BaseEvent):
    """
    Published when a new assignment file is submitted.

    Triggers:
    - Processing pipeline to start processing the file
    - User activity tracking
    - Assignment lifecycle monitoring
    """

    assignment_uid: str
    user_uid: str
    assignment_type: str  # AssignmentType enum value
    processor_type: str  # ProcessorType enum value
    file_size: int
    file_type: str
    original_filename: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.submitted"


@dataclass(frozen=True)
class AssignmentProcessingStarted(BaseEvent):
    """
    Published when processing begins for an assignment.

    Triggers:
    - User notification that processing has started
    - Progress tracking updates
    """

    assignment_uid: str
    user_uid: str
    processor_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.processing_started"


@dataclass(frozen=True)
class AssignmentProcessingCompleted(BaseEvent):
    """
    Published when processing completes successfully.

    Triggers:
    - User notification that content is ready
    - User context invalidation (new journal/content available)
    - Related entity creation (journals, transcripts, etc.)
    """

    assignment_uid: str
    user_uid: str
    assignment_type: str
    has_processed_content: bool
    processing_duration_seconds: float | None
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.processing_completed"


@dataclass(frozen=True)
class AssignmentProcessingFailed(BaseEvent):
    """
    Published when processing fails.

    Triggers:
    - User notification of failure
    - Error logging and monitoring
    - Retry scheduling (if applicable)
    """

    assignment_uid: str
    user_uid: str
    error_message: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.processing_failed"


@dataclass(frozen=True)
class AssignmentDeleted(BaseEvent):
    """
    Published when an assignment is deleted.

    Triggers:
    - File cleanup operations
    - User context updates
    - Storage reclamation
    """

    assignment_uid: str
    user_uid: str
    assignment_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "assignment.deleted"
