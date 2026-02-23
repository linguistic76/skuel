"""
PrincipleDTO - Principle-Specific DTO (Tier 2 - Transfer)
==========================================================

Extends UserOwnedDTO with 19 principle-specific fields matching the Principle
frozen dataclass (Tier 3): statement, classification, philosophy, expressions,
alignment, conflicts, reflection, and status.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── PrincipleDTO(UserOwnedDTO) +19 principle-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import (
    AlignmentLevel,
    EntityStatus,
    EntityType,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class PrincipleDTO(UserOwnedDTO):
    """
    Mutable DTO for principles (EntityType.PRINCIPLE).

    Extends UserOwnedDTO with 19 principle-specific fields:
    - Statement (1): statement
    - Classification (3): principle_category, principle_source, strength
    - Philosophical (3): tradition, original_source, personal_interpretation
    - Expressions (2): expressions, key_behaviors
    - Alignment (3): current_alignment, alignment_history, last_review_date
    - Conflicts (3): potential_conflicts, conflicting_principles, resolution_strategies
    - Reflection (2): origin_story, evolution_notes
    - Status (2): is_active, adopted_date
    """

    # =========================================================================
    # STATEMENT
    # =========================================================================
    statement: str | None = None

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # =========================================================================
    # PHILOSOPHICAL CONTEXT
    # =========================================================================
    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    # =========================================================================
    # EXPRESSIONS & APPLICATIONS
    # =========================================================================
    expressions: list[dict[str, Any]] = field(default_factory=list)
    key_behaviors: list[str] = field(default_factory=list)

    # =========================================================================
    # ALIGNMENT TRACKING
    # =========================================================================
    current_alignment: AlignmentLevel | None = None
    alignment_history: list[dict[str, Any]] = field(default_factory=list)
    last_review_date: date | None = None

    # =========================================================================
    # CONFLICTS & TENSIONS
    # =========================================================================
    potential_conflicts: list[str] = field(default_factory=list)
    conflicting_principles: list[str] = field(default_factory=list)
    resolution_strategies: list[str] = field(default_factory=list)

    # =========================================================================
    # PERSONAL REFLECTION
    # =========================================================================
    origin_story: str | None = None
    evolution_notes: str | None = None

    # =========================================================================
    # PRINCIPLE STATUS
    # =========================================================================
    is_active: bool = True
    adopted_date: date | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_principle(cls, user_uid: str, title: str, **kwargs: Any) -> PrincipleDTO:
        """Create a PrincipleDTO with generated UID and correct defaults."""
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("principle", title)
            else:
                uid = UIDGenerator.generate_random_uid("principle")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            ku_type=EntityType.PRINCIPLE,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including principle-specific fields."""
        from core.models.dto_helpers import convert_dates_to_iso
        from core.ports import get_enum_value

        data = super().to_dict()

        data.update(
            {
                # Statement
                "statement": self.statement,
                # Classification
                "principle_category": get_enum_value(self.principle_category),
                "principle_source": get_enum_value(self.principle_source),
                "strength": get_enum_value(self.strength),
                # Philosophical
                "tradition": self.tradition,
                "original_source": self.original_source,
                "personal_interpretation": self.personal_interpretation,
                # Expressions
                "expressions": list(self.expressions) if self.expressions else [],
                "key_behaviors": list(self.key_behaviors) if self.key_behaviors else [],
                # Alignment
                "current_alignment": get_enum_value(self.current_alignment),
                "alignment_history": list(self.alignment_history) if self.alignment_history else [],
                "last_review_date": self.last_review_date,
                # Conflicts
                "potential_conflicts": list(self.potential_conflicts)
                if self.potential_conflicts
                else [],
                "conflicting_principles": list(self.conflicting_principles)
                if self.conflicting_principles
                else [],
                "resolution_strategies": list(self.resolution_strategies)
                if self.resolution_strategies
                else [],
                # Reflection
                "origin_story": self.origin_story,
                "evolution_notes": self.evolution_notes,
                # Status
                "is_active": self.is_active,
                "adopted_date": self.adopted_date,
            }
        )

        convert_dates_to_iso(data, ["last_review_date", "adopted_date"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrincipleDTO:
        """Create PrincipleDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
                "current_alignment": AlignmentLevel,
            },
            date_fields=["last_review_date", "adopted_date"],
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "expressions",
                "key_behaviors",
                "alignment_history",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
            ],
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
                # Principle-specific fields
                "statement",
                "principle_category",
                "principle_source",
                "strength",
                "tradition",
                "original_source",
                "personal_interpretation",
                "expressions",
                "key_behaviors",
                "current_alignment",
                "alignment_history",
                "last_review_date",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
                "origin_story",
                "evolution_notes",
                "is_active",
                "adopted_date",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "principle_category": PrincipleCategory,
                "principle_source": PrincipleSource,
                "strength": PrincipleStrength,
                "current_alignment": AlignmentLevel,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, PrincipleDTO):
            return False
        return self.uid == other.uid
