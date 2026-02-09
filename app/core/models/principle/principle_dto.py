"""
Principle DTO (Tier 2 - Transfer)
==================================

Mutable data transfer object for Principle operations.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, ClassVar

from core.models.activity_dto_mixin import ActivityDTOMixin
from core.models.enums import Priority

from ..principle.principle import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)


@dataclass
class PrincipleDTO(ActivityDTOMixin):
    """Mutable data transfer object for Principle."""

    # Class variable for UID generation (ActivityDTOMixin)
    _uid_prefix: ClassVar[str] = "principle"

    # Identity
    uid: str
    user_uid: str  # REQUIRED - principle ownership
    name: str
    statement: str
    description: str | None = None

    # Classification
    category: PrincipleCategory = PrincipleCategory.PERSONAL
    source: PrincipleSource = PrincipleSource.PERSONAL
    strength: PrincipleStrength = PrincipleStrength.MODERATE

    # Philosophical Context
    tradition: str | None = None
    original_source: str | None = None
    personal_interpretation: str | None = None

    # Expressions & Applications (list of dicts)
    expressions: list[dict] = field(default_factory=list)
    key_behaviors: list[str] = field(default_factory=list)
    decision_criteria: list[str] = field(default_factory=list)

    # Alignment Tracking
    current_alignment: AlignmentLevel = AlignmentLevel.UNKNOWN
    alignment_history: list[dict] = field(default_factory=list)
    last_review_date: date | None = None

    # Conflicts
    potential_conflicts: list[str] = field(default_factory=list)
    resolution_strategies: list[str] = field(default_factory=list)

    # Personal Reflection
    why_important: str | None = None
    origin_story: str | None = None
    evolution_notes: str | None = None

    # Status
    is_active: bool = True
    priority: Priority = Priority.MEDIUM

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    adopted_date: date | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Rich context storage (graph neighborhoods, etc.)

    @classmethod
    def create(
        cls,
        user_uid: str,
        name: str,
        statement: str,
        category: PrincipleCategory = PrincipleCategory.PERSONAL,
        strength: PrincipleStrength = PrincipleStrength.MODERATE,
        **kwargs: Any,
    ) -> "PrincipleDTO":
        """Factory method to create new PrincipleDTO."""
        return cls._create_activity_dto(
            user_uid=user_uid,
            name=name,
            statement=statement,
            category=category,
            strength=strength,
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrincipleDTO":
        """Create DTO from dictionary."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "category": PrincipleCategory,
                "source": PrincipleSource,
                "strength": PrincipleStrength,
                "current_alignment": AlignmentLevel,
                "priority": Priority,
            },
            date_fields=["last_review_date", "adopted_date"],
            datetime_fields=["created_at", "updated_at"],
            list_fields=[
                "expressions",
                "key_behaviors",
                "decision_criteria",
                "alignment_history",
                "potential_conflicts",
                "resolution_strategies",
                "tags",
            ],
            dict_fields=["metadata"],
        )

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates, skip_none=False)

    def add_expression(self, context: str, behavior: str, example: str | None = None) -> None:
        """Add a new expression of this principle."""
        self.expressions.append({"context": context, "behavior": behavior, "example": example})
        self.updated_at = datetime.now()

    def assess_alignment(
        self, level: AlignmentLevel, evidence: str, reflection: str | None = None
    ) -> None:
        """Record an alignment assessment."""
        self.alignment_history.append(
            {
                "assessed_date": date.today(),
                "alignment_level": level,
                "evidence": evidence,
                "reflection": reflection,
            }
        )
        self.current_alignment = level
        self.last_review_date = date.today()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for storage."""
        from core.models.dto_helpers import dto_to_dict
        from core.services.protocols import get_enum_value

        data = dto_to_dict(
            self,
            enum_fields=["category", "source", "strength", "current_alignment", "priority"],
            date_fields=["last_review_date", "adopted_date"],
            datetime_fields=["created_at", "updated_at"],
            nested_date_fields={"alignment_history": ["assessed_date"]},
        )

        # Convert nested enums in alignment_history (unique to PrincipleDTO)
        for assessment in data.get("alignment_history", []):
            if assessment.get("alignment_level"):
                assessment["alignment_level"] = get_enum_value(assessment["alignment_level"])

        return data
