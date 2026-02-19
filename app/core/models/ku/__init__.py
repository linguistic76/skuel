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

Assignment & KuSchedule:
7. assignment.py - Instruction templates for LLM processing (Assign stage)
8. assignment_request.py - Assignment API validation models
9. ku_schedule.py - Recurring progress Ku generation

Nested Types:
10. ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment

14 KuType manifestations:
    CURRICULUM      -> Admin-created shared knowledge
    SUBMISSION      -> Student submission
    AI_REPORT       -> AI-derived from submission
    FEEDBACK_REPORT -> Teacher feedback on submission
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
    from core.models.ku import Assignment, AssignmentDTO, KuSchedule
    from core.models.ku import Milestone, ChoiceOption, PrincipleExpression
"""

from .assignment import (
    Assignment,
    AssignmentDTO,
    assignment_domain_to_dto,
    assignment_dto_to_domain,
    create_assignment,
)
from .assignment_request import (
    AssignmentCreateRequest,
    AssignmentUpdateRequest,
    KuFeedbackGenerateRequest,
)
from .ku import KU_TYPE_CLASS_MAP, Ku
from .ku_base import KuBase
from .ku_choice import ChoiceKu
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_dto import KuDTO
from .ku_event import EventKu
from .ku_goal import GoalKu
from .ku_habit import HabitKu
from .ku_metadata import KuMetadata
from .ku_nested_types import (
    AlignmentAssessment,
    ChoiceOption,
    Milestone,
    PrincipleExpression,
)
from .ku_principle import PrincipleKu
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
from .ku_task import TaskKu
from .lp_position import LpPosition, create_lp_position

__all__ = [
    # Core domain models
    "Ku",
    "KuBase",
    "TaskKu",
    "GoalKu",
    "HabitKu",
    "EventKu",
    "ChoiceKu",
    "PrincipleKu",
    "KU_TYPE_CLASS_MAP",
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
    # Assignment (instruction templates — Assign stage)
    "Assignment",
    "AssignmentDTO",
    "create_assignment",
    "assignment_dto_to_domain",
    "assignment_domain_to_dto",
    # Assignment requests
    "AssignmentCreateRequest",
    "AssignmentUpdateRequest",
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
