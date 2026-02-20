"""
Knowledge Models - Unified Ku Architecture
============================================

"Ku is the heartbeat of SKUEL."

Three-tier model for ALL knowledge in the system:
1. ku.py - God object (frozen dataclass, ~138 fields) + KU_TYPE_CLASS_MAP
2. ku_dto.py - Mutable data transfer objects (KuDTOMixin)
3. ku_request.py - External API models (Pydantic, 14 create + 1 update + 1 response)

Domain Subclasses (Phases 1-8 decomposition):
4. ku_task.py, ku_goal.py, ku_habit.py, ku_event.py - Activity domains
5. ku_choice.py, ku_principle.py - Activity domains
6. ku_curriculum.py - Shared knowledge (CURRICULUM, RESOURCE)
7. ku_learning_step.py, ku_learning_path.py - Curriculum structure
8. ku_submission.py - Content processing base (SUBMISSION, JOURNAL, AI_REPORT, FEEDBACK_REPORT)
9. ku_journal.py, ku_ai_report.py, ku_feedback.py - Content processing leaf types

Content & RAG Support:
10. ku_content.py - Rich content storage with automatic chunking
11. ku_chunks.py - Semantic chunking for RAG retrieval
12. ku_metadata.py - Analytics and search optimization

Assignment & KuSchedule:
13. assignment.py - Instruction templates for LLM processing (Assign stage)
14. assignment_request.py - Assignment API validation models
15. ku_schedule.py - Recurring progress Ku generation

Nested Types:
16. ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment

Usage:
    from core.models.ku import Ku, KuDTO, KuResponse
    from core.models.ku import TaskKu, GoalKu, HabitKu, EventKu, ChoiceKu, PrincipleKu
    from core.models.ku import CurriculumKu, LearningStepKu, LearningPathKu
    from core.models.ku import SubmissionKu, JournalKu, AiReportKu, FeedbackKu
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
from .ku_ai_report import AiReportKu
from .ku_base import KuBase
from .ku_choice import ChoiceKu
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_curriculum import CurriculumKu
from .ku_dto import KuDTO
from .ku_event import EventKu
from .ku_feedback import FeedbackKu
from .ku_goal import GoalKu
from .ku_habit import HabitKu
from .ku_journal import JournalKu
from .ku_learning_path import LearningPathKu
from .ku_learning_step import LearningStepKu
from .ku_life_path import LifePathKu
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
from .ku_submission import SubmissionKu
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
    "CurriculumKu",
    "LearningStepKu",
    "LearningPathKu",
    "SubmissionKu",
    "JournalKu",
    "AiReportKu",
    "FeedbackKu",
    "LifePathKu",
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
