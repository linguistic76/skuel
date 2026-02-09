"""
Transcription Pure Domain Models
=================================

Pure, immutable domain models for Transcription (Tier 3 of three-tier architecture).
Frozen dataclasses with business logic, no framework dependencies.

ARCHITECTURAL ALIGNMENT (November 2, 2025):
-------------------------------------------
✅ FLATTENED MODEL - Aligned with UniversalNeo4jBackend pattern
- Removed nested value objects (AudioMetadata, TranscriptionMetrics)
- All fields are Neo4j primitives (string, int, float, bool, arrays)
- Automatic serialization via UniversalNeo4jBackend
- Consistent with other 10+ SKUEL domains

Migration from nested structure completed to fix Neo4j serialization errors.
"""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

# Transcription enums consolidated in /core/models/enums/transcription_enums.py (January 2026)
from core.models.enums.transcription_enums import (
    AudioFormat,
    LanguageCode,
    ProcessingStatus,
    TranscriptionService,
)

# ============================================================================
# TRANSCRIPTION PURE MODEL (FLATTENED)
# ============================================================================


@dataclass(frozen=True)
class TranscriptionPure:
    """
    Pure immutable transcription domain model.

    FLATTENED STRUCTURE (November 2, 2025):
    - All nested objects removed
    - Neo4j primitive types only
    - Automatic serialization via UniversalNeo4jBackend

    Represents an audio transcription with associated metadata and processing results.
    All fields are immutable - use factory methods or dataclasses.replace() to create modified copies.
    """

    # ========================================================================
    # IDENTITY
    # ========================================================================

    uid: str

    # ========================================================================
    # AUDIO FILE INFORMATION
    # ========================================================================

    audio_file_path: str
    original_filename: str | None = None

    # Audio metadata (flattened from AudioMetadata value object)
    audio_format: AudioFormat | str = AudioFormat.MP3
    audio_duration_seconds: float | None = None
    audio_file_size_bytes: int | None = None
    audio_sample_rate: int | None = None
    audio_bit_rate: int | None = None
    audio_channels: int | None = None
    audio_encoding: str | None = None

    # ========================================================================
    # TRANSCRIPTION RESULTS
    # ========================================================================

    transcript_text: str = ""
    processing_status: ProcessingStatus | str = ProcessingStatus.PENDING

    # Transcription metrics (flattened from TranscriptionMetrics value object)
    processing_time_ms: float | None = None
    confidence_score: float | None = None
    word_count: int = 0
    speaking_rate_wpm: float = 0.0
    silence_ratio: float | None = None

    # ========================================================================
    # PROCESSING INFORMATION
    # ========================================================================

    processing_attempts: int = 0
    error_message: str | None = None

    # ========================================================================
    # ANALYSIS RESULTS (Arrays - allowed in Neo4j)
    # ========================================================================

    speakers: list[str] = None  # type: ignore[assignment]
    paragraphs: list[str] = None  # type: ignore[assignment]
    sentences: list[str] = None  # type: ignore[assignment]

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    service: TranscriptionService | str = TranscriptionService.DEEPGRAM
    model: str | None = None
    language: LanguageCode | str = LanguageCode.EN
    enable_diarization: bool = False
    enable_punctuation: bool = True
    enable_paragraphs: bool = True
    custom_vocabulary: list[str] = None  # type: ignore[assignment]

    # ========================================================================
    # METADATA
    # ========================================================================

    tags: list[str] = None  # type: ignore[assignment]
    notes: str | None = None
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # ========================================================================
    # AUDIT FIELDS
    # ========================================================================

    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    created_by: str | None = None
    user_uid: str | None = None  # Owner (REQUIRED for entity ownership)

    def __post_init__(self) -> None:
        """Initialize default values for mutable fields"""
        if self.speakers is None:
            object.__setattr__(self, "speakers", [])
        if self.paragraphs is None:
            object.__setattr__(self, "paragraphs", [])
        if self.sentences is None:
            object.__setattr__(self, "sentences", [])
        if self.custom_vocabulary is None:
            object.__setattr__(self, "custom_vocabulary", [])
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ========================================================================
    # DOMAIN METHODS (Updated for flattened structure)
    # ========================================================================

    def with_status(self, status: ProcessingStatus) -> "TranscriptionPure":
        """Create new transcription with updated status"""
        return replace(self, processing_status=status, updated_at=datetime.now())

    def mark_as_failed(self, error_message: str) -> "TranscriptionPure":
        """Mark transcription as failed with error message"""
        return replace(
            self,
            processing_status=ProcessingStatus.FAILED,
            error_message=error_message,
            updated_at=datetime.now(),
        )

    def with_transcript(
        self,
        transcript_text: str,
        confidence_score: float | None = None,
        word_count: int | None = None,
        speaking_rate_wpm: float | None = None,
        processing_time_ms: float | None = None,
    ) -> "TranscriptionPure":
        """Update transcription with transcript text and metrics"""
        updates = {
            "transcript_text": transcript_text,
            "processing_status": ProcessingStatus.TRANSCRIBED,
            "updated_at": datetime.now(),
        }
        if confidence_score is not None:
            updates["confidence_score"] = confidence_score
        if word_count is not None:
            updates["word_count"] = word_count
        if speaking_rate_wpm is not None:
            updates["speaking_rate_wpm"] = speaking_rate_wpm
        if processing_time_ms is not None:
            updates["processing_time_ms"] = processing_time_ms

        return replace(self, **updates)

    def increment_attempts(self) -> "TranscriptionPure":
        """Increment processing attempts counter"""
        return replace(
            self, processing_attempts=self.processing_attempts + 1, updated_at=datetime.now()
        )

    # ========================================================================
    # DOMAIN LOGIC
    # ========================================================================

    def is_successful(self) -> bool:
        """Check if transcription was successful"""
        status = self.processing_status
        if isinstance(status, str):
            status = ProcessingStatus(status)
        return status in [ProcessingStatus.TRANSCRIBED, ProcessingStatus.COMPLETED]

    def is_failed(self) -> bool:
        """Check if transcription failed"""
        status = self.processing_status
        if isinstance(status, str):
            status = ProcessingStatus(status)
        return status == ProcessingStatus.FAILED

    def is_processing(self) -> bool:
        """Check if currently being processed"""
        status = self.processing_status
        if isinstance(status, str):
            status = ProcessingStatus(status)
        return status in [
            ProcessingStatus.TRANSCRIBING,
            ProcessingStatus.ANALYZING,
            ProcessingStatus.EXTRACTING,
        ]

    def has_multiple_speakers(self) -> bool:
        """Check if multiple speakers were detected"""
        return len(self.speakers) > 1

    def get_word_count(self) -> int:
        """Get word count from field or calculate from transcript"""
        if self.word_count > 0:
            return self.word_count
        return len(self.transcript_text.split()) if self.transcript_text else 0

    def get_duration_minutes(self) -> float:
        """Get audio duration in minutes (from flattened audio_duration_seconds)"""
        return (self.audio_duration_seconds / 60) if self.audio_duration_seconds else 0.0

    def get_file_size_mb(self) -> float:
        """Get file size in megabytes (from flattened audio_file_size_bytes)"""
        return (self.audio_file_size_bytes / (1024 * 1024)) if self.audio_file_size_bytes else 0.0

    def is_stereo(self) -> bool:
        """Check if audio is stereo (from flattened audio_channels)"""
        return self.audio_channels == 2 if self.audio_channels else False

    def get_speaking_rate(self) -> float:
        """Get speaking rate (words per minute)"""
        if self.speaking_rate_wpm > 0:
            return self.speaking_rate_wpm

        duration_minutes = self.get_duration_minutes()
        if duration_minutes > 0:
            return self.get_word_count() / duration_minutes
        return 0.0

    def get_confidence_score(self) -> float | None:
        """Get confidence score if available"""
        return self.confidence_score

    def get_processing_time_seconds(self) -> float:
        """Get processing time in seconds"""
        return (self.processing_time_ms / 1000) if self.processing_time_ms else 0.0

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if transcription has high confidence"""
        return self.confidence_score >= threshold if self.confidence_score else False

    def needs_retry(self, max_attempts: int = 3) -> bool:
        """Check if transcription should be retried"""
        return self.is_failed() and self.processing_attempts < max_attempts

    def get_processing_summary(self) -> dict[str, Any]:
        """Get summary of processing information"""
        status_val = (
            self.processing_status.value
            if isinstance(self.processing_status, Enum)
            else self.processing_status
        )
        service_val = self.service.value if isinstance(self.service, Enum) else self.service
        language_val = self.language.value if isinstance(self.language, Enum) else self.language

        return {
            "status": status_val,
            "is_successful": self.is_successful(),
            "attempts": self.processing_attempts,
            "service": service_val,
            "language": language_val,
            "word_count": self.get_word_count(),
            "duration_minutes": self.get_duration_minutes(),
            "speaking_rate_wpm": self.get_speaking_rate(),
            "confidence": self.get_confidence_score(),
            "has_multiple_speakers": self.has_multiple_speakers(),
            "speaker_count": len(self.speakers),
        }


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_transcription(
    uid: str,
    audio_file_path: str,
    original_filename: str | None = None,
    user_uid: str | None = None,
    service: TranscriptionService = TranscriptionService.DEEPGRAM,
    language: LanguageCode = LanguageCode.EN,
    tags: list[str] | None = None,
) -> TranscriptionPure:
    """Factory function to create a new transcription"""
    return TranscriptionPure(
        uid=uid,
        audio_file_path=audio_file_path,
        original_filename=original_filename,
        user_uid=user_uid,
        service=service,
        language=language,
        tags=tags or [],
        processing_status=ProcessingStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_transcription_with_audio_metadata(
    uid: str,
    audio_file_path: str,
    audio_format: AudioFormat,
    audio_duration_seconds: float,
    audio_file_size_bytes: int,
    original_filename: str | None = None,
    user_uid: str | None = None,
    audio_sample_rate: int | None = None,
    audio_bit_rate: int | None = None,
    audio_channels: int | None = None,
    service: TranscriptionService = TranscriptionService.DEEPGRAM,
    language: LanguageCode = LanguageCode.EN,
) -> TranscriptionPure:
    """Factory function to create a transcription with audio metadata (flattened)"""
    return TranscriptionPure(
        uid=uid,
        audio_file_path=audio_file_path,
        original_filename=original_filename,
        user_uid=user_uid,
        # Flattened audio metadata
        audio_format=audio_format,
        audio_duration_seconds=audio_duration_seconds,
        audio_file_size_bytes=audio_file_size_bytes,
        audio_sample_rate=audio_sample_rate,
        audio_bit_rate=audio_bit_rate,
        audio_channels=audio_channels,
        # Configuration
        service=service,
        language=language,
        processing_status=ProcessingStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
