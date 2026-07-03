"""
InteractionDTO - Interaction-Specific DTO (Tier 2 - Transfer)
=============================================================

Extends UserOwnedDTO with 6 interaction-specific fields matching the
Interaction frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── InteractionDTO(UserOwnedDTO) +6 interaction-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.interaction_enums import InteractionResult, InteractionType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class InteractionDTO(UserOwnedDTO):
    """
    Mutable DTO for situated learning-loop events (EntityType.INTERACTION).

    Extends UserOwnedDTO with 6 interaction-specific fields:
    - Interaction type + target (2): interaction_type, target_uid
    - Curriculum context (2): context_path_step_uid, context_learning_path_uid
    - Source + result (2): source_entity_uid, result_status
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.INTERACTION, kw_only=True)

    # =========================================================================
    # INTERACTION TYPE + TARGET
    # =========================================================================
    interaction_type: InteractionType | None = None
    target_uid: str | None = None

    # =========================================================================
    # CURRICULUM CONTEXT
    # =========================================================================
    context_path_step_uid: str | None = None
    context_learning_path_uid: str | None = None

    # =========================================================================
    # SOURCE + RESULT
    # =========================================================================
    source_entity_uid: str | None = None
    result_status: InteractionResult | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "visibility",
                "interaction_type",
                "result_status",
            ],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InteractionDTO:
        """Create InteractionDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "visibility": Visibility,
                "interaction_type": InteractionType,
                "result_status": InteractionResult,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags"],
            dict_fields=["metadata"],
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
                "title",
                "description",
                "content",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
                # Interaction-specific fields
                "result_status",
            },
            enum_mappings={
                "status": EntityStatus,
                "visibility": Visibility,
                "result_status": InteractionResult,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, InteractionDTO):
            return False
        return self.uid == other.uid
