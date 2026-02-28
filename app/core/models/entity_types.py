"""
Entity Type Aliases and Class Dispatch Map
==========================================

Type aliases and the EntityType→class map for all 16 domain models.

For construction: Use the specific subclass (Task, Ku, Goal, etc.)
For dispatched deserialization: Use Entity.from_dto(dto)
For type annotations: Use Entity (base type for all domain models)
For domain-specific annotations: Use ActivityEntity, CurriculumEntity, SubmissionEntity

ENTITY_TYPE_CLASS_MAP maps each EntityType enum to its domain-specific subclass.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from core.models.choice.choice import Choice
from core.models.curriculum.exercise import Exercise
from core.models.curriculum.ku import Ku
from core.models.curriculum.learning_path import LearningPath
from core.models.curriculum.learning_step import LearningStep
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.feedback.ai_feedback import AiFeedback
from core.models.feedback.feedback import Feedback
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.life_path.life_path import LifePath
from core.models.principle.principle import Principle
from core.models.resource.resource import Resource
from core.models.submissions.journal import Journal
from core.models.submissions.submission import Submission
from core.models.task.task import Task

# =============================================================================
# NARROWER TYPE ALIASES — for services that handle a subset of entity types
#
# Use these instead of Entity when a service only handles a specific domain group.
# =============================================================================

# Activity entities — user-owned entities with user_uid and priority
ActivityEntity = Task | Goal | Habit | Event | Choice | Principle

# Curriculum entities — carry learning_level, quality_score, sel_category, etc.
# Ku is the atomic leaf; Curriculum is the base class.
CurriculumEntity = Ku | LearningStep | LearningPath | Exercise

# Submission entities — carry file_path, processed_content, file_type, etc.
SubmissionEntity = Submission | Journal | AiFeedback | Feedback

# =============================================================================
# TYPE CLASS MAP — dispatcher for entity deserialization
#
# Maps EntityType to domain-specific subclass. Used by Entity.from_dto() dispatcher
# and cross-domain deserialization.
# =============================================================================
ENTITY_TYPE_CLASS_MAP: dict[EntityType, type[Entity]] = {
    EntityType.TASK: Task,
    EntityType.GOAL: Goal,
    EntityType.HABIT: Habit,
    EntityType.EVENT: Event,
    EntityType.CHOICE: Choice,
    EntityType.PRINCIPLE: Principle,
    EntityType.KU: Ku,
    EntityType.RESOURCE: Resource,
    EntityType.LEARNING_STEP: LearningStep,
    EntityType.LEARNING_PATH: LearningPath,
    EntityType.EXERCISE: Exercise,
    EntityType.SUBMISSION: Submission,
    EntityType.JOURNAL: Journal,
    EntityType.AI_FEEDBACK: AiFeedback,
    EntityType.FEEDBACK_REPORT: Feedback,
    EntityType.LIFE_PATH: LifePath,
}
