"""
KuDTO - Atomic Knowledge Unit DTO (Tier 2 - Transfer)
=====================================================

Mutable DTO for atomic knowledge unit entities (EntityType.KU).
Extends EntityDTO (NOT CurriculumDTO) with 4 Ku-specific fields.

Ku is lightweight — no learning metadata, no substance scores.

Hierarchy:
    EntityDTO (~18 common fields)
    └── KuDTO(EntityDTO) +4 Ku-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType


@dataclass
class KuDTO(EntityDTO):
    """Mutable DTO for atomic knowledge unit entities (EntityType.KU).

    Extends EntityDTO with 4 Ku-specific fields:
    - namespace: primary grouping (attention, emotion, body, ...)
    - ku_category: state/concept/principle/intake/substance/practice/value
    - aliases: alternative names
    - source: self_observation/research/teacher
    """

    namespace: str | None = None
    ku_category: str | None = None
    aliases: list[str] | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including Ku-specific fields."""
        data = super().to_dict()
        data.update(
            {
                "namespace": self.namespace,
                "ku_category": self.ku_category,
                "aliases": self.aliases,
                "source": self.source,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KuDTO:
        """Create KuDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "aliases"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
        )

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
                # Ku-specific fields
                "namespace",
                "ku_category",
                "aliases",
                "source",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, KuDTO):
            return False
        return self.uid == other.uid
