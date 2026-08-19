"""
PrincipleDTO - Principle-Specific DTO (Tier 2 - Transfer)
==========================================================

Extends UserOwnedDTO with 20 principle-specific fields matching the Principle
frozen dataclass (Tier 3): statement, classification, philosophy, expressions,
alignment, conflicts, reflection, and status.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── PrincipleDTO(UserOwnedDTO) +20 principle-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from datetime import date

from core.models.enum_field_registry import enum_fields_for
from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class PrincipleDTO(UserOwnedDTO):
    """
    Mutable DTO for principles (EntityType.PRINCIPLE).

    Extends UserOwnedDTO with 20 principle-specific fields:
    - Statement (1): statement
    - Classification (3): principle_category, principle_source, strength
    - Philosophical (3): tradition, original_source, personal_interpretation
    - Expressions (2): expressions, key_behaviors
    - Alignment (3): current_alignment, alignment_history, last_review_date
    - Conflicts (3): potential_conflicts, conflicting_principles, resolution_strategies
    - Reflection (3): why_important, origin_story, evolution_notes
    - Status (2): is_active, adopted_date
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.PRINCIPLE, kw_only=True)

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
    dual_track_checkins: list[dict[str, Any]] = field(default_factory=list)
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
    why_important: str | None = None
    origin_story: str | None = None
    evolution_notes: str | None = None

    # =========================================================================
    # PRINCIPLE STATUS
    # =========================================================================
    is_active: bool = True
    adopted_date: date | None = None

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_path_step_uid: str | None = None

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Principle)-[:SPAWNED_FROM]->(PrincipleTemplate).
    engagement_state: EngagementState | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_principle(cls, user_uid: UserUID, title: str, **kwargs: Any) -> PrincipleDTO:
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
            entity_type=EntityType.PRINCIPLE,
            user_uid=user_uid,
            **kwargs,
        )

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
                "domain",
                "visibility",
                "principle_category",
                "principle_source",
                "strength",
                "current_alignment",
            ],
            date_fields=["last_review_date", "adopted_date"],
            datetime_fields=["created_at", "updated_at"],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrincipleDTO:
        """Create PrincipleDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "principle_category",
                "principle_source",
                "strength",
                "current_alignment",
                "engagement_state",
            ),
            date_fields=["last_review_date", "adopted_date"],
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "tags",
                "expressions",
                "key_behaviors",
                "alignment_history",
                "dual_track_checkins",
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
                "dual_track_checkins",
                "last_review_date",
                "potential_conflicts",
                "conflicting_principles",
                "resolution_strategies",
                "why_important",
                "origin_story",
                "evolution_notes",
                "is_active",
                "adopted_date",
                "source_path_step_uid",
                "engagement_state",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "principle_category",
                "principle_source",
                "strength",
                "current_alignment",
                "engagement_state",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, PrincipleDTO):
            return False
        return self.uid == other.uid
