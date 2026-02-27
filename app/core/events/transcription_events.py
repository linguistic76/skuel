"""
Transcription Domain Events
============================

Events for the transcription domain, enabling loose coupling
with downstream services like SubmissionsCoreService.

Event-Driven Architecture:
- TranscriptionCompleted → SubmissionsCoreService creates journal-type Report from transcript
- TranscriptionFailed → Monitoring/alerting can respond

This replaces direct coupling between TranscriptionService and SubmissionsCoreService.
"""

from dataclasses import dataclass
from datetime import datetime

from core.events.base import BaseEvent


@dataclass(frozen=True)
class TranscriptionCompleted(BaseEvent):
    """
    Published when a transcription completes successfully.

    Subscribers:
    - SubmissionsCoreService: Creates journal-type Report from transcript
    - AnalyticsService: Can update transcription metrics
    - UserContextService: Can invalidate user context cache
    """

    transcription_uid: str
    user_uid: str
    transcript_text: str
    audio_file_path: str
    confidence_score: float
    duration_seconds: float
    word_count: int
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "transcription.completed"


@dataclass(frozen=True)
class TranscriptionFailed(BaseEvent):
    """
    Published when a transcription fails.

    Subscribers:
    - MonitoringService: Can alert on failures
    - RetryService: Can schedule retry
    """

    transcription_uid: str
    user_uid: str
    error_message: str
    audio_file_path: str
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "transcription.failed"


@dataclass(frozen=True)
class TranscriptionCreated(BaseEvent):
    """
    Published when a new transcription is created (before processing).

    Subscribers:
    - ProcessingQueue: Can queue for processing
    """

    transcription_uid: str
    user_uid: str
    audio_file_path: str
    occurred_at: datetime

    @property
    def event_type(self) -> str:
        return "transcription.created"


__all__ = [
    "TranscriptionCompleted",
    "TranscriptionCreated",
    "TranscriptionFailed",
]
