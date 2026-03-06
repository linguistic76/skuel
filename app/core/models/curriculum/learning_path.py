"""
LearningPath - Learning Path Domain Model
=============================================

Frozen dataclass for learning path entities (EntityType.LEARNING_PATH).

Inherits common fields from Entity via Curriculum. Adds 4 learning-path-specific fields:
- Path configuration (4): path_type, outcomes, checkpoint_week_intervals, estimated_hours

Learning-path-specific methods/properties: steps, goal, get_summary, from_dto.

Note: LP steps are graph relationships (HAS_STEP), not model attributes.
The `steps` property returns an empty tuple — use LpService.get_steps() instead.

See: /.claude/plans/crispy-spinning-wozniak.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.curriculum.learning_path_dto import LearningPathDTO
    from core.models.entity_dto import EntityDTO

from core.models.curriculum.curriculum import Curriculum
from core.models.enums.curriculum_enums import LpType
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class LearningPath(Curriculum):
    """
    Immutable domain model for learning paths (EntityType.LEARNING_PATH).

    Inherits ~50 fields from Curriculum (Entity fields + learning metadata
    + substance tracking). Adds 4 learning-path-specific fields for path
    configuration. Steps are graph relationships (HAS_STEP), not model attributes.
    """

    def __post_init__(self) -> None:
        """Force entity_type=LEARNING_PATH, then delegate to Entity."""
        if self.entity_type != EntityType.LEARNING_PATH:
            object.__setattr__(self, "entity_type", EntityType.LEARNING_PATH)
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
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | LearningPathDTO") -> "LearningPath":  # type: ignore[override]
        """Create LearningPath from an EntityDTO or LearningPathDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "LearningPathDTO":  # type: ignore[override]
        """Convert LearningPath to domain-specific LearningPathDTO."""
        import dataclasses
        from typing import Any

        from core.models.curriculum.learning_path_dto import LearningPathDTO

        dto_field_names = {f.name for f in dataclasses.fields(LearningPathDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return LearningPathDTO(**kwargs)

    def __str__(self) -> str:
        return f"LearningPath(uid={self.uid}, path_type={self.path_type}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LearningPath(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, path_type={self.path_type}, "
            f"outcomes={len(self.outcomes)})"
        )
