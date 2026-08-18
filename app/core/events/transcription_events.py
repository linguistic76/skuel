"""
Transcription Domain Events
============================

Events for the transcription domain, enabling loose coupling
with downstream services like UserEntryProcessingService.

Event-Driven Architecture:
- TranscriptionCompleted → UserEntryProcessingService finishes the
  TRANSCRIBE / TRANSCRIBE_AND_STRUCTURE pipeline for the source UserEntry
- TranscriptionFailed → Monitoring/alerting can respond

This replaces direct coupling between TranscriptionService and UserEntry processing.
"""

from dataclasses import dataclass
from typing import ClassVar

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


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
    user_uid: UserUID
    transcript_text: str
    audio_file_path: str
    confidence_score: float
    duration_seconds: float
    word_count: int

    event_type: ClassVar[str] = "transcription.completed"


@dataclass(frozen=True)
class TranscriptionFailed(BaseEvent):
    """
    Published when a transcription fails.

    Subscribers:
    - MonitoringService: Can alert on failures
    - RetryService: Can schedule retry
    """

    transcription_uid: str
    user_uid: UserUID
    error_message: str
    audio_file_path: str

    event_type: ClassVar[str] = "transcription.failed"


@dataclass(frozen=True)
class TranscriptionCreated(BaseEvent):
    """
    Published when a new transcription is created (before processing).

    Subscribers:
    - ProcessingQueue: Can queue for processing
    """

    transcription_uid: str
    user_uid: UserUID
    audio_file_path: str

    event_type: ClassVar[str] = "transcription.created"


__all__ = [
    "TranscriptionCompleted",
    "TranscriptionCreated",
    "TranscriptionFailed",
]
