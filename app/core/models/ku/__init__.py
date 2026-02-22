"""
Knowledge Models - Domain-First Architecture
==============================================

"Ku is the heartbeat of SKUEL."

Each domain has its own frozen dataclass. User-owned types inherit from
UserOwnedEntity (adds user_uid, priority). Shared types inherit from Entity.

Architecture:
    entity.py            - Entity (~19 common fields, from_dto dispatcher)
    user_owned_entity.py - UserOwnedEntity(Entity) +2 fields (user_uid, priority)
    ku.py                - Ku union type alias + ENTITY_TYPE_CLASS_MAP

    User-owned (via UserOwnedEntity):
        task.py       - Task          +25 task fields
        goal.py       - Goal          +24 goal fields
        habit.py      - Habit         +31 habit fields
        event.py      - Event         +26 event fields
        choice.py     - Choice        +13 choice fields
        principle.py  - Principle     +19 principle fields
        submission.py - Submission    +13 file/processing fields
            journal.py    - Journal(Submission)   +0
            ai_report.py  - AiReport(Submission)  +0
            feedback.py   - Feedback(Submission)  +2
        life_path.py  - LifePath      +14 alignment fields

    Shared (via Entity):
        curriculum.py     - Curriculum    +21 learning/substance fields
            learning_step.py - LearningStep(Curriculum) +9
            learning_path.py - LearningPath(Curriculum) +4
            exercise.py      - Exercise(Curriculum)     +7
        resource.py       - Resource      +7 resource fields

Support:
    ku_dto.py          - Unified KuDTO (all fields, mutable)
    ku_request.py      - Pydantic API models
    ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment
    ku_content.py, ku_chunks.py, ku_metadata.py - Content & RAG
    ku_schedule.py     - Scheduling

Usage:
    from core.models.ku import Task, Goal, Habit, Event, Choice, Principle
    from core.models.ku import Curriculum, Exercise, LearningStep, LearningPath
    from core.models.ku import Submission, Journal, AiReport, Feedback
    from core.models.ku import Entity, UserOwnedEntity, Ku, KuDTO, KuSchedule
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
from .ku import ENTITY_TYPE_CLASS_MAP, ActivityEntity, CurriculumEntity, Ku, SubmissionEntity
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
from .user_owned_entity import UserOwnedEntity

__all__ = [
    # Core domain models
    "Ku",
    "Entity",
    "UserOwnedEntity",
    "ActivityEntity",
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
