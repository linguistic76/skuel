"""
ChoiceDTO - Choice-Specific DTO (Tier 2 - Transfer)
=====================================================

Extends UserOwnedDTO with 16 choice-specific fields matching the Choice
frozen dataclass (Tier 3): decision context, timing, lifecycle, outcome
tracking, and curriculum integration.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── ChoiceDTO(UserOwnedDTO) +16 choice-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from datetime import datetime

from core.models.enum_field_registry import enum_fields_for
from core.models.enums.activity_enums import EngagementState
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class ChoiceDTO(UserOwnedDTO):
    """
    Mutable DTO for choices (EntityType.CHOICE).

    Extends UserOwnedDTO with 16 choice-specific fields:
    - Decision (8): choice_type, options, selected_option_uid, decision_context, decision_rationale, decision_criteria, constraints, stakeholders
    - Timing (2): decision_deadline, decided_at
    - Lifecycle (1): completed_at
    - Outcome (3): satisfaction_score, actual_outcome, lessons_learned
    - Curriculum (2): inspiration_type, expands_possibilities
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.CHOICE, kw_only=True)

    # =========================================================================
    # DECISION
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option_uid: str | None = None
    decision_context: str | None = None
    decision_rationale: str | None = None
    decision_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)

    # =========================================================================
    # DECISION TIMING
    # =========================================================================
    decision_deadline: datetime | None = None
    decided_at: datetime | None = None

    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    # When the choice transitioned into COMPLETED; cleared on reopen.
    completed_at: datetime | None = None

    # =========================================================================
    # OUTCOME
    # =========================================================================
    satisfaction_score: int | None = None
    actual_outcome: str | None = None
    lessons_learned: list[str] = field(default_factory=list)

    # =========================================================================
    # CURRICULUM INTEGRATION
    # =========================================================================
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_path_step_uid: str | None = None

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Choice)-[:SPAWNED_FROM]->(ChoiceTemplate).
    engagement_state: EngagementState | None = None

    # =========================================================================
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_choice(cls, user_uid: UserUID, title: str, **kwargs: Any) -> ChoiceDTO:
        """Create a ChoiceDTO with generated UID and correct defaults."""
        from core.utils.uid_generator import UIDGenerator

        uid = kwargs.pop("uid", None)
        if not uid:
            if title:
                uid = UIDGenerator.generate_uid("choice", title)
            else:
                uid = UIDGenerator.generate_random_uid("choice")

        kwargs.setdefault("status", EntityStatus.DRAFT)
        kwargs.setdefault("visibility", Visibility.PRIVATE)

        return cls(
            uid=uid,
            title=title,
            entity_type=EntityType.CHOICE,
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
            enum_fields=["entity_type", "status", "domain", "visibility", "choice_type"],
            datetime_fields=[
                "created_at",
                "updated_at",
                "decision_deadline",
                "decided_at",
                "completed_at",
            ],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChoiceDTO:
        """Create ChoiceDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "choice_type",
                "engagement_state",
            ),
            datetime_fields=[
                "created_at",
                "updated_at",
                "decision_deadline",
                "decided_at",
                "completed_at",
            ],
            list_fields=[
                "tags",
                "options",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "lessons_learned",
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
                # Choice-specific fields
                "choice_type",
                "options",
                "selected_option_uid",
                "decision_context",
                "decision_rationale",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "decision_deadline",
                "decided_at",
                "completed_at",
                "satisfaction_score",
                "actual_outcome",
                "lessons_learned",
                "inspiration_type",
                "expands_possibilities",
                "source_path_step_uid",
                "engagement_state",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "choice_type",
                "engagement_state",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ChoiceDTO):
            return False
        return self.uid == other.uid
