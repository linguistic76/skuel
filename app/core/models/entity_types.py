"""
Entity Type Aliases and Class Dispatch Map
==========================================

Type aliases and the EntityType→class map for all 21 entity types.

For construction: Use the specific subclass (Task, Ku, Goal, etc.)
For dispatched deserialization: Use Entity.from_dto(dto)
For type annotations: Use Entity (base type for all domain models)
For domain-specific annotations: Use ActivityEntity, CurriculumEntity, SubmissionEntity

ENTITY_TYPE_CLASS_MAP maps each EntityType enum to its domain-specific subclass.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from core.models.lesson.lesson import Lesson
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
from core.models.ku.ku import Ku
from core.models.life_path.life_path import LifePath
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.learning_step import LearningStep
from core.models.principle.principle import Principle
from core.models.report.activity_report import ActivityReport
from core.models.report.exercise_report import ExerciseReport
from core.models.report.journal_report import JournalReport
from core.models.report.submission_report import SubmissionReport
from core.models.resource.resource import Resource
from core.models.submissions.exercise_submission import ExerciseSubmission
from core.models.submissions.journal import Journal
from core.models.submissions.journal_submission import JournalSubmission
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
# Lesson is the narrative curriculum leaf; Curriculum is the base class.
CurriculumEntity = Lesson | LearningStep | LearningPath | Exercise

# Atomic Ku — lightweight ontology/reference node (extends Entity directly, not Curriculum)
KuEntity = Ku

# Submission entities — carry file_path, processed_content, file_type, etc.
SubmissionEntity = Submission | ExerciseSubmission | JournalSubmission | Journal

# Report entities — report output (no file fields, report-specific fields)
ReportEntity = ActivityReport | SubmissionReport | ExerciseReport | JournalReport

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
    EntityType.LESSON: Lesson,
    EntityType.KU: Ku,
    EntityType.RESOURCE: Resource,
    EntityType.LEARNING_STEP: LearningStep,
    EntityType.LEARNING_PATH: LearningPath,
    EntityType.EXERCISE: Exercise,
    EntityType.REVISED_EXERCISE: RevisedExercise,
    EntityType.EXERCISE_SUBMISSION: ExerciseSubmission,
    EntityType.JOURNAL_SUBMISSION: JournalSubmission,
    EntityType.ACTIVITY_REPORT: ActivityReport,
    EntityType.EXERCISE_REPORT: ExerciseReport,
    EntityType.JOURNAL_REPORT: JournalReport,
    EntityType.FORM_TEMPLATE: FormTemplate,
    EntityType.FORM_SUBMISSION: FormSubmission,
    EntityType.LIFE_PATH: LifePath,
    # Deprecated aliases — kept for backward compat during migration
    EntityType.SUBMISSION: Submission,
    EntityType.JOURNAL: Journal,
    EntityType.SUBMISSION_REPORT: SubmissionReport,
}
