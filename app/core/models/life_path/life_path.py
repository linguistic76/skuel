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

Note: LifePath is a designation on a Learning Path, carried entirely by the
ULTIMATE_PATH edge — designation does NOT change the LearningPath node, which
keeps its label and its 'learning_path' entity_type throughout. Vision data
lives on the User node. Alignment scores live on the ULTIMATE_PATH
relationship. These fields are hydrated for model consistency; nothing
persists a node with entity_type 'life_path' as a result of designation.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.life_path.life_path_dto import LifePathDTO

from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import AlignmentLevel
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class LifePath(UserOwnedEntity):
    """
    Immutable domain model for life path entities (EntityType.LIFE_PATH).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    sharing, meta, embedding, user_uid, priority).

    Adds 14 life-path-specific fields for designation, alignment scores,
    dimension scores, and vision metadata.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.LIFE_PATH, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=LIFE_PATH, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.LIFE_PATH:
            raise ValueError(
                f"LifePath constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # DESIGNATION (ULTIMATE_PATH relationship data)
    # =========================================================================
    life_path_uid: str | None = None  # LP designated as life path
    designated_at: datetime | None = None

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
    vision_captured_at: datetime | None = None

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
        from core.utils.sort_functions import make_dict_value_getter

        dimensions = {
            "knowledge": self.knowledge_alignment,
            "activity": self.activity_alignment,
            "goal": self.goal_alignment,
            "principle": self.principle_alignment,
            "momentum": self.momentum,
        }
        return min(dimensions, key=make_dict_value_getter(dimensions))

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

    def to_dto(self) -> "LifePathDTO":
        """Convert LifePath to domain-specific LifePathDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.life_path.life_path_dto import LifePathDTO

        return domain_to_dto(self, LifePathDTO)

    def __str__(self) -> str:
        return f"LifePath(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LifePath(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, alignment={self.alignment_score:.2f}, "
            f"user_uid={self.user_uid})"
        )
