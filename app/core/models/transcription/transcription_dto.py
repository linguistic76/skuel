"""
Transcription DTO Models
========================

Data Transfer Objects for Transcription domain (Tier 2 of three-tier architecture).
Mutable dataclasses for transferring data between layers.

ARCHITECTURAL ALIGNMENT (November 2, 2025):
-------------------------------------------
✅ FLATTENED STRUCTURE - Matches flattened TranscriptionPure model
- Removed nested value objects (AudioMetadataDTO, TranscriptionMetricsDTO)
- All fields are Neo4j primitives (string, int, float, bool, arrays)
- No more manual to_dict() serialization needed
- UniversalNeo4jBackend handles serialization automatically
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Transcription enums consolidated in /core/models/enums/transcription_enums.py (January 2026)
from core.models.enums.transcription_enums import (
    AudioFormat,
    LanguageCode,
    ProcessingStatus,
    TranscriptionService,
)

# ============================================================================
# TRANSCRIPTION DTOs (FLATTENED)
# ============================================================================


@dataclass
class TranscriptionDTO:
    """
    Mutable DTO for transcription data transfer between layers.

    FLATTENED STRUCTURE (November 2, 2025):
    - All nested objects removed
    - Matches flattened TranscriptionPure model
    - UniversalNeo4jBackend handles serialization

    Used to move data between:
    - API layer (Pydantic) and Service layer
    - Service layer and Repository/Backend layer
    - Service layer and Domain model (Pure)
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

    # Audio metadata (flattened)
    audio_format: AudioFormat = AudioFormat.MP3
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
    processing_status: ProcessingStatus = ProcessingStatus.PENDING

    # Transcription metrics (flattened)
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
    # ANALYSIS RESULTS
    # ========================================================================

    speakers: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    service: TranscriptionService = TranscriptionService.DEEPGRAM
    model: str | None = None
    language: LanguageCode = LanguageCode.EN
    enable_diarization: bool = False
    enable_punctuation: bool = True
    enable_paragraphs: bool = True
    custom_vocabulary: list[str] = field(default_factory=list)

    # ========================================================================
    # METADATA
    # ========================================================================

    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # ========================================================================
    # AUDIT FIELDS
    # ========================================================================

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str | None = None
    user_uid: str | None = None  # Owner (REQUIRED for entity ownership)


# ============================================================================
# ANALYTICS DTOs
# ============================================================================


@dataclass
class TranscriptionAnalyticsDTO:
    """DTO for transcription analytics data"""

    # Time period
    period_start: datetime
    period_end: datetime

    # Processing statistics
    total_transcriptions: int = 0
    successful_transcriptions: int = 0
    failed_transcriptions: int = 0
    success_rate: float = 0.0

    # Audio statistics
    total_audio_hours: float = 0.0
    average_duration_minutes: float = 0.0
    largest_file_mb: float = 0.0
    total_words_transcribed: int = 0

    # Service breakdown
    service_usage: dict[str, int] = field(default_factory=dict)
    service_success_rates: dict[str, float] = field(default_factory=dict)

    # Language breakdown
    language_distribution: dict[str, int] = field(default_factory=dict)

    # Quality metrics
    average_confidence: float | None = None
    average_speaking_rate: float = 0.0

    # Processing performance
    average_processing_time_seconds: float = 0.0
    processing_time_by_duration: dict[str, float] = field(default_factory=dict)

    # Report integration
    transcriptions_with_reports: int = 0
    report_creation_rate: float = 0.0

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class TranscriptionExportDTO:
    """DTO for transcription export data"""

    format: str
    transcriptions: list[TranscriptionDTO]
    include_metadata: bool = True
    include_timestamps: bool = False
    include_speaker_labels: bool = True
    export_timestamp: datetime = field(default_factory=datetime.now)
    total_count: int = 0
    total_duration_hours: float = 0.0

    def __post_init__(self) -> None:
        """Calculate totals"""
        if self.transcriptions:
            self.total_count = len(self.transcriptions)
            self.total_duration_hours = sum(
                ((t.audio_duration_seconds or 0) / 3600) for t in self.transcriptions
            )


# ============================================================================
# SEARCH DTOs (from search_schemas.py)
# ============================================================================


@dataclass
class FacetSetDTO:
    """DTO for search facets"""

    domain: str | None = None
    level: str | None = None
    intents: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    detected_intent: str | None = None
    concepts: list[str] = field(default_factory=list)


@dataclass
class SearchQueryDTO:
    """DTO for complete search query"""

    text: str
    user_uid: str
    facets: FacetSetDTO = field(default_factory=FacetSetDTO)
    limit: int = 20
    offset: int = 0
    include_relationships: bool = True
    check_mastery: bool = True


@dataclass
class SearchResultDTO:
    """DTO for search results"""

    uid: str
    title: str
    domain: str
    snippet: str | None = None
    user_mastery_level: float | None = None
    is_accessible: bool = True
    mastery_warnings: list[str] = field(default_factory=list)
    score: float | None = None
    highlights: list[str] = field(default_factory=list)
