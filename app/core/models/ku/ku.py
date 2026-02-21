"""
Ku - Union Type for Domain-Specific Knowledge Types
=====================================================

After Phase 10 decomposition, Ku is a Union type alias representing any of the
15 domain-specific frozen dataclasses. The God Object is gone.

For construction: Use the specific subclass (TaskKu, GoalKu, etc.)
For dispatched deserialization: Use KuBase.from_dto(dto)
For type annotations: Use Ku (union of all subclasses) or KuBase (common base)

KU_TYPE_CLASS_MAP maps each KuType enum to its domain-specific subclass.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from core.models.enums.ku_enums import KuType
from core.models.ku.ku_ai_report import AiReportKu
from core.models.ku.ku_base import KuBase
from core.models.ku.ku_choice import ChoiceKu
from core.models.ku.ku_curriculum import CurriculumKu
from core.models.ku.ku_event import EventKu
from core.models.ku.ku_feedback import FeedbackKu
from core.models.ku.ku_goal import GoalKu
from core.models.ku.ku_habit import HabitKu
from core.models.ku.ku_journal import JournalKu
from core.models.ku.ku_learning_path import LearningPathKu
from core.models.ku.ku_learning_step import LearningStepKu
from core.models.ku.ku_life_path import LifePathKu
from core.models.ku.ku_principle import PrincipleKu
from core.models.ku.ku_resource import ResourceKu
from core.models.ku.ku_submission import SubmissionKu
from core.models.ku.ku_task import TaskKu

# =============================================================================
# UNION TYPE — for type annotations
#
# Ku can appear in type hints wherever any KuBase subclass is acceptable.
# For isinstance checks, use isinstance(x, KuBase).
# =============================================================================
Ku = (
    TaskKu
    | GoalKu
    | HabitKu
    | EventKu
    | ChoiceKu
    | PrincipleKu
    | CurriculumKu
    | ResourceKu
    | LearningStepKu
    | LearningPathKu
    | SubmissionKu
    | JournalKu
    | AiReportKu
    | FeedbackKu
    | LifePathKu
)

# =============================================================================
# TYPE CLASS MAP — dispatcher for Ku decomposition
#
# Maps KuType to domain-specific subclass. Used by KuBase.from_dto() dispatcher
# and cross-domain deserialization.
# =============================================================================
KU_TYPE_CLASS_MAP: dict[KuType, type[KuBase]] = {
    KuType.TASK: TaskKu,
    KuType.GOAL: GoalKu,
    KuType.HABIT: HabitKu,
    KuType.EVENT: EventKu,
    KuType.CHOICE: ChoiceKu,
    KuType.PRINCIPLE: PrincipleKu,
    KuType.CURRICULUM: CurriculumKu,
    KuType.RESOURCE: ResourceKu,
    KuType.LEARNING_STEP: LearningStepKu,
    KuType.LEARNING_PATH: LearningPathKu,
    KuType.SUBMISSION: SubmissionKu,
    KuType.JOURNAL: JournalKu,
    KuType.AI_REPORT: AiReportKu,
    KuType.FEEDBACK_REPORT: FeedbackKu,
    KuType.LIFE_PATH: LifePathKu,
}
