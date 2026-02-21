"""
LearningPathKu - Learning Path Domain Model
=============================================

Frozen dataclass for learning path entities (KuType.LEARNING_PATH).

Inherits common fields from KuBase via CurriculumKu. Adds 4 learning-path-specific fields:
- Path configuration (4): path_type, outcomes, checkpoint_week_intervals, estimated_hours

Learning-path-specific methods/properties: steps, goal, get_summary, from_dto.

Note: LP steps are graph relationships (HAS_STEP), not model attributes.
The `steps` property returns an empty tuple — use LpService.get_steps() instead.

See: /.claude/plans/crispy-spinning-wozniak.md
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType, LpType
from core.models.ku.ku_curriculum import CurriculumKu


@dataclass(frozen=True)
class LearningPathKu(CurriculumKu):
    """
    Immutable domain model for learning paths (KuType.LEARNING_PATH).

    Inherits ~50 fields from CurriculumKu (KuBase fields + learning metadata
    + substance tracking). Adds 4 learning-path-specific fields for path
    configuration. Steps are graph relationships (HAS_STEP), not model attributes.
    """

    def __post_init__(self) -> None:
        """Force ku_type=LEARNING_PATH, then delegate to KuBase."""
        if self.ku_type != KuType.LEARNING_PATH:
            object.__setattr__(self, "ku_type", KuType.LEARNING_PATH)
        super().__post_init__()

    # =========================================================================
    # PATH CONFIGURATION
    # =========================================================================
    path_type: LpType | None = None
    outcomes: tuple[str, ...] = ()  # Expected learning outcomes
    checkpoint_week_intervals: tuple[int, ...] = ()  # Milestone week intervals
    estimated_hours: float | None = None  # Estimated total hours for this path

    # =========================================================================
    # LEARNING-PATH-SPECIFIC METHODS
    # =========================================================================

    @property
    def steps(self) -> tuple:
        """LP steps are graph relationships (HAS_STEP), not model attributes.

        Always returns empty tuple. Use LpService.get_path_steps(uid) for actual steps.
        """
        return ()

    @property
    def goal(self) -> str:
        """LP goal -- alias for description."""
        return self.description or ""

    # =========================================================================
    # OVERRIDES
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the learning path."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION (generic -- uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "LearningPathKu":
        """Create LearningPathKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"LearningPathKu(uid={self.uid}, path_type={self.path_type}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LearningPathKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, path_type={self.path_type}, "
            f"outcomes={len(self.outcomes)}, user_uid={self.user_uid})"
        )
