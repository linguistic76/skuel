"""
UserOwnedDTO - DTO for User-Owned Entity Types (Tier 2 - Transfer)
===================================================================

Extends EntityDTO with user ownership fields (user_uid, priority, visibility).
Mirrors the UserOwnedEntity frozen dataclass (Tier 3) fields.

Used by: Activity Domains (Task, Goal, Habit, Event, Choice, Principle),
         Submission types, LifePath.

Hierarchy:
    EntityDTO (~18 common fields)
    ├── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
    │   └── TaskDTO(UserOwnedDTO) +25 task-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.activity_enums import Priority
from core.models.enums.metadata_enums import Visibility
from core.models.type_hints import UserUID


@dataclass
class UserOwnedDTO(EntityDTO):
    """
    Mutable DTO for user-owned entities.

    Extends EntityDTO with:
    - user_uid: Owner user UID
    - priority: the entity's Priority, or None when it states none
    - visibility: PRIVATE by default (vs PUBLIC for shared types)
    """

    # =========================================================================
    # USER OWNERSHIP
    # =========================================================================
    user_uid: UserUID | None = None
    priority: Priority | None = None

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = Visibility.PRIVATE

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "visibility", "priority"],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserOwnedDTO:
        """Create DTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type", "status", "domain", "visibility", "priority"
            ),
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags"],
            dict_fields=["metadata"],
        )
