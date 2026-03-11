"""
Transcription Enums - Single Source of Truth
=============================================

Per One Path Forward: One definition, imported everywhere.

February 2026 cleanup: Deleted 4 dead enums (ProcessingStatus, AudioFormat,
TranscriptionService, LanguageCode) that were only consumed by the deleted
three-tier transcription models.
"""

from enum import StrEnum


class TranscriptionStatus(StrEnum):
    """Processing status for transcription."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    def is_terminal(self) -> bool:
        """Check if status is terminal (no more processing)."""
        return self in (TranscriptionStatus.COMPLETED, TranscriptionStatus.FAILED)

    def can_retry(self) -> bool:
        """Check if transcription can be retried."""
        return self == TranscriptionStatus.FAILED
