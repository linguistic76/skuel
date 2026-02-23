"""
LifePathDTO - Life Path-Specific DTO (Tier 2 - Transfer)
==========================================================

Extends UserOwnedDTO with 14 life-path-specific fields matching the
LifePath frozen dataclass (Tier 3): designation, alignment scores,
dimension scores, and vision metadata.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── LifePathDTO(UserOwnedDTO) +14 life-path-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import AlignmentLevel, EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO
from core.ports import get_enum_value


@dataclass
class LifePathDTO(UserOwnedDTO):
    """
    Mutable DTO for life paths (EntityType.LIFE_PATH).

    Extends UserOwnedDTO with 14 life-path-specific fields:
    - Designation (2): life_path_uid, designated_at
    - Alignment (3): alignment_score, word_action_gap, alignment_level
    - Dimensions (5): knowledge, activity, goal, principle, momentum
    - Vision (3): vision_statement, vision_themes, vision_captured_at
    """

    # =========================================================================
    # DESIGNATION
    # =========================================================================
    life_path_uid: str | None = None
    designated_at: datetime | None = None

    # =========================================================================
    # ALIGNMENT SCORES
    # =========================================================================
    alignment_score: float = 0.0
    word_action_gap: float = 0.0
    alignment_level: AlignmentLevel | None = None

    # =========================================================================
    # DIMENSION SCORES
    # =========================================================================
    knowledge_alignment: float = 0.0
    activity_alignment: float = 0.0
    goal_alignment: float = 0.0
    principle_alignment: float = 0.0
    momentum: float = 0.0

    # =========================================================================
    # VISION
    # =========================================================================
    vision_statement: str | None = None
    vision_themes: list[str] = field(default_factory=list)
    vision_captured_at: datetime | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including life-path-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                # Designation
                "life_path_uid": self.life_path_uid,
                "designated_at": self.designated_at,
                # Alignment
                "alignment_score": self.alignment_score,
                "word_action_gap": self.word_action_gap,
                "alignment_level": get_enum_value(self.alignment_level),
                # Dimensions
                "knowledge_alignment": self.knowledge_alignment,
                "activity_alignment": self.activity_alignment,
                "goal_alignment": self.goal_alignment,
                "principle_alignment": self.principle_alignment,
                "momentum": self.momentum,
                # Vision
                "vision_statement": self.vision_statement,
                "vision_themes": list(self.vision_themes) if self.vision_themes else [],
                "vision_captured_at": self.vision_captured_at,
            }
        )

        convert_datetimes_to_iso(data, ["designated_at", "vision_captured_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LifePathDTO:
        """Create LifePathDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "alignment_level": AlignmentLevel,
            },
            datetime_fields=[
                "created_at", "updated_at",
                "designated_at", "vision_captured_at",
            ],
            list_fields=["tags", "vision_themes"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # EntityDTO fields
                "title", "content", "summary", "description", "word_count",
                "domain", "status", "tags", "metadata",
                # UserOwnedDTO fields
                "priority", "visibility",
                # LifePath-specific fields
                "life_path_uid", "designated_at",
                "alignment_score", "word_action_gap", "alignment_level",
                "knowledge_alignment", "activity_alignment", "goal_alignment",
                "principle_alignment", "momentum",
                "vision_statement", "vision_themes", "vision_captured_at",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "alignment_level": AlignmentLevel,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, LifePathDTO):
            return False
        return self.uid == other.uid
