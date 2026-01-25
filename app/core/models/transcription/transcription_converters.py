"""
Transcription Model Converters
===============================

Conversion functions between the three tiers:
- Request (Pydantic) <-> DTO <-> Pure (Domain)

ARCHITECTURAL ALIGNMENT (November 2, 2025):
-------------------------------------------
✅ SIMPLIFIED CONVERTERS - Flattened structure
- No more nested value object conversions
- Direct field mapping between DTO and Pure
- Simpler, more maintainable code
"""

import uuid
from datetime import datetime
from typing import Any

from .transcription_dto import (
    AudioFormat,
    FacetSetDTO,
    LanguageCode,
    ProcessingStatus,
    SearchQueryDTO,
    TranscriptionDTO,
    TranscriptionService,
)
from .transcription_pure import TranscriptionPure
from .transcription_request import (
    FacetSetRequest,
    SearchQueryRequest,
    TranscriptionCreateRequest,
    TranscriptionProcessRequest,
    TranscriptionUpdateRequest,
)

# ============================================================================
# TRANSCRIPTION CONVERTERS (FLATTENED)
# ============================================================================


def transcription_create_request_to_dto(
    request: TranscriptionCreateRequest, user_uid: str | None = None
) -> TranscriptionDTO:
    """Convert TranscriptionCreateRequest to TranscriptionDTO"""
    return TranscriptionDTO(
        uid=str(uuid.uuid4()),  # Generate new UID
        audio_file_path=request.audio_file_path,
        original_filename=request.original_filename,
        service=TranscriptionService(request.service),
        model=request.model,
        language=LanguageCode(request.language),
        enable_diarization=request.enable_diarization,
        enable_punctuation=request.enable_punctuation,
        enable_paragraphs=request.enable_paragraphs,
        custom_vocabulary=request.custom_vocabulary or [],
        journal_uid=request.journal_uid,
        tags=request.tags or [],
        notes=request.notes,
        processing_status=ProcessingStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=user_uid,
        user_uid=user_uid,
    )


def transcription_update_request_to_dto(
    request: TranscriptionUpdateRequest, existing: TranscriptionDTO
) -> TranscriptionDTO:
    """
    Apply TranscriptionUpdateRequest to existing TranscriptionDTO.

    FLATTENED: Direct field updates, no nested object handling.
    """
    # Build update dictionary
    updates = {}

    # Transcript and status
    if request.transcript_text is not None:
        updates["transcript_text"] = request.transcript_text
        # Auto-update word count if transcript changes
        updates["word_count"] = len(request.transcript_text.split())

    if request.processing_status is not None:
        updates["processing_status"] = ProcessingStatus(request.processing_status)

    # Flattened metrics
    if request.confidence_score is not None:
        updates["confidence_score"] = request.confidence_score
    if request.word_count is not None:
        updates["word_count"] = request.word_count

    # Analysis results
    if request.speakers is not None:
        updates["speakers"] = request.speakers
    if request.paragraphs is not None:
        updates["paragraphs"] = request.paragraphs
    if request.sentences is not None:
        updates["sentences"] = request.sentences

    # Relations and metadata
    if request.journal_uid is not None:
        updates["journal_uid"] = request.journal_uid
    if request.error_message is not None:
        updates["error_message"] = request.error_message
    if request.tags is not None:
        updates["tags"] = request.tags
    if request.notes is not None:
        updates["notes"] = request.notes

    # Always update timestamp
    updates["updated_at"] = datetime.now()

    # Apply updates to existing DTO
    for key, value in updates.items():
        setattr(existing, key, value)

    return existing


def transcription_dto_to_pure(dto: TranscriptionDTO) -> TranscriptionPure:
    """
    Convert TranscriptionDTO to TranscriptionPure.

    FLATTENED: Simple field mapping, no nested object conversion.
    """
    return TranscriptionPure(
        # Identity
        uid=dto.uid,
        # Audio file information
        audio_file_path=dto.audio_file_path,
        original_filename=dto.original_filename,
        # Flattened audio metadata
        audio_format=dto.audio_format,
        audio_duration_seconds=dto.audio_duration_seconds,
        audio_file_size_bytes=dto.audio_file_size_bytes,
        audio_sample_rate=dto.audio_sample_rate,
        audio_bit_rate=dto.audio_bit_rate,
        audio_channels=dto.audio_channels,
        audio_encoding=dto.audio_encoding,
        # Transcription results
        transcript_text=dto.transcript_text,
        processing_status=dto.processing_status,
        # Flattened transcription metrics
        processing_time_ms=dto.processing_time_ms,
        confidence_score=dto.confidence_score,
        word_count=dto.word_count,
        speaking_rate_wpm=dto.speaking_rate_wpm,
        silence_ratio=dto.silence_ratio,
        # Processing information
        processing_attempts=dto.processing_attempts,
        error_message=dto.error_message,
        # Analysis results (copy lists to ensure immutability)
        speakers=dto.speakers.copy() if dto.speakers else [],
        paragraphs=dto.paragraphs.copy() if dto.paragraphs else [],
        sentences=dto.sentences.copy() if dto.sentences else [],
        # Relations
        journal_uid=dto.journal_uid,
        # Configuration
        service=dto.service,
        model=dto.model,
        language=dto.language,
        enable_diarization=dto.enable_diarization,
        enable_punctuation=dto.enable_punctuation,
        enable_paragraphs=dto.enable_paragraphs,
        custom_vocabulary=dto.custom_vocabulary.copy() if dto.custom_vocabulary else [],
        # Metadata
        tags=dto.tags.copy() if dto.tags else [],
        notes=dto.notes,
        metadata=dto.metadata.copy() if dto.metadata else {},
        # Audit
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        created_by=dto.created_by,
        user_uid=dto.user_uid,
    )


def transcription_pure_to_dto(pure: TranscriptionPure) -> TranscriptionDTO:
    """
    Convert TranscriptionPure to TranscriptionDTO.

    FLATTENED: Simple field mapping, no nested object conversion.
    """
    return TranscriptionDTO(
        # Identity
        uid=pure.uid,
        # Audio file information
        audio_file_path=pure.audio_file_path,
        original_filename=pure.original_filename,
        # Flattened audio metadata
        audio_format=pure.audio_format,
        audio_duration_seconds=pure.audio_duration_seconds,
        audio_file_size_bytes=pure.audio_file_size_bytes,
        audio_sample_rate=pure.audio_sample_rate,
        audio_bit_rate=pure.audio_bit_rate,
        audio_channels=pure.audio_channels,
        audio_encoding=pure.audio_encoding,
        # Transcription results
        transcript_text=pure.transcript_text,
        processing_status=pure.processing_status,
        # Flattened transcription metrics
        processing_time_ms=pure.processing_time_ms,
        confidence_score=pure.confidence_score,
        word_count=pure.word_count,
        speaking_rate_wpm=pure.speaking_rate_wpm,
        silence_ratio=pure.silence_ratio,
        # Processing information
        processing_attempts=pure.processing_attempts,
        error_message=pure.error_message,
        # Analysis results (copy lists)
        speakers=pure.speakers.copy() if pure.speakers else [],
        paragraphs=pure.paragraphs.copy() if pure.paragraphs else [],
        sentences=pure.sentences.copy() if pure.sentences else [],
        # Relations
        journal_uid=pure.journal_uid,
        # Configuration
        service=pure.service,
        model=pure.model,
        language=pure.language,
        enable_diarization=pure.enable_diarization,
        enable_punctuation=pure.enable_punctuation,
        enable_paragraphs=pure.enable_paragraphs,
        custom_vocabulary=pure.custom_vocabulary.copy() if pure.custom_vocabulary else [],
        # Metadata
        tags=pure.tags.copy() if pure.tags else [],
        notes=pure.notes,
        metadata=pure.metadata.copy() if pure.metadata else {},
        # Audit
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        created_by=pure.created_by,
        user_uid=pure.user_uid,
    )


def transcription_dto_to_response(dto: TranscriptionDTO) -> dict[str, Any]:
    """
    Convert TranscriptionDTO to API response format.

    FLATTENED: Access fields directly instead of via nested objects.
    """
    # Calculate derived values from flattened fields
    duration_minutes = (dto.audio_duration_seconds / 60) if dto.audio_duration_seconds else 0
    file_size_mb = (dto.audio_file_size_bytes / (1024 * 1024)) if dto.audio_file_size_bytes else 0

    return {
        "uid": dto.uid,
        "audio_file_path": dto.audio_file_path,
        "original_filename": dto.original_filename,
        # Audio metadata (flattened)
        "audio_metadata": {
            "format": dto.audio_format.value
            if isinstance(dto.audio_format, AudioFormat)
            else dto.audio_format,
            "duration_seconds": dto.audio_duration_seconds,
            "file_size_bytes": dto.audio_file_size_bytes,
            "sample_rate": dto.audio_sample_rate,
            "bit_rate": dto.audio_bit_rate,
            "channels": dto.audio_channels,
            "encoding": dto.audio_encoding,
        }
        if dto.audio_duration_seconds or dto.audio_file_size_bytes
        else None,
        # Transcription results
        "transcript_text": dto.transcript_text,
        "transcript_preview": dto.transcript_text[:200] + "..."
        if len(dto.transcript_text) > 200
        else dto.transcript_text,
        "processing_status": dto.processing_status.value
        if isinstance(dto.processing_status, ProcessingStatus)
        else dto.processing_status,
        # Transcription metrics (flattened)
        "transcription_metrics": {
            "processing_time_ms": dto.processing_time_ms,
            "confidence_score": dto.confidence_score,
            "word_count": dto.word_count,
            "speaking_rate_wpm": dto.speaking_rate_wpm,
            "silence_ratio": dto.silence_ratio,
        }
        if dto.processing_time_ms or dto.confidence_score
        else None,
        # Processing information
        "processing_attempts": dto.processing_attempts,
        "error_message": dto.error_message,
        # Analysis results
        "speakers": dto.speakers,
        "speaker_count": len(dto.speakers),
        "paragraphs": dto.paragraphs,
        "sentences": dto.sentences,
        # Relations
        "journal_uid": dto.journal_uid,
        "has_journal": bool(dto.journal_uid),
        # Configuration
        "service": dto.service.value
        if isinstance(dto.service, TranscriptionService)
        else dto.service,
        "model": dto.model,
        "language": dto.language.value if isinstance(dto.language, LanguageCode) else dto.language,
        "enable_diarization": dto.enable_diarization,
        "enable_punctuation": dto.enable_punctuation,
        "enable_paragraphs": dto.enable_paragraphs,
        "custom_vocabulary": dto.custom_vocabulary,
        # Metadata
        "tags": dto.tags,
        "notes": dto.notes,
        # Computed status flags
        "is_successful": dto.processing_status
        in [ProcessingStatus.TRANSCRIBED, ProcessingStatus.COMPLETED],
        "is_failed": dto.processing_status == ProcessingStatus.FAILED,
        "is_processing": dto.processing_status
        in [ProcessingStatus.TRANSCRIBING, ProcessingStatus.ANALYZING],
        # Computed metrics
        "duration_minutes": duration_minutes,
        "words_per_minute": dto.speaking_rate_wpm,
        "confidence_score": dto.confidence_score,
        "file_size_mb": file_size_mb,
        "has_multiple_speakers": len(dto.speakers) > 1,
        # Audit
        "created_at": dto.created_at.isoformat()
        if isinstance(dto.created_at, datetime)
        else dto.created_at,
        "updated_at": dto.updated_at.isoformat()
        if isinstance(dto.updated_at, datetime)
        else dto.updated_at,
        "created_by": dto.created_by,
    }


# ============================================================================
# PROCESSING REQUEST CONVERTERS
# ============================================================================


def process_request_to_dto(
    request: TranscriptionProcessRequest, audio_file_path: str, user_uid: str | None = None
) -> TranscriptionDTO:
    """Convert TranscriptionProcessRequest to TranscriptionDTO for new processing"""
    return TranscriptionDTO(
        uid=str(uuid.uuid4()),
        audio_file_path=audio_file_path,
        service=TranscriptionService(request.service),
        model=request.model,
        language=LanguageCode(request.language),
        enable_diarization=request.enable_diarization,
        enable_punctuation=request.enable_punctuation,
        enable_paragraphs=request.enable_paragraphs,
        tags=request.tags or [],
        notes=request.notes,
        processing_status=ProcessingStatus.PENDING,
        metadata={
            "create_journal": request.create_journal,
            "journal_title": request.journal_title,
            "journal_category": request.journal_category,
            "extract_insights": request.extract_insights,
            "auto_paragraph": request.auto_paragraph,
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=user_uid,
        user_uid=user_uid,
    )


# ============================================================================
# SEARCH CONVERTERS
# ============================================================================


def facet_request_to_dto(request: FacetSetRequest) -> FacetSetDTO:
    """Convert FacetSetRequest to FacetSetDTO"""
    return FacetSetDTO(
        domain=request.domain,
        level=request.level,
        intents=request.intents or [],
        topics=request.topics or [],
        filters=request.filters or {},
    )


def search_query_request_to_dto(request: SearchQueryRequest) -> SearchQueryDTO:
    """Convert SearchQueryRequest to SearchQueryDTO"""
    return SearchQueryDTO(
        text=request.text,
        user_uid=request.user_uid,
        facets=facet_request_to_dto(request.facets),
        limit=request.limit,
        offset=request.offset,
        include_relationships=request.include_relationships,
        check_mastery=request.check_mastery,
    )
