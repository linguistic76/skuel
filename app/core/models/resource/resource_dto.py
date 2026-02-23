"""
ResourceDTO - Resource-Specific DTO (Tier 2 - Transfer)
=========================================================

Extends EntityDTO (NOT UserOwnedDTO) with 7 resource-specific fields
matching the Resource frozen dataclass (Tier 3): source, publication,
and media information.

Resources are admin-curated shared content (Tier A). They inherit from
Entity directly, NOT from Curriculum (no learning metadata/substance).

Hierarchy:
    EntityDTO (~18 common fields)
    └── ResourceDTO(EntityDTO) +7 resource-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.entity_dto import EntityDTO


@dataclass
class ResourceDTO(EntityDTO):
    """
    Mutable DTO for resources (EntityType.RESOURCE).

    Extends EntityDTO with 7 resource-specific fields:
    - Source (3): source_url, author, publisher
    - Publication (2): publication_year, isbn
    - Media (2): media_type, resource_duration_minutes
    """

    # =========================================================================
    # SOURCE
    # =========================================================================
    source_url: str | None = None
    author: str | None = None
    publisher: str | None = None

    # =========================================================================
    # PUBLICATION
    # =========================================================================
    publication_year: int | None = None
    isbn: str | None = None

    # =========================================================================
    # MEDIA
    # =========================================================================
    media_type: str | None = None
    resource_duration_minutes: int | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including resource-specific fields."""
        data = super().to_dict()

        data.update(
            {
                "source_url": self.source_url,
                "author": self.author,
                "publisher": self.publisher,
                "publication_year": self.publication_year,
                "isbn": self.isbn,
                "media_type": self.media_type,
                "resource_duration_minutes": self.resource_duration_minutes,
            }
        )

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceDTO:
        """Create ResourceDTO from dictionary (from database)."""
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
            list_fields=["tags"],
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
                # Resource-specific fields
                "source_url", "author", "publisher",
                "publication_year", "isbn",
                "media_type", "resource_duration_minutes",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ResourceDTO):
            return False
        return self.uid == other.uid
