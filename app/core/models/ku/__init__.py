"""
Knowledge Models - Unified Ku Architecture
============================================

"Ku is the heartbeat of SKUEL."

Three-tier model for ALL knowledge in the system:
1. ku.py - Immutable domain model (frozen dataclass, 47 fields)
2. ku_dto.py - Mutable data transfer objects (KuDTOMixin)
3. ku_request.py - External API models (Pydantic, 4 create + 1 update + 1 response)

Content & RAG Support:
4. ku_content.py - Rich content storage with automatic chunking
5. ku_chunks.py - Semantic chunking for RAG retrieval
6. ku_metadata.py - Analytics and search optimization

KuProject & KuSchedule:
7. ku_project.py - Instruction templates for LLM processing
8. ku_project_request.py - Project API validation models
9. ku_schedule.py - Recurring progress Ku generation

Four KuType manifestations:
    CURRICULUM      -> Admin-created shared knowledge
    ASSIGNMENT      -> Student submission
    AI_REPORT       -> AI-derived from assignment
    FEEDBACK_REPORT -> Teacher feedback on assignment

Usage:
    from core.models.ku import Ku, KuDTO, KuResponse
    from core.models.ku import KuCurriculumCreateRequest, KuAssignmentCreateRequest
    from core.models.ku import KuProject, KuProjectDTO, KuSchedule
"""

from .ku import Ku
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_dto import KuDTO
from .ku_metadata import KuMetadata
from .ku_project import (
    KuProject,
    KuProjectDTO,
    create_ku_project,
    ku_project_domain_to_dto,
    ku_project_dto_to_domain,
)
from .ku_project_request import (
    KuFeedbackGenerateRequest,
    KuProjectCreateRequest,
    KuProjectUpdateRequest,
)
from .ku_request import (
    AddTagsRequest,
    AssessmentCreateRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeKuRequest,
    KuAiReportCreateRequest,
    KuAssignmentCreateRequest,
    KuCurriculumCreateRequest,
    KuFeedbackCreateRequest,
    KuListResponse,
    KuResponse,
    KuScheduleCreateRequest,
    KuScheduleUpdateRequest,
    KuUpdateRequest,
    ProgressKuGenerateRequest,
    RemoveTagsRequest,
)
from .ku_schedule import (
    KuSchedule,
    KuScheduleDTO,
    ku_schedule_domain_to_dto,
    ku_schedule_dto_to_domain,
)

__all__ = [
    # Core domain models
    "Ku",
    "KuChunk",
    "KuChunkType",
    # Content models
    "KuContent",
    # Converter
    "ku_to_response",
    # DTO
    "KuDTO",
    "KuMetadata",
    # API request models (one per KuType)
    "KuCurriculumCreateRequest",
    "KuAssignmentCreateRequest",
    "KuAiReportCreateRequest",
    "KuFeedbackCreateRequest",
    "KuUpdateRequest",
    # API response models
    "KuResponse",
    "KuListResponse",
    # Route-specific request models
    "AddTagsRequest",
    "RemoveTagsRequest",
    "BulkCategorizeRequest",
    "BulkTagRequest",
    "BulkDeleteRequest",
    "CategorizeKuRequest",
    "ProgressKuGenerateRequest",
    "KuScheduleCreateRequest",
    "KuScheduleUpdateRequest",
    "AssessmentCreateRequest",
    # KuProject (instruction templates)
    "KuProject",
    "KuProjectDTO",
    "create_ku_project",
    "ku_project_dto_to_domain",
    "ku_project_domain_to_dto",
    # KuProject requests
    "KuProjectCreateRequest",
    "KuProjectUpdateRequest",
    "KuFeedbackGenerateRequest",
    # KuSchedule (recurring progress generation)
    "KuSchedule",
    "KuScheduleDTO",
    "ku_schedule_dto_to_domain",
    "ku_schedule_domain_to_dto",
    # Functions
    "chunk_content",
]
