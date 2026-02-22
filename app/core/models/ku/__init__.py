"""
Knowledge Models - Decomposed Ku Architecture (Phase 10 Complete)
==================================================================

"Ku is the heartbeat of SKUEL."

After Phase 10 decomposition, the God Object is gone. Each domain has its own
frozen dataclass inheriting from KuBase (~48 common fields).

Architecture:
    ku_base.py      - KuBase (~29 common fields + stubs, from_dto dispatcher)
    ku.py           - Ku union type alias + KU_TYPE_CLASS_MAP
    ku_task.py      - TaskKu(KuBase)          +25 task fields
    ku_goal.py      - GoalKu(KuBase)          +24 goal fields
    ku_habit.py     - HabitKu(KuBase)         +31 habit fields
    ku_event.py     - EventKu(KuBase)         +37 event fields
    ku_choice.py    - ChoiceKu(KuBase)        +13 choice fields
    ku_principle.py - PrincipleKu(KuBase)     +19 principle fields
    ku_curriculum.py  - CurriculumKu(KuBase)  +21 learning/substance fields
    ku_resource.py    - ResourceKu(KuBase)    +7 resource fields
    ku_learning_step.py - LearningStepKu(CurriculumKu) +9 fields
    ku_learning_path.py - LearningPathKu(CurriculumKu) +4 fields
    ku_submission.py  - SubmissionKu(KuBase)  +13 file/processing fields
    ku_journal.py     - JournalKu(SubmissionKu)  +0
    ku_ai_report.py   - AiReportKu(SubmissionKu) +0
    ku_feedback.py    - FeedbackKu(SubmissionKu)  +2 feedback fields
    ku_life_path.py   - LifePathKu(KuBase)       +12 alignment fields

Support:
    ku_dto.py          - Unified KuDTO (all fields, mutable)
    ku_request.py      - Pydantic API models (14 create + 1 update + 1 response)
    ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment
    ku_content.py, ku_chunks.py, ku_metadata.py - Content & RAG
    ku_exercise.py - ExerciseKu(CurriculumKu) - instruction templates
    ku_schedule.py - Scheduling

Usage:
    from core.models.ku import TaskKu, GoalKu, HabitKu, EventKu, ChoiceKu, PrincipleKu
    from core.models.ku import CurriculumKu, ExerciseKu, LearningStepKu, LearningPathKu
    from core.models.ku import SubmissionKu, JournalKu, AiReportKu, FeedbackKu
    from core.models.ku import KuBase, Ku, KuDTO, KuResponse, KuSchedule
"""

from .exercise_request import (
    ExerciseCreateRequest,
    ExerciseUpdateRequest,
    KuFeedbackGenerateRequest,
)
from .ku import KU_TYPE_CLASS_MAP, CurriculumEntity, Ku, SubmissionEntity
from .ku_ai_report import AiReportKu
from .ku_base import KuBase
from .ku_choice import ChoiceKu
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_curriculum import CurriculumKu
from .ku_dto import KuDTO
from .ku_event import EventKu
from .ku_exercise import ExerciseKu
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
from .ku_resource import ResourceKu
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
    "ExerciseKu",
    "ResourceKu",
    "LearningStepKu",
    "LearningPathKu",
    "SubmissionKu",
    "JournalKu",
    "AiReportKu",
    "FeedbackKu",
    "LifePathKu",
    "KU_TYPE_CLASS_MAP",
    "CurriculumEntity",
    "SubmissionEntity",
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
    # Exercise requests (instruction templates)
    "ExerciseCreateRequest",
    "ExerciseUpdateRequest",
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
