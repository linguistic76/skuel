"""
Transcription Request Models (Pydantic)
========================================

Pydantic models for Transcription API boundaries (Tier 1 of three-tier architecture).
Handles validation and serialization at the API layer.

Based on transcription_schemas.py and search_schemas.py but aligned with three-tier pattern.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Type literals for strict validation
ProcessingStatusLiteral = Literal[
    "pending",
    "transcribing",
    "transcribed",
    "analyzing",
    "analyzed",
    "extracting",
    "completed",
    "failed",
]
AudioFormatLiteral = Literal["mp3", "wav", "m4a", "webm", "ogg", "flac"]
TranscriptionServiceLiteral = Literal["deepgram", "whisper", "google", "azure", "aws"]
LanguageCodeLiteral = Literal[
    "en", "es", "fr", "de", "it", "pt", "ru", "zh", "ja", "ko", "ar", "hi"
]


# ============================================================================
# TRANSCRIPTION REQUEST MODELS
# ============================================================================


class TranscriptionCreateRequest(BaseModel):
    """Request model for creating a transcription"""

    # Audio file information
    audio_file_path: str = Field(min_length=1, description="Path to audio file")
    original_filename: str | None = Field(
        default=None, max_length=255, description="Original filename"
    )

    # Processing configuration
    service: TranscriptionServiceLiteral = Field(
        default="deepgram", description="Transcription service"
    )
    model: str | None = Field(default=None, max_length=100, description="Specific model to use")
    language: LanguageCodeLiteral = Field(default="en", description="Expected language")
    enable_diarization: bool = Field(default=False, description="Enable speaker diarization")
    enable_punctuation: bool = Field(default=True, description="Enable punctuation")
    enable_paragraphs: bool = Field(default=True, description="Enable paragraph detection")
    custom_vocabulary: list[str] = Field(
        default_factory=list, description="Custom vocabulary words"
    )

    # Relations
    journal_uid: str | None = Field(default=None, description="Associated journal UID")

    # Additional metadata
    tags: list[str] = Field(default_factory=list, description="Tags for organization")
    notes: str | None = Field(default=None, max_length=1000, description="Processing notes")

    @field_validator("audio_file_path")
    @classmethod
    def validate_audio_path(cls, v: str) -> str:
        """Validate audio file path"""
        allowed_extensions = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"}
        if not any(v.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError(
                f"Audio file must have one of these extensions: {', '.join(allowed_extensions)}"
            )
        return v

    @field_validator("custom_vocabulary")
    @classmethod
    def validate_vocabulary(cls, v: list[str]) -> list[str]:
        """Validate custom vocabulary"""
        if len(v) > 100:
            raise ValueError("Custom vocabulary cannot exceed 100 words")
        return [word.strip().lower() for word in v if word.strip()]


class TranscriptionUpdateRequest(BaseModel):
    """Request model for updating a transcription"""

    # Core fields (optional for updates)
    transcript_text: str | None = Field(default=None, description="Transcribed text")
    processing_status: ProcessingStatusLiteral | None = Field(
        default=None, description="Processing status"
    )

    # Analysis results
    confidence_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score"
    )
    word_count: int | None = Field(default=None, ge=0, description="Word count")
    speakers: list[str] | None = Field(default=None, description="Identified speakers")
    paragraphs: list[str] | None = Field(default=None, description="Text paragraphs")
    sentences: list[str] | None = Field(default=None, description="Extracted sentences")

    # Relations
    journal_uid: str | None = Field(default=None, description="Linked journal UID")

    # Error handling
    error_message: str | None = Field(default=None, max_length=500, description="Error message")

    # Metadata
    tags: list[str] | None = Field(default=None, description="Updated tags")
    notes: str | None = Field(default=None, max_length=1000, description="Updated notes")


# ============================================================================
# PROCESSING REQUEST MODELS
# ============================================================================


class TranscriptionProcessRequest(BaseModel):
    """Request model for processing an uploaded audio file"""

    # Processing options
    service: TranscriptionServiceLiteral = Field(
        default="deepgram", description="Transcription service"
    )
    model: str | None = Field(default=None, max_length=100, description="Specific model to use")
    language: LanguageCodeLiteral = Field(default="en", description="Expected language")
    enable_diarization: bool = Field(default=False, description="Enable speaker diarization")
    enable_punctuation: bool = Field(default=True, description="Enable punctuation")
    enable_paragraphs: bool = Field(default=True, description="Enable paragraph detection")

    # Processing flags
    create_journal: bool = Field(default=False, description="Create journal from transcription")
    journal_title: str | None = Field(
        default=None, max_length=200, description="Title for created journal"
    )
    journal_category: str = Field(default="daily", description="Category for created journal")
    journal_project_uid: str | None = Field(
        default=None,
        max_length=100,
        description="UID of JournalProject for LLM processing of transcript",
    )

    # Post-processing
    extract_insights: bool = Field(default=True, description="Extract insights after transcription")
    auto_paragraph: bool = Field(default=True, description="Automatically create paragraphs")

    # Metadata
    tags: list[str] = Field(default_factory=list, description="Tags for transcription")
    notes: str | None = Field(default=None, max_length=1000, description="Processing notes")

    @field_validator("journal_title")
    @classmethod
    def validate_journal_title(cls, v: str | None, info) -> str | None:
        """Validate journal title when creating journal"""
        create_journal = info.data.get("create_journal", False)
        if create_journal and not v:
            raise ValueError("journal_title is required when create_journal is True")
        return v


class AudioProcessingRequest(BaseModel):
    """Request model for audio transcription API endpoint (simplified for routes)"""

    # Required field
    audio_file_path: str = Field(min_length=1, description="Path to the audio file to transcribe")

    # Optional fields
    title: str | None = Field(
        default=None, max_length=200, description="Title for the transcription"
    )

    create_journal: bool = Field(
        default=True, description="Whether to create a journal entry from transcription"
    )

    # Processing options (defaults match TranscriptionProcessRequest)
    language: LanguageCodeLiteral = Field(default="en", description="Expected language")
    service: TranscriptionServiceLiteral = Field(
        default="deepgram", description="Transcription service"
    )
    model: str | None = Field(default=None, description="Specific model to use")

    @field_validator("audio_file_path")
    @classmethod
    def validate_audio_path(cls, v: str) -> str:
        """Validate audio file path"""
        allowed_extensions = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"}
        if not any(v.lower().endswith(ext) for ext in allowed_extensions):
            raise ValueError(
                f"Audio file must have one of these extensions: {', '.join(allowed_extensions)}"
            )
        return v


# ============================================================================
# FILTER REQUEST MODELS
# ============================================================================


class TranscriptionFilterRequest(BaseModel):
    """Request model for filtering and searching transcriptions"""

    # Date filters
    start_date: datetime | None = Field(default=None, description="Filter from date")
    end_date: datetime | None = Field(default=None, description="Filter to date")

    # Status filters
    statuses: list[ProcessingStatusLiteral] | None = Field(default=None)
    services: list[TranscriptionServiceLiteral] | None = Field(default=None)
    languages: list[LanguageCodeLiteral] | None = Field(default=None)

    # Duration filters
    min_duration_minutes: float | None = Field(default=None, ge=0)
    max_duration_minutes: float | None = Field(default=None, gt=0)

    # Quality filters
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    max_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    # Content filters
    min_word_count: int | None = Field(default=None, ge=0)
    max_word_count: int | None = Field(default=None, gt=0)
    has_multiple_speakers: bool | None = Field(default=None)

    # Text search
    search_query: str | None = Field(
        default=None, max_length=100, description="Search in transcript text"
    )

    # Relationship filters
    has_journal: bool | None = Field(default=None)
    journal_uid: str | None = Field(default=None)

    # Tag filters
    tags: list[str] | None = Field(default=None)

    # Processing filters
    has_errors: bool | None = Field(default=None)
    max_attempts: int | None = Field(default=None, ge=1)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: datetime | None, info) -> datetime | None:
        """Ensure end_date is after start_date"""
        if v is None:
            return v
        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")
        return v

    @field_validator("max_confidence")
    @classmethod
    def validate_confidence_range(cls, v: float | None, info) -> float | None:
        """Ensure max_confidence is greater than min_confidence"""
        if v is None:
            return v
        min_conf = info.data.get("min_confidence")
        if min_conf is not None and v <= min_conf:
            raise ValueError("max_confidence must be greater than min_confidence")
        return v


# ============================================================================
# BATCH OPERATION REQUEST MODELS
# ============================================================================


class TranscriptionBulkUpdateRequest(BaseModel):
    """Request model for bulk updating multiple transcriptions"""

    transcription_uids: list[str] = Field(min_length=1, description="Transcription UIDs to update")
    updates: TranscriptionUpdateRequest = Field(description="Updates to apply")


class TranscriptionRetryRequest(BaseModel):
    """Request model for retrying failed transcriptions"""

    transcription_uid: str = Field(description="UID of transcription to retry")
    service: TranscriptionServiceLiteral | None = Field(
        default=None, description="Try different service"
    )
    model: str | None = Field(default=None, description="Try different model")
    reset_attempts: bool = Field(default=False, description="Reset attempt counter")


class BatchTranscriptionRequest(BaseModel):
    """Request model for batch transcription processing"""

    audio_files: list[str] = Field(
        min_length=1, max_length=10, description="Audio file paths to process"
    )
    service: TranscriptionServiceLiteral = Field(
        default="deepgram", description="Service for all files"
    )
    language: LanguageCodeLiteral = Field(default="en", description="Language for all files")
    create_journals: bool = Field(default=False, description="Create journals for all")
    journal_category: str = Field(default="daily", description="Category for created journals")
    processing_priority: Literal["low", "normal", "high"] = Field(default="normal")
    callback_url: str | None = Field(default=None, description="Webhook callback URL")


# ============================================================================
# EXPORT REQUEST MODELS
# ============================================================================


class TranscriptionExportRequest(BaseModel):
    """Request model for exporting transcriptions"""

    format: Literal["text", "json", "srt", "vtt", "markdown"] = Field(default="text")
    transcription_uids: list[str] | None = Field(
        default=None, description="Specific transcriptions"
    )
    filters: TranscriptionFilterRequest | None = Field(default=None)
    include_metadata: bool = Field(default=True)
    include_timestamps: bool = Field(default=False)
    include_speaker_labels: bool = Field(default=True)
    combine_into_single_file: bool = Field(default=False)


# ============================================================================
# SEARCH REQUEST MODELS (from search_schemas.py)
# ============================================================================


class FacetSetRequest(BaseModel):
    """Request model for search facets"""

    domain: Literal["habits", "knowledge", "tasks", "finance", "transcription"] | None = None
    level: Literal["intro", "intermediate", "advanced"] | None = None
    intents: list[str] = Field(default_factory=list, description="Search intents")
    topics: list[str] = Field(default_factory=list, description="Normalized key terms/tags")
    filters: dict[str, Any] = Field(default_factory=dict, description="Extra filters")


class SearchQueryRequest(BaseModel):
    """Request model for complete search query"""

    text: str = Field(min_length=1, description="Search query text")
    user_uid: str = Field(description="User UID for personalization")
    facets: FacetSetRequest = Field(default_factory=FacetSetRequest)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    include_relationships: bool = Field(default=True)
    check_mastery: bool = Field(default=True)


# ============================================================================
# ANALYTICS REQUEST MODELS
# ============================================================================


class TranscriptionAnalyticsRequest(BaseModel):
    """Request model for transcription analytics"""

    # Time period
    start_date: datetime = Field(description="Analytics start date")
    end_date: datetime = Field(description="Analytics end date")

    # Analysis options
    include_service_breakdown: bool = Field(default=True)
    include_language_breakdown: bool = Field(default=True)
    include_quality_metrics: bool = Field(default=True)
    include_processing_performance: bool = Field(default=True)
    include_journal_integration: bool = Field(default=True)

    # Grouping
    group_by: Literal["day", "week", "month", "service", "language"] | None = Field(default="week")

    # Filters
    services: list[TranscriptionServiceLiteral] | None = Field(default=None)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """Ensure end_date is after start_date"""
        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")
        return v
