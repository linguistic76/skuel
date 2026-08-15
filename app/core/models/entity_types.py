"""
Entity Type Aliases and Class Dispatch Map
==========================================

Type aliases and the EntityType→class map for all 25 entity types.

For construction: Use the specific subclass (Task, Ku, Goal, etc.)
For dispatched deserialization: Use Entity.from_dto(dto)
For type annotations: Use Entity (base type for all domain models)
For domain-specific annotations: Use ActivityEntity, CurriculumEntity, SubmissionEntity

ENTITY_TYPE_CLASS_MAP maps each EntityType enum to its domain-specific subclass.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.models.choice.choice import Choice
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.exercises.exercise import Exercise
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_template import FormTemplate
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.interaction.interaction import Interaction
from core.models.ku.ku import Ku
from core.models.life_path.life_path import LifePath
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.report.activity_report import ActivityReport
from core.models.report.entry_report import EntryReport
from core.models.resource.resource import Resource
from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.task_template import TaskTemplate
from core.models.user_entry.user_entry import UserEntry

# =============================================================================
# NARROWER TYPE ALIASES — for services that handle a subset of entity types
#
# Use these instead of Entity when a service only handles a specific domain group.
# =============================================================================

# Activity entities — user-owned entities with user_uid and priority
ActivityEntity = Task | Goal | Habit | Event | Choice | Principle

# Curriculum entities — carry learning_level, quality_score, sel_category, etc.
# PathStep is THE curriculum content entity; Curriculum is the base class.
CurriculumEntity = PathStep | LearningPath | Exercise

# Atomic Ku — lightweight ontology/reference node (extends Entity directly, not Curriculum)
KuEntity = Ku

# User-authored entry — ADR-054 unified type. Replaces the old
# SubmissionEntity/JournalEntity unions. Kept as aliases during the pre-6b
# shelving window so existing imports resolve to UserEntry.
SubmissionEntity = UserEntry
JournalEntity = UserEntry

# Report entities — report output (no file fields, report-specific fields)
ReportEntity = ActivityReport | EntryReport

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
    EntityType.PATH_STEP: PathStep,
    EntityType.LEARNING_PATH: LearningPath,
    EntityType.EXERCISE: Exercise,
    EntityType.REVISED_EXERCISE: RevisedExercise,
    EntityType.USER_ENTRY: UserEntry,
    EntityType.ACTIVITY_REPORT: ActivityReport,
    EntityType.ENTRY_REPORT: EntryReport,
    EntityType.FORM_TEMPLATE: FormTemplate,
    EntityType.FORM_SUBMISSION: FormSubmission,
    EntityType.INTERACTION: Interaction,
    EntityType.LIFE_PATH: LifePath,
    # Activity Templates (Phase 2 — PS-owned, spawn user-owned instances)
    EntityType.TASK_TEMPLATE: TaskTemplate,
    EntityType.GOAL_TEMPLATE: GoalTemplate,
    EntityType.HABIT_TEMPLATE: HabitTemplate,
    EntityType.EVENT_TEMPLATE: EventTemplate,
    EntityType.CHOICE_TEMPLATE: ChoiceTemplate,
    EntityType.PRINCIPLE_TEMPLATE: PrincipleTemplate,
}
