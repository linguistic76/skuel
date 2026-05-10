"""PrincipleTemplateDTO — Transfer tier for PrincipleTemplate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import (
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)


@dataclass
class PrincipleTemplateDTO(EntityDTO):
    """Mutable DTO for PrincipleTemplate entities."""

    # Statement
    statement: str | None = None

    # Classification
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # Philosophical
    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    # Expressions
    expressions: list[dict[str, Any]] = field(default_factory=list)
    key_behaviors: list[str] = field(default_factory=list)

    # Conflicts
    potential_conflicts: list[str] = field(default_factory=list)
    conflicting_principles: list[str] = field(default_factory=list)
    resolution_strategies: list[str] = field(default_factory=list)

    # Reflection
    origin_story: str | None = None
    evolution_notes: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=[
                "entity_type",
                "status",
                "domain",
                "principle_category",
                "principle_source",
                "strength",
            ],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrincipleTemplateDTO:
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "expressions",
                "key_behaviors",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
            ],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
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
                # PrincipleTemplate-specific
                "statement",
                "principle_category",
                "principle_source",
                "strength",
                "tradition",
                "original_source",
                "personal_interpretation",
                "expressions",
                "key_behaviors",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
                "origin_story",
                "evolution_notes",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
            },
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PrincipleTemplateDTO):
            return False
        return self.uid == other.uid
