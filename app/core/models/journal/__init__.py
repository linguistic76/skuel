"""
Journal Models Module
=====================

Three-tier architecture for Journal domain:
- Request models (Pydantic) for API validation
- DTOs for data transfer between layers
- Pure models for domain logic
"""

# Pure domain models
# Converters
from .journal_converters import (
    create_journal_from_transcript,
    journal_create_request_to_dto,
    journal_dto_to_pure,
    journal_dto_to_response,
    journal_pure_to_dto,
    journal_update_request_to_dto,
    transcript_request_to_instructions_dto,
)

# DTOs
from .journal_dto import (
    AnalysisDepth,
    ContextEnrichmentLevel,
    FormattingStyle,
    JournalAnalyticsDTO,
    JournalDTO,
    JournalExportDTO,
    ProcessedTranscriptResultDTO,
    TranscriptProcessingInstructionsDTO,
)

# Journal Projects
from .journal_project import JournalProjectDTO, JournalProjectPure, create_journal_project
from .journal_project import dto_to_pure as project_dto_to_pure
from .journal_project import pure_to_dto as project_pure_to_dto

# Journal Project Request models
from .journal_project_request import (
    JournalFeedbackRequest,
    JournalProjectCreateRequest,
    JournalProjectUpdateRequest,
)
from .journal_pure import (
    ContentStatus,
    ContentType,
    ContentVisibility,
    JournalCategory,
    JournalPure,
    create_journal,
    create_journal_from_transcription,
)

# Request models (Pydantic)
from .journal_request import (
    JournalAnalyticsRequest,
    JournalBulkUpdateRequest,
    JournalCreateRequest,
    JournalExportRequest,
    JournalFilterRequest,
    JournalInsightExtractionRequest,
    JournalUpdateRequest,
    TranscriptProcessingRequest,
)

# No aliases needed - use JournalPure directly

__all__ = [
    "AnalysisDepth",
    "ContentStatus",
    # Enums
    "ContentType",
    "ContentVisibility",
    "ContextEnrichmentLevel",
    "FormattingStyle",
    "JournalAnalyticsDTO",
    "JournalAnalyticsRequest",
    "JournalBulkUpdateRequest",
    "JournalCategory",
    # Request models
    "JournalCreateRequest",
    # DTOs
    "JournalDTO",
    "JournalExportDTO",
    "JournalExportRequest",
    "JournalFeedbackRequest",
    "JournalFilterRequest",
    "JournalInsightExtractionRequest",
    # Journal Project Request models
    "JournalProjectCreateRequest",
    "JournalProjectDTO",
    "JournalProjectPure",
    "JournalProjectUpdateRequest",
    # Pure models
    "JournalPure",
    "JournalUpdateRequest",
    "ProcessedTranscriptResultDTO",
    "TranscriptProcessingInstructionsDTO",
    "TranscriptProcessingRequest",
    # Factory functions
    "create_journal",
    "create_journal_from_transcript",
    "create_journal_from_transcription",
    "create_journal_project",
    # Converters
    "journal_create_request_to_dto",
    "journal_dto_to_pure",
    "journal_dto_to_response",
    "journal_pure_to_dto",
    "journal_update_request_to_dto",
    "project_dto_to_pure",
    "project_pure_to_dto",
    "transcript_request_to_instructions_dto",
]
