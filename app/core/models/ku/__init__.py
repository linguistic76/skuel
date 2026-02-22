"""
Knowledge Models - Decomposed Ku Architecture (Phase 10 Complete)
==================================================================

"Ku is the heartbeat of SKUEL."

After Phase 10 decomposition, the God Object is gone. Each domain has its own
frozen dataclass inheriting from Entity (~48 common fields).

Architecture:
    ku_base.py      - Entity (~29 common fields + stubs, from_dto dispatcher)
    ku.py           - Ku union type alias + ENTITY_TYPE_CLASS_MAP
    ku_task.py      - Task(Entity)          +25 task fields
    ku_goal.py      - Goal(Entity)          +24 goal fields
    ku_habit.py     - Habit(Entity)         +31 habit fields
    ku_event.py     - Event(Entity)         +37 event fields
    ku_choice.py    - Choice(Entity)        +13 choice fields
    ku_principle.py - Principle(Entity)     +19 principle fields
    ku_curriculum.py  - Curriculum(Entity)  +21 learning/substance fields
    ku_resource.py    - Resource(Entity)    +7 resource fields
    ku_learning_step.py - LearningStep(Curriculum) +9 fields
    ku_learning_path.py - LearningPath(Curriculum) +4 fields
    ku_submission.py  - Submission(Entity)  +13 file/processing fields
    ku_journal.py     - Journal(Submission)  +0
    ku_ai_report.py   - AiReport(Submission) +0
    ku_feedback.py    - Feedback(Submission)  +2 feedback fields
    ku_life_path.py   - LifePath(Entity)       +12 alignment fields

Support:
    ku_dto.py          - Unified KuDTO (all fields, mutable)
    ku_request.py      - Pydantic API models (14 create + 1 update + 1 response)
    ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment
    ku_content.py, ku_chunks.py, ku_metadata.py - Content & RAG
    ku_exercise.py - Exercise(Curriculum) - instruction templates
    ku_schedule.py - Scheduling

Usage:
    from core.models.ku import Task, Goal, Habit, Event, Choice, Principle
    from core.models.ku import Curriculum, Exercise, LearningStep, LearningPath
    from core.models.ku import Submission, Journal, AiReport, Feedback
    from core.models.ku import Entity, Ku, KuDTO, KuResponse, KuSchedule
"""

from .ai_report import AiReport
from .choice import Choice
from .curriculum import Curriculum
from .entity import Entity
from .event import Event
from .exercise import Exercise
from .exercise_request import (
    ExerciseCreateRequest,
    ExerciseUpdateRequest,
    KuFeedbackGenerateRequest,
)
from .feedback import Feedback
from .goal import Goal
from .habit import Habit
from .journal import Journal
from .ku import ENTITY_TYPE_CLASS_MAP, CurriculumEntity, Ku, SubmissionEntity
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
from .learning_path import LearningPath
from .learning_step import LearningStep
from .life_path import LifePath
from .lp_position import LpPosition, create_lp_position
from .principle import Principle
from .resource import Resource
from .submission import Submission
from .task import Task

__all__ = [
    # Core domain models
    "Ku",
    "Entity",
    "Task",
    "Goal",
    "Habit",
    "Event",
    "Choice",
    "Principle",
    "Curriculum",
    "Exercise",
    "Resource",
    "LearningStep",
    "LearningPath",
    "Submission",
    "Journal",
    "AiReport",
    "Feedback",
    "LifePath",
    "ENTITY_TYPE_CLASS_MAP",
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
