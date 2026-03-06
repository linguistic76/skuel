"""
EntityDTO - Base DTO for All Entity Types (Tier 2 - Transfer)
==============================================================

Mutable data transfer object with ~18 fields common to ALL entity types.
Mirrors the Entity frozen dataclass (Tier 3) fields.

Hierarchy:
    EntityDTO (~18 common fields)
    ├── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
    │   └── TaskDTO(UserOwnedDTO) +25 task-specific fields
    │   └── (future: GoalDTO, HabitDTO, etc.)
    └── (future: CurriculumDTO, ResourceDTO)

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.ports import get_enum_value


@dataclass
class EntityDTO:
    """
    Mutable base DTO for all entity types.

    Contains ~18 fields matching Entity (frozen dataclass):
    Identity (6), Content (4), Status (1), Meta (4+3 embedding).

    Subclasses add domain-specific fields.
    """

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str = ""
    title: str = ""
    entity_type: EntityType = EntityType.KU
    parent_entity_uid: str | None = None
    domain: Domain = Domain.KNOWLEDGE
    created_by: str | None = None

    # =========================================================================
    # CONTENT
    # =========================================================================
    content: str | None = None
    summary: str = ""
    description: str | None = None
    word_count: int = 0

    # =========================================================================
    # STATUS
    # =========================================================================
    status: EntityStatus = EntityStatus.DRAFT

    # =========================================================================
    # META
    # =========================================================================
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data: dict[str, Any] = {
            "uid": self.uid,
            "title": self.title,
            "entity_type": get_enum_value(self.entity_type),
            "parent_entity_uid": self.parent_entity_uid,
            "domain": get_enum_value(self.domain),
            "created_by": self.created_by,
            "content": self.content,
            "summary": self.summary,
            "description": self.description,
            "word_count": self.word_count,
            "status": get_enum_value(self.status),
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata) if self.metadata else {},
        }

        convert_datetimes_to_iso(data, ["created_at", "updated_at"])
        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityDTO:
        """Create DTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
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
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, EntityDTO):
            return False
        return self.uid == other.uid
