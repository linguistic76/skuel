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
    ku_request.py      - Re-export shim (imports from split files below)
    activity_requests.py    - Activity domain creates (Tasks, Goals, etc.)
    curriculum_requests.py  - Curriculum creates (KU, LS, LP)
    report_requests.py      - Report creates + LifePath + Assessment
    entity_requests.py      - Shared types (update, response, bulk ops)
    ku_nested_types.py - Milestone, ChoiceOption, PrincipleExpression, AlignmentAssessment
    ku_content.py, ku_chunks.py, ku_metadata.py - Content & RAG
    ku_schedule.py     - Scheduling

Usage:
    from core.models.ku import Task, Goal, Habit, Event, Choice, Principle
    from core.models.ku import Curriculum, Exercise, LearningStep, LearningPath
    from core.models.ku import Submission, Journal, AiReport, Feedback
    from core.models.ku import Entity, UserOwnedEntity, Ku, EntityDTO, KuSchedule
"""

from .ai_report import AiReport
from .ai_report_dto import AiReportDTO
from .choice import Choice
from .choice_dto import ChoiceDTO
from .curriculum import Curriculum
from .curriculum_dto import CurriculumDTO
from .entity import Entity
from .entity_dto import EntityDTO
from .event import Event
from .event_dto import EventDTO
from .exercise import Exercise
from .exercise_dto import ExerciseDTO
from .exercise_request import (
    ExerciseCreateRequest,
    ExerciseUpdateRequest,
    FeedbackGenerateRequest,
)
from .feedback import Feedback
from .feedback_dto import FeedbackDTO
from .goal import Goal
from .goal_dto import GoalDTO
from .habit import Habit
from .habit_dto import HabitDTO
from .journal import Journal
from .journal_dto import JournalDTO
from .ku import ENTITY_TYPE_CLASS_MAP, ActivityEntity, CurriculumEntity, Ku, SubmissionEntity
from .ku_chunks import KuChunk, KuChunkType, chunk_content
from .ku_content import KuContent
from .ku_converters import ku_to_response
from .ku_metadata import KuMetadata
from .ku_nested_types import (
    AlignmentAssessment,
    ChoiceOption,
    Milestone,
    PrincipleExpression,
)
from .activity_requests import (
    ChoiceCreateRequest,
    ChoiceOptionRequest,
    EventCreateRequest,
    GoalCreateRequest,
    HabitCreateRequest,
    MilestoneRequest,
    PrincipleCreateRequest,
    PrincipleExpressionRequest,
    TaskCreateRequest,
)
from .curriculum_requests import (
    CurriculumCreateRequest,
    LearningPathCreateRequest,
    LearningStepCreateRequest,
    MocCreateRequest,
)
from .entity_requests import (
    AddTagsRequest,
    BulkCategorizeRequest,
    BulkDeleteRequest,
    BulkTagRequest,
    CategorizeEntityRequest,
    EntityListResponse,
    EntityResponse,
    EntityUpdateRequest,
    ProgressReportGenerateRequest,
    RemoveTagsRequest,
    ScheduleCreateRequest,
    ScheduleUpdateRequest,
)
from .report_requests import (
    AiReportCreateRequest,
    AssessmentCreateRequest,
    FeedbackCreateRequest,
    LifePathCreateRequest,
    SubmissionCreateRequest,
)
from .ku_schedule import (
    KuSchedule,
    KuScheduleDTO,
    ku_schedule_domain_to_dto,
    ku_schedule_dto_to_domain,
)
from .learning_path import LearningPath
from .learning_path_dto import LearningPathDTO
from .learning_step import LearningStep
from .learning_step_dto import LearningStepDTO
from .life_path import LifePath
from .life_path_dto import LifePathDTO
from .lp_position import LpPosition, create_lp_position
from .principle import Principle
from .principle_dto import PrincipleDTO
from .resource import Resource
from .resource_dto import ResourceDTO
from .submission import Submission
from .submission_dto import SubmissionDTO
from .task import Task
from .task_dto import TaskDTO
from .user_owned_dto import UserOwnedDTO
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
    # DTO hierarchy
    "EntityDTO",
    "UserOwnedDTO",
    "TaskDTO",
    "GoalDTO",
    "HabitDTO",
    "EventDTO",
    "ChoiceDTO",
    "PrincipleDTO",
    "SubmissionDTO",
    "JournalDTO",
    "AiReportDTO",
    "FeedbackDTO",
    "LifePathDTO",
    "CurriculumDTO",
    "LearningStepDTO",
    "LearningPathDTO",
    "ExerciseDTO",
    "ResourceDTO",
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
    "CurriculumCreateRequest",
    "SubmissionCreateRequest",
    "AiReportCreateRequest",
    "FeedbackCreateRequest",
    # API create requests — Activity Domains (6 new)
    "TaskCreateRequest",
    "GoalCreateRequest",
    "HabitCreateRequest",
    "EventCreateRequest",
    "ChoiceCreateRequest",
    "PrincipleCreateRequest",
    # API create requests — Shared/Curriculum (3 new)
    "MocCreateRequest",
    "LearningStepCreateRequest",
    "LearningPathCreateRequest",
    # API create requests — Destination (1 new)
    "LifePathCreateRequest",
    # API update/response
    "EntityUpdateRequest",
    "EntityResponse",
    "EntityListResponse",
    # Route-specific request models
    "AddTagsRequest",
    "RemoveTagsRequest",
    "BulkCategorizeRequest",
    "BulkTagRequest",
    "BulkDeleteRequest",
    "CategorizeEntityRequest",
    "ProgressReportGenerateRequest",
    "ScheduleCreateRequest",
    "ScheduleUpdateRequest",
    "AssessmentCreateRequest",
    # Exercise requests (instruction templates)
    "ExerciseCreateRequest",
    "ExerciseUpdateRequest",
    "FeedbackGenerateRequest",
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
