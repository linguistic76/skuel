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
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.principle.principle_dto import PrincipleDTO

from core.models.enums.activity_enums import EngagementState
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle_types import AlignmentAssessment, PrincipleExpression
from core.models.user_owned_entity import UserOwnedEntity

# ``why_important`` is a request-only field — Principle has no dedicated column,
# so the create/update flow appends it to ``description`` with this marker.
# Edit forms call ``split_why_important`` to reverse the merge for prefill.
# Round-trip caveat: if ``description`` was empty at write time the marker is
# omitted (preserves the original behavior of principles_core_service), so a
# write of (description=None, why_important="x") reads back as
# (description="x", why_important=None).
WHY_IMPORTANT_MARKER = "\n\nWhy this matters:\n"


def merge_why_important(description: str | None, why_important: str | None) -> str | None:
    """Append ``why_important`` to ``description`` with the canonical marker."""
    if not why_important:
        return description
    if not description:
        return why_important
    return f"{description}{WHY_IMPORTANT_MARKER}{why_important}"


def split_why_important(
    description: str | None,
) -> tuple[str | None, str | None]:
    """Inverse of ``merge_why_important``: return (prose, why_important)."""
    if not description:
        return None, None
    prose, sep, why = description.rpartition(WHY_IMPORTANT_MARKER)
    if not sep:
        return description, None
    return (prose or None), (why or None)


def _to_alignment_assessment(entry: Any) -> AlignmentAssessment:
    """Reconstruct an AlignmentAssessment from a dict produced by ``asdict()``.

    The dict form may carry ``assessed_date`` as a real ``date`` (in-memory
    round-trip) or an ISO string (after JSON serialization), and
    ``alignment_level`` as either an ``AlignmentLevel`` or its string value.
    Handle both so callers don't have to.
    """
    if isinstance(entry, AlignmentAssessment):
        return entry
    data = dict(entry)
    assessed = data.get("assessed_date")
    if isinstance(assessed, str):
        data["assessed_date"] = date.fromisoformat(assessed)
    level = data.get("alignment_level")
    if isinstance(level, str):
        data["alignment_level"] = AlignmentLevel(level)
    return AlignmentAssessment(**data)


def _to_principle_expression(entry: Any) -> PrincipleExpression:
    """Reconstruct a PrincipleExpression from an asdict()-flattened dict."""
    if isinstance(entry, PrincipleExpression):
        return entry
    return PrincipleExpression(**entry)


@dataclass(frozen=True, kw_only=True)
class Principle(UserOwnedEntity):
    """
    Immutable domain model for principles (EntityType.PRINCIPLE).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 19 principle-specific fields for classification, philosophical context,
    expressions, alignment tracking, conflicts, and personal reflection.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.PRINCIPLE, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=PRINCIPLE, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.PRINCIPLE:
            raise ValueError(
                f"Principle constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
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
    last_review_date: date | None = None

    # Dual-track perception-gap check-ins (ADR-030). Distinct from the typed
    # alignment_history above (which the older single-track assess_with_user_input
    # feature writes): this append-only tuple[dict] log holds the full dual-track
    # snapshot (self-rated vs measured + gap) the dual-track store_callback writes,
    # and is what the per-entity gap card + cross-domain aggregator read.
    # See: core/models/shared/dual_track.py.
    dual_track_checkins: tuple[dict, ...] = ()

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
    adopted_date: date | None = None

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_path_step_uid: str | None = None  # PRINCIPLE -> PS

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Principle)-[:SPAWNED_FROM]->(PrincipleTemplate).
    engagement_state: EngagementState | None = None  # None = standalone instance

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
        if self.strength is None:
            return 30
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

    @classmethod
    def _from_dto(cls, dto: "EntityDTO") -> Self:
        """Extend the generic extraction to rehydrate typed nested records.

        ``PrincipleDTO`` stores ``alignment_history`` and ``expressions`` as
        ``list[dict[str, Any]]`` because ``asdict()`` in ``dto_to_dict`` flattens
        nested dataclasses recursively during JSON serialization. The generic
        ``Entity._from_dto`` only converts the outer ``list`` to ``tuple`` and
        leaves the inner dicts untouched — so consumers that expect
        ``alignment_history[-1].alignment_level`` get an ``AttributeError``.

        Rebuild the typed ``AlignmentAssessment`` and ``PrincipleExpression``
        records here so the rest of the codebase can rely on the type
        annotations on ``Principle``.
        """
        instance = super()._from_dto(dto)
        return dataclasses.replace(
            instance,
            alignment_history=tuple(
                _to_alignment_assessment(entry) for entry in instance.alignment_history
            ),
            expressions=tuple(_to_principle_expression(entry) for entry in instance.expressions),
        )

    def to_dto(self) -> "PrincipleDTO":
        """Convert Principle to domain-specific PrincipleDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.principle.principle_dto import PrincipleDTO

        return domain_to_dto(self, PrincipleDTO)

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


def get_principle_priority(principle: Any) -> int:
    """
    Sort key: numeric priority (1-4) for ordering principles.

    Principle-domain sorting policy (Dynamic Enum Pattern): converts the
    Priority enum via to_numeric(); string priorities (Neo4j deserialization)
    are resolved through the Priority enum; anything else defaults to
    MEDIUM (2).

    Example:
        principles.sort(key=get_principle_priority, reverse=True)
    """
    from core.ports.base_protocols import HasPriority, HasToNumeric

    if isinstance(principle, HasPriority):
        if isinstance(principle.priority, HasToNumeric):
            return principle.priority.to_numeric()
        if isinstance(principle.priority, str):
            from core.models.enums import Priority

            try:
                return Priority(principle.priority).to_numeric()
            except ValueError:
                return 2
    return 2  # Default to MEDIUM priority
