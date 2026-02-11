"""
Knowledge Models - Unified Ku Architecture
============================================

"Ku is the heartbeat of SKUEL."

Three-tier model for ALL knowledge in the system:
1. ku.py - Immutable domain model (frozen dataclass, ~138 fields)
2. ku_dto.py - Mutable data transfer objects (KuDTOMixin)
3. ku_request.py - External API models (Pydantic, 14 create + 1 update + 1 response)

Content & RAG Support:
4. ku_content.py - Rich content storage with automatic chunking
5. ku_chunks.py - Semantic chunking for RAG retrieval
6. ku_metadata.py - Analytics and search optimization

KuProject & KuSchedule:
7. ku_project.py - Instruction templates for LLM processing
8. ku_project_request.py - Project API validation models
9. ku_schedule.py - Recurring progress Ku generation

Nested Types:
10. ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment

14 KuType manifestations:
    CURRICULUM      -> Admin-created shared knowledge
    ASSIGNMENT      -> Student submission
    AI_REPORT       -> AI-derived from assignment
    FEEDBACK_REPORT -> Teacher feedback on assignment
    TASK            -> Knowledge about what needs doing
    GOAL            -> Knowledge about where you're heading
    HABIT           -> Knowledge about what you practice
    EVENT           -> Knowledge about what you attend
    CHOICE          -> Knowledge about decisions you make
    PRINCIPLE       -> Knowledge about what you believe
    MOC             -> Map of Content (KU organizing KUs)
    LEARNING_STEP   -> Step in a learning path
    LEARNING_PATH   -> Ordered sequence of steps
    LIFE_PATH       -> Knowledge about your life direction

Usage:
    from core.models.ku import Ku, KuDTO, KuResponse
    from core.models.ku import KuCurriculumCreateRequest, KuTaskCreateRequest
    from core.models.ku import KuProject, KuProjectDTO, KuSchedule
    from core.models.ku import Milestone, ChoiceOption, PrincipleExpression
"""

from .ku import Ku
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_dto import KuDTO
from .ku_metadata import KuMetadata
from .ku_nested_types import (
    AlignmentAssessment,
    ChoiceOption,
    Milestone,
    PrincipleExpression,
)
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
    # Route-specific
    AddTagsRequest,
    AssessmentCreateRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeKuRequest,
    # Nested request models
    ChoiceOptionRequest,
    # Content processing create requests
    KuAiReportCreateRequest,
    KuAssignmentCreateRequest,
    # Activity domain create requests
    KuChoiceCreateRequest,
    KuCurriculumCreateRequest,
    KuEventCreateRequest,
    KuFeedbackCreateRequest,
    KuGoalCreateRequest,
    KuHabitCreateRequest,
    # Shared/curriculum create requests
    KuLearningPathCreateRequest,
    KuLearningStepCreateRequest,
    # Destination create request
    KuLifePathCreateRequest,
    # Response models
    KuListResponse,
    KuMocCreateRequest,
    KuPrincipleCreateRequest,
    KuResponse,
    KuScheduleCreateRequest,
    KuScheduleUpdateRequest,
    KuTaskCreateRequest,
    KuUpdateRequest,
    MilestoneRequest,
    PrincipleExpressionRequest,
    ProgressKuGenerateRequest,
    RemoveTagsRequest,
)
from .ku_schedule import (
    KuSchedule,
    KuScheduleDTO,
    ku_schedule_domain_to_dto,
    ku_schedule_dto_to_domain,
)
from .lp_position import LpPosition, create_lp_position

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
    # Nested types (frozen dataclasses)
    "Milestone",
    "ChoiceOption",
    "PrincipleExpression",
    "AlignmentAssessment",
    # Nested request models (Pydantic)
    "MilestoneRequest",
    "ChoiceOptionRequest",
    "PrincipleExpressionRequest",
    # API create requests — Content Processing (original 4)
    "KuCurriculumCreateRequest",
    "KuAssignmentCreateRequest",
    "KuAiReportCreateRequest",
    "KuFeedbackCreateRequest",
    # API create requests — Activity Domains (6 new)
    "KuTaskCreateRequest",
    "KuGoalCreateRequest",
    "KuHabitCreateRequest",
    "KuEventCreateRequest",
    "KuChoiceCreateRequest",
    "KuPrincipleCreateRequest",
    # API create requests — Shared/Curriculum (3 new)
    "KuMocCreateRequest",
    "KuLearningStepCreateRequest",
    "KuLearningPathCreateRequest",
    # API create requests — Destination (1 new)
    "KuLifePathCreateRequest",
    # API update/response
    "KuUpdateRequest",
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
    # Learning Path Position
    "LpPosition",
    "create_lp_position",
]
