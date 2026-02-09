"""
Transcription Domain Model - Simplified
========================================

Minimal model for audio transcription: audio file → Deepgram → text.

ARCHITECTURE DECISION (December 2025):
This replaces the over-engineered 48-field TranscriptionPure with a focused model.
The transcription domain has ONE job: convert audio to text.

Fields: Only what's needed for the core workflow.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums.transcription_enums import TranscriptionStatus


@dataclass(frozen=True)
class Transcription:
    """
    Immutable transcription domain model.

    Core fields only - what's needed for: audio file → Deepgram → text.
    Additional metadata stored in `metadata` dict if needed.
    """

    # Identity
    uid: str

    # Audio source
    audio_file_path: str
    original_filename: str | None = None

    # Processing state
    status: TranscriptionStatus = TranscriptionStatus.PENDING
    error_message: str | None = None

    # Result
    transcript_text: str = ""
    confidence_score: float | None = None
    word_count: int = 0
    duration_seconds: float | None = None

    # Ownership
    user_uid: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Extensible metadata (for anything else)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Calculate word count if transcript provided."""
        if self.transcript_text and self.word_count == 0:
            # Use object.__setattr__ for frozen dataclass
            object.__setattr__(self, "word_count", len(self.transcript_text.split()))

    # ========================================================================
    # STATUS HELPERS
    # ========================================================================

    def is_pending(self) -> bool:
        """Check if transcription is pending."""
        return self.status == TranscriptionStatus.PENDING

    def is_processing(self) -> bool:
        """Check if transcription is being processed."""
        return self.status == TranscriptionStatus.PROCESSING

    def is_completed(self) -> bool:
        """Check if transcription completed successfully."""
        return self.status == TranscriptionStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if transcription failed."""
        return self.status == TranscriptionStatus.FAILED

    def can_process(self) -> bool:
        """Check if transcription can be sent for processing."""
        return self.status == TranscriptionStatus.PENDING

    def can_retry(self) -> bool:
        """Check if transcription can be retried."""
        return self.status == TranscriptionStatus.FAILED

    # ========================================================================
    # SERIALIZATION
    # ========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "uid": self.uid,
            "audio_file_path": self.audio_file_path,
            "original_filename": self.original_filename,
            "status": self.status.value,
            "error_message": self.error_message,
            "transcript_text": self.transcript_text,
            "confidence_score": self.confidence_score,
            "word_count": self.word_count,
            "duration_seconds": self.duration_seconds,
            "user_uid": self.user_uid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transcription":
        """Create from dictionary."""
        # Handle status enum
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = TranscriptionStatus(status)

        # Handle datetime fields
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()

        return cls(
            uid=data["uid"],
            audio_file_path=data.get("audio_file_path", ""),
            original_filename=data.get("original_filename"),
            status=status,
            error_message=data.get("error_message"),
            transcript_text=data.get("transcript_text", ""),
            confidence_score=data.get("confidence_score"),
            word_count=data.get("word_count", 0),
            duration_seconds=data.get("duration_seconds"),
            user_uid=data.get("user_uid"),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
        )


# ============================================================================
# REQUEST MODELS (Pydantic for validation at boundaries)
# ============================================================================

from pydantic import BaseModel, Field  # noqa: E402


class TranscriptionCreateRequest(BaseModel):
    """Request to create a new transcription."""

    audio_file_path: str = Field(..., description="Path to audio file")
    original_filename: str | None = Field(None, description="Original filename")
    language: str = Field("en", description="Language code for transcription")
    model: str = Field("nova-2", description="Deepgram model to use")

    model_config = {"extra": "forbid"}


class TranscriptionProcessOptions(BaseModel):
    """Options for processing transcription."""

    language: str = Field("en", description="Language code")
    model: str = Field("nova-2", description="Deepgram model")
    punctuate: bool = Field(True, description="Enable punctuation")
    paragraphs: bool = Field(True, description="Enable paragraph detection")
    diarize: bool = Field(False, description="Enable speaker diarization")

    model_config = {"extra": "forbid"}


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "Transcription",
    "TranscriptionCreateRequest",
    "TranscriptionProcessOptions",
    "TranscriptionStatus",
]
