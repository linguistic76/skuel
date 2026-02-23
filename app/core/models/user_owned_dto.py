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
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.ports import get_enum_value


@dataclass
class UserOwnedDTO(EntityDTO):
    """
    Mutable DTO for user-owned entities.

    Extends EntityDTO with:
    - user_uid: Owner user UID
    - priority: Priority enum value
    - visibility: PRIVATE by default (vs PUBLIC for shared types)
    """

    # =========================================================================
    # USER OWNERSHIP
    # =========================================================================
    user_uid: str | None = None
    priority: str | None = None

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = Visibility.PRIVATE

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including user ownership fields."""
        data = super().to_dict()
        data["user_uid"] = self.user_uid
        data["priority"] = self.priority
        data["visibility"] = get_enum_value(self.visibility)
        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserOwnedDTO:
        """Create DTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
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
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
            },
            enum_mappings={
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
        )
