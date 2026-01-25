"""
Transcription Domain Models
===========================

Three-tier architecture for Transcription domain:
- Request models (Pydantic) for API validation
- DTOs for data transfer between layers
- Pure models (frozen dataclasses) for domain logic
"""

# Request models (Tier 1 - Pydantic)
# Converters
from .transcription_converters import (
    # Search converters
    facet_request_to_dto,
    # Processing converters
    process_request_to_dto,
    search_query_request_to_dto,
    # Transcription converters
    transcription_create_request_to_dto,
    transcription_dto_to_pure,
    transcription_dto_to_response,
    transcription_pure_to_dto,
    transcription_update_request_to_dto,
)

# DTOs (Tier 2 - Data Transfer)
from .transcription_dto import (
    AudioFormat,
    # Search DTOs
    FacetSetDTO,
    LanguageCode,
    # Enums (shared with Pure)
    ProcessingStatus,
    SearchQueryDTO,
    SearchResultDTO,
    # Analytics/Export DTOs
    TranscriptionAnalyticsDTO,
    # Core DTOs
    TranscriptionDTO,
    TranscriptionExportDTO,
    TranscriptionService,
)

# Pure models (Tier 3 - Domain)
from .transcription_pure import (
    # Domain models
    TranscriptionPure,
    # Factory functions
    create_transcription,
    create_transcription_with_audio_metadata,
)
from .transcription_request import (
    AudioFormatLiteral,
    AudioProcessingRequest,  # API endpoint request model
    BatchTranscriptionRequest,
    # Search requests
    FacetSetRequest,
    LanguageCodeLiteral,
    # Type literals
    ProcessingStatusLiteral,
    SearchQueryRequest,
    TranscriptionAnalyticsRequest,
    # Batch operations
    TranscriptionBulkUpdateRequest,
    # Create/Update requests
    TranscriptionCreateRequest,
    # Export/Analytics
    TranscriptionExportRequest,
    TranscriptionFilterRequest,
    TranscriptionProcessRequest,
    TranscriptionRetryRequest,
    TranscriptionServiceLiteral,
    TranscriptionUpdateRequest,
)

__all__ = [
    "AudioFormat",
    "AudioFormatLiteral",
    "AudioProcessingRequest",
    "BatchTranscriptionRequest",
    "FacetSetDTO",
    "FacetSetRequest",
    "LanguageCode",
    "LanguageCodeLiteral",
    # Enums
    "ProcessingStatus",
    # Type literals
    "ProcessingStatusLiteral",
    "SearchQueryDTO",
    "SearchQueryRequest",
    "SearchResultDTO",
    "TranscriptionAnalyticsDTO",
    "TranscriptionAnalyticsRequest",
    "TranscriptionBulkUpdateRequest",
    # Request models
    "TranscriptionCreateRequest",
    # DTOs
    "TranscriptionDTO",
    "TranscriptionExportDTO",
    "TranscriptionExportRequest",
    "TranscriptionFilterRequest",
    "TranscriptionProcessRequest",
    # Pure models
    "TranscriptionPure",
    "TranscriptionRetryRequest",
    "TranscriptionService",
    "TranscriptionServiceLiteral",
    "TranscriptionUpdateRequest",
    # Factory functions
    "create_transcription",
    "create_transcription_with_audio_metadata",
    "facet_request_to_dto",
    "process_request_to_dto",
    "search_query_request_to_dto",
    # Converters
    "transcription_create_request_to_dto",
    "transcription_dto_to_pure",
    "transcription_dto_to_response",
    "transcription_pure_to_dto",
    "transcription_update_request_to_dto",
]
