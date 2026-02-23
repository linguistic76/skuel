"""
LifePath - Life Path Domain Model
=====================================

Frozen dataclass for life path entities (EntityType.LIFE_PATH).

Inherits ~48 common fields from Entity. Adds 14 life-path-specific fields:
- Designation (2): life_path_uid, designated_at
- Alignment scores (3): alignment_score, word_action_gap, alignment_level
- Dimension scores (5): knowledge, activity, goal, principle, momentum
- Vision (3): vision_statement, vision_themes, vision_captured_at

Life-path-specific methods: is_designated, calculate_alignment_score,
get_weakest_dimension, get_summary, from_dto.

Note: LifePath is a designation on a Learning Path. When designated,
the LP's ku_type changes from 'learning_path' to 'life_path'.
Vision data lives on the User node. Alignment scores live on the
ULTIMATE_PATH relationship. These fields are hydrated onto the Ku
node for model consistency.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 9)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.entity_dto import EntityDTO
    from core.models.ku.life_path_dto import LifePathDTO

from core.models.enums.ku_enums import AlignmentLevel, EntityType
from core.models.ku.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class LifePath(UserOwnedEntity):
    """
    Immutable domain model for life path entities (EntityType.LIFE_PATH).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    sharing, meta, embedding, user_uid, priority).

    Adds 14 life-path-specific fields for designation, alignment scores,
    dimension scores, and vision metadata.
    """

    def __post_init__(self) -> None:
        """Force ku_type=LIFE_PATH, then delegate to UserOwnedEntity."""
        if self.ku_type != EntityType.LIFE_PATH:
            object.__setattr__(self, "ku_type", EntityType.LIFE_PATH)
        super().__post_init__()

    # =========================================================================
    # DESIGNATION (ULTIMATE_PATH relationship data)
    # =========================================================================
    life_path_uid: str | None = None  # LP designated as life path
    designated_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # ALIGNMENT SCORES
    # =========================================================================
    alignment_score: float = 0.0  # Overall 0.0-1.0 vision-to-action alignment
    word_action_gap: float = 0.0  # Vision vs. behavior gap
    alignment_level: AlignmentLevel | None = None

    # Dimension scores (weighted sum = alignment_score)
    knowledge_alignment: float = 0.0  # 25% — mastery of path knowledge
    activity_alignment: float = 0.0  # 25% — tasks/habits supporting path
    goal_alignment: float = 0.0  # 20% — active goals contributing
    principle_alignment: float = 0.0  # 15% — values supporting direction
    momentum: float = 0.0  # 15% — recent activity trend

    # =========================================================================
    # VISION (user's own words)
    # =========================================================================
    vision_statement: str | None = None  # User's vision in their words
    vision_themes: tuple[str, ...] = ()  # Extracted theme keywords
    vision_captured_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # LIFE-PATH-SPECIFIC METHODS
    # =========================================================================

    def is_designated(self) -> bool:
        """Check if this life path is currently designated."""
        return self.life_path_uid is not None

    def calculate_alignment_score(self) -> float:
        """Calculate overall alignment from 5 dimensions."""
        return (
            self.knowledge_alignment * 0.25
            + self.activity_alignment * 0.25
            + self.goal_alignment * 0.20
            + self.principle_alignment * 0.15
            + self.momentum * 0.15
        )

    def get_weakest_dimension(self) -> str:
        """Identify the dimension needing most attention."""
        dimensions = {
            "knowledge": self.knowledge_alignment,
            "activity": self.activity_alignment,
            "goal": self.goal_alignment,
            "principle": self.principle_alignment,
            "momentum": self.momentum,
        }
        return min(dimensions, key=dimensions.get)  # type: ignore[arg-type]

    # =========================================================================
    # OVERRIDES
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the life path."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | LifePathDTO") -> "LifePath":
        """Create LifePath from an EntityDTO or LifePathDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "LifePathDTO":  # type: ignore[override]
        """Convert LifePath to domain-specific LifePathDTO."""
        import dataclasses
        from typing import Any

        from core.models.ku.life_path_dto import LifePathDTO

        dto_field_names = {f.name for f in dataclasses.fields(LifePathDTO)}
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
        return LifePathDTO(**kwargs)

    def __str__(self) -> str:
        return f"LifePath(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LifePath(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, alignment={self.alignment_score:.2f}, "
            f"user_uid={self.user_uid})"
        )
