"""
Report Domain Events
========================

Events published when report operations occur.

These events enable:
- Processing pipeline trigger when reports are submitted
- User context updates when content is processed
- Report lifecycle tracking
- Cross-service coordination

Version: 1.0.0
Date: 2025-11-08
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.events.base import BaseEvent


@dataclass(frozen=True)
class ReportSubmitted(BaseEvent):
    """
    Published when a new report file is submitted.

    Triggers:
    - Processing pipeline to start processing the file
    - User activity tracking
    - Report lifecycle monitoring
    """

    report_uid: str
    user_uid: str
    report_type: str  # ReportType enum value
    occurred_at: datetime
    # File fields - optional (journals don't have files)
    processor_type: str | None = None  # ProcessorType enum value
    file_size: int | None = None
    file_type: str | None = None
    original_filename: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "report.submitted"


@dataclass(frozen=True)
class ReportProcessingStarted(BaseEvent):
    """
    Published when processing begins for a report.

    Triggers:
    - User notification that processing has started
    - Progress tracking updates
    """

    report_uid: str
    user_uid: str
    processor_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "report.processing_started"


@dataclass(frozen=True)
class ReportProcessingCompleted(BaseEvent):
    """
    Published when processing completes successfully.

    Triggers:
    - User notification that content is ready
    - User context invalidation (new journal/content available)
    - Related entity creation (journals, transcripts, etc.)
    """

    report_uid: str
    user_uid: str
    report_type: str
    has_processed_content: bool
    processing_duration_seconds: float | None
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "report.processing_completed"


@dataclass(frozen=True)
class ReportProcessingFailed(BaseEvent):
    """
    Published when processing fails.

    Triggers:
    - User notification of failure
    - Error logging and monitoring
    - Retry scheduling (if applicable)
    """

    report_uid: str
    user_uid: str
    error_message: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "report.processing_failed"


@dataclass(frozen=True)
class ReportDeleted(BaseEvent):
    """
    Published when a report is deleted.

    Triggers:
    - File cleanup operations
    - User context updates
    - Storage reclamation
    """

    report_uid: str
    user_uid: str
    report_type: str
    occurred_at: datetime
    metadata: dict[str, Any] | None = None

    @property
    def event_type(self) -> str:
        return "report.deleted"
