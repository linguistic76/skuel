"""
ChoiceDTO - Choice-Specific DTO (Tier 2 - Transfer)
=====================================================

Extends UserOwnedDTO with 14 choice-specific fields matching the Choice
frozen dataclass (Tier 3): decision context, timing, outcome tracking,
and curriculum integration.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── ChoiceDTO(UserOwnedDTO) +14 choice-specific fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import ChoiceType, EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class ChoiceDTO(UserOwnedDTO):
    """
    Mutable DTO for choices (EntityType.CHOICE).

    Extends UserOwnedDTO with 14 choice-specific fields:
    - Decision (7): choice_type, options, selected_option_uid, decision_rationale, decision_criteria, constraints, stakeholders
    - Timing (2): decision_deadline, decided_at
    - Outcome (3): satisfaction_score, actual_outcome, lessons_learned
    - Curriculum (2): inspiration_type, expands_possibilities
    """

    # =========================================================================
    # DECISION
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option_uid: str | None = None
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
    # FACTORY METHOD
    # =========================================================================

    @classmethod
    def create_choice(cls, user_uid: str, title: str, **kwargs: Any) -> ChoiceDTO:
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
            ku_type=EntityType.CHOICE,
            user_uid=user_uid,
            **kwargs,
        )

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including choice-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso
        from core.ports import get_enum_value

        data = super().to_dict()

        data.update(
            {
                # Decision
                "choice_type": get_enum_value(self.choice_type),
                "options": list(self.options) if self.options else [],
                "selected_option_uid": self.selected_option_uid,
                "decision_rationale": self.decision_rationale,
                "decision_criteria": list(self.decision_criteria) if self.decision_criteria else [],
                "constraints": list(self.constraints) if self.constraints else [],
                "stakeholders": list(self.stakeholders) if self.stakeholders else [],
                # Timing
                "decision_deadline": self.decision_deadline,
                "decided_at": self.decided_at,
                # Outcome
                "satisfaction_score": self.satisfaction_score,
                "actual_outcome": self.actual_outcome,
                "lessons_learned": list(self.lessons_learned) if self.lessons_learned else [],
                # Curriculum
                "inspiration_type": self.inspiration_type,
                "expands_possibilities": self.expands_possibilities,
            }
        )

        convert_datetimes_to_iso(data, ["decision_deadline", "decided_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChoiceDTO:
        """Create ChoiceDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "choice_type": ChoiceType,
            },
            datetime_fields=[
                "created_at",
                "updated_at",
                "decision_deadline",
                "decided_at",
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
                # Choice-specific fields
                "choice_type",
                "options",
                "selected_option_uid",
                "decision_rationale",
                "decision_criteria",
                "constraints",
                "stakeholders",
                "decision_deadline",
                "decided_at",
                "satisfaction_score",
                "actual_outcome",
                "lessons_learned",
                "inspiration_type",
                "expands_possibilities",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "choice_type": ChoiceType,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ChoiceDTO):
            return False
        return self.uid == other.uid
