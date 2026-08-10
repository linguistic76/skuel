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

from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.entity_enums import EntityType


@dataclass
class KuDTO(EntityDTO):
    """Mutable DTO for atomic knowledge unit entities (EntityType.KU).

    Extends EntityDTO with 4 Ku-specific fields:
      - aliases: alternative names
      - sel_category: SEL competency (self_awareness, self_management, etc.)
      - nous: NOUS topic membership (stories, body, self-awareness, ...)
      - nous_subtopic: NOUS sub-topic membership (2nd level — nervous-system, ...)
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.KU, kw_only=True)

    aliases: list[str] | None = None
    sel_category: str | None = None
    publication_state: PublicationState = PublicationState.PUBLISHED
    # NOUS topic membership (stories, body, self-awareness, ...) — multi-topic;
    # empty = deliberately unassigned (rawness principle)
    nous: list[str] | None = None
    # NOUS sub-topic membership (2nd taxonomy level — nervous-system, sleep, ...);
    # mirrors `nous`, multi-valued, empty = deliberately unassigned
    nous_subtopic: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "sel_category", "publication_state"],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KuDTO:
        """Create KuDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type", "status", "domain", "sel_category", "publication_state"
            ),
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags", "aliases", "nous", "nous_subtopic"],
            dict_fields=["metadata"],
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
                "aliases",
                "sel_category",
                "publication_state",
                "nous",
                "nous_subtopic",
            },
            enum_mappings=enum_fields_for(
                "entity_type", "status", "domain", "sel_category", "publication_state"
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, KuDTO):
            return False
        return self.uid == other.uid
