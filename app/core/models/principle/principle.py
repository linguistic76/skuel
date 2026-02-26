"""
Principle - Principle Domain Model
======================================

Frozen dataclass for principle entities (EntityType.PRINCIPLE).

Inherits common fields from UserOwnedEntity. Adds 19 principle-specific fields:
- Statement (1): statement
- Classification (3): principle_category, principle_source, strength
- Philosophical context (3): tradition, original_source, personal_interpretation
- Expressions & applications (2): expressions, key_behaviors
- Alignment tracking (3): current_alignment, alignment_history, last_review_date
- Conflicts & tensions (3): potential_conflicts, conflicting_principles, resolution_strategies
- Personal reflection (2): origin_story, evolution_notes
- Principle status (2): is_active, adopted_date

Principle-specific methods: is_well_aligned, has_alignment_issues, has_concrete_behaviors,
is_actionable, assess_alignment, get_summary, explain_existence, category, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.principle.principle_dto import PrincipleDTO

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle_types import AlignmentAssessment, PrincipleExpression
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class Principle(UserOwnedEntity):
    """
    Immutable domain model for principles (EntityType.PRINCIPLE).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 19 principle-specific fields for classification, philosophical context,
    expressions, alignment tracking, conflicts, and personal reflection.
    """

    def __post_init__(self) -> None:
        """Force ku_type=PRINCIPLE, then delegate to Entity for timestamps/status defaults."""
        if self.ku_type != EntityType.PRINCIPLE:
            object.__setattr__(self, "ku_type", EntityType.PRINCIPLE)
        super().__post_init__()

    # =========================================================================
    # STATEMENT
    # =========================================================================
    statement: str | None = None  # Core principle statement

    # =========================================================================
    # CLASSIFICATION
    # =========================================================================
    principle_category: PrincipleCategory | None = None
    principle_source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None

    # =========================================================================
    # PHILOSOPHICAL CONTEXT
    # =========================================================================
    tradition: str | None = None  # Philosophical/religious tradition
    original_source: str | None = None  # Source text/author
    personal_interpretation: str | None = None

    # =========================================================================
    # EXPRESSIONS & APPLICATIONS
    # =========================================================================
    expressions: tuple[PrincipleExpression, ...] = ()
    key_behaviors: tuple[str, ...] = ()

    # =========================================================================
    # ALIGNMENT TRACKING
    # =========================================================================
    current_alignment: AlignmentLevel | None = None
    alignment_history: tuple[AlignmentAssessment, ...] = ()
    last_review_date: date | None = None  # type: ignore[assignment]

    # =========================================================================
    # CONFLICTS & TENSIONS
    # =========================================================================
    potential_conflicts: tuple[str, ...] = ()
    conflicting_principles: tuple[str, ...] = ()
    resolution_strategies: tuple[str, ...] = ()

    # =========================================================================
    # PERSONAL REFLECTION
    # =========================================================================
    origin_story: str | None = None
    evolution_notes: str | None = None

    # =========================================================================
    # PRINCIPLE STATUS
    # =========================================================================
    is_active: bool = True
    adopted_date: date | None = None  # type: ignore[assignment]

    # =========================================================================
    # PRINCIPLE-SPECIFIC METHODS
    # =========================================================================

    def is_well_aligned(self) -> bool:
        """Check if principle is well-aligned."""
        return self.current_alignment in (AlignmentLevel.ALIGNED, AlignmentLevel.FLOURISHING)

    def has_alignment_issues(self) -> bool:
        """Check if principle has alignment issues."""
        return self.current_alignment in (AlignmentLevel.DRIFTING, AlignmentLevel.MISALIGNED)

    def has_concrete_behaviors(self) -> bool:
        """Check if principle has concrete key behaviors defined."""
        return len(self.key_behaviors) > 0

    def is_actionable(self) -> bool:
        """Check if principle is actionable (has behaviors and expressions)."""
        return self.has_concrete_behaviors() or len(self.expressions) > 0

    def assess_alignment(self) -> dict[str, Any]:
        """Assess principle alignment status."""
        return {
            "level": self.current_alignment.value if self.current_alignment else "unknown",
            "is_well_aligned": self.is_well_aligned(),
            "has_issues": self.has_alignment_issues(),
            "behaviors_defined": len(self.key_behaviors),
            "expressions_count": len(self.expressions),
        }

    # =========================================================================
    # OVERRIDES
    # =========================================================================

    def needs_review(self) -> bool:
        """Principle needs review based on alignment drift or time-based cadence."""
        # Dormant principles don't need review
        if not self.is_active or self.status in (EntityStatus.ARCHIVED, EntityStatus.PAUSED):
            return False

        # Alignment issues always trigger review
        if self.has_alignment_issues():
            return True

        # Unassessed alignment triggers review (after grace period)
        if self.current_alignment is None or self.current_alignment == AlignmentLevel.UNKNOWN:
            return self._past_grace_period()

        # Time-based: check review cadence
        if self.last_review_date is None:
            return self._past_grace_period()

        days_since = (date.today() - self.last_review_date).days
        return days_since >= self._review_cadence_days()

    def _review_cadence_days(self) -> int:
        """Review interval based on strength level."""
        cadence = {
            PrincipleStrength.EXPLORING: 14,
            PrincipleStrength.DEVELOPING: 21,
            PrincipleStrength.MODERATE: 30,
            PrincipleStrength.STRONG: 45,
            PrincipleStrength.CORE: 60,
        }
        return cadence.get(self.strength, 30)

    def _past_grace_period(self) -> bool:
        """True if principle is older than 7 days (past new-principle grace period)."""
        reference = self.adopted_date or (self.created_at.date() if self.created_at else None)
        if reference is None:
            return True
        return (date.today() - reference).days > 7

    def days_until_review_needed(self) -> int | None:
        """Days until next review, 0 if overdue, None if not applicable."""
        if not self.is_active or self.status in (EntityStatus.ARCHIVED, EntityStatus.PAUSED):
            return None

        if self.needs_review():
            return 0

        if self.last_review_date is None:
            return None

        remaining = self._review_cadence_days() - (date.today() - self.last_review_date).days
        return max(0, remaining)

    @property
    def category(self) -> str | None:
        """Principle category -- uses principle_category, falls back to domain."""
        if self.principle_category:
            return self.principle_category.value
        return self.domain.value if self.domain else None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the principle."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this principle exists."""
        return (
            self.personal_interpretation
            or self.description
            or self.summary
            or f"principle: {self.title}"
        )

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | PrincipleDTO") -> "Principle":
        """Create Principle from an EntityDTO or PrincipleDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "PrincipleDTO":  # type: ignore[override]
        """Convert Principle to domain-specific PrincipleDTO."""
        import dataclasses

        from core.models.principle.principle_dto import PrincipleDTO

        dto_field_names = {f.name for f in dataclasses.fields(PrincipleDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return PrincipleDTO(**kwargs)

    def __str__(self) -> str:
        return (
            f"Principle(uid={self.uid}, title='{self.title}', category={self.principle_category})"
        )

    def __repr__(self) -> str:
        return (
            f"Principle(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, principle_category={self.principle_category}, "
            f"strength={self.strength}, user_uid={self.user_uid})"
        )
