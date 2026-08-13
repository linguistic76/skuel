"""
LearningPath - Learning Path Domain Model
=============================================

Frozen dataclass for learning path entities (EntityType.LEARNING_PATH).

Inherits common fields from Entity via Curriculum. Adds 4 learning-path-specific fields:
- Path configuration (4): path_type, outcomes, checkpoint_week_intervals, estimated_hours

Learning-path-specific methods/properties: steps, goal, get_summary, from_dto.

Note: LP steps are graph relationships (HAS_STEP), not model attributes.
The `steps` property returns an empty tuple — use LpService.get_steps() instead.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.pathways.learning_path_dto import LearningPathDTO

from core.models.curriculum import Curriculum
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

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.LEARNING_PATH, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=LEARNING_PATH, then delegate to Entity."""
        if self.entity_type != EntityType.LEARNING_PATH:
            raise ValueError(
                f"LearningPath constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
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
    def from_dto(cls, dto: "EntityDTO | LearningPathDTO") -> "LearningPath":
        """Create LearningPath from an EntityDTO or LearningPathDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "LearningPathDTO":
        """Convert LearningPath to domain-specific LearningPathDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.pathways.learning_path_dto import LearningPathDTO

        return domain_to_dto(self, LearningPathDTO)

    def __str__(self) -> str:
        return f"LearningPath(uid={self.uid}, path_type={self.path_type}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LearningPath(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, path_type={self.path_type}, "
            f"outcomes={len(self.outcomes)})"
        )
