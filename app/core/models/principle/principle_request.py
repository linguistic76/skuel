"""
Principle Request Models
=========================

Pydantic models for the Principle Activity Domain API boundaries.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from core.models.enums import Priority
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.models.request_base import CreateRequestBase, UpdateRequestBase
from core.models.sentinels import UNSET, Unset

# =============================================================================
# NESTED REQUEST MODELS (used by create requests)
# =============================================================================


class PrincipleExpressionRequest(BaseModel):
    """Request model for creating an expression within a Principle entity."""

    context: str = Field(min_length=1, max_length=500, description="Life situation")
    behavior: str = Field(min_length=1, max_length=500, description="Expected behavior")
    example: str | None = Field(default=None, max_length=500, description="Concrete example")


# =============================================================================
# CREATE / UPDATE / FILTER REQUESTS
# =============================================================================


class PrincipleCreateRequest(CreateRequestBase):
    """Create a Principle entity (knowledge about what you believe).

    Field names mirror the ``Principle`` domain model 1:1 so the form layer
    auto-prefills via ``FormGenerator.from_instance``. The one exception is
    ``decision_criteria``, which has no ``Principle`` column and is dropped by
    the generic converter.
    """

    title: str = Field(min_length=1, max_length=100, description="Principle title")
    statement: str = Field(min_length=1, max_length=500, description="Core statement")
    description: str | None = Field(default=None, max_length=1000, description="Full description")

    # Classification
    principle_category: PrincipleCategory = Field(
        default=PrincipleCategory.PERSONAL, description="Category"
    )
    principle_source: PrincipleSource = Field(
        default=PrincipleSource.PERSONAL, description="Source"
    )
    strength: PrincipleStrength = Field(default=PrincipleStrength.MODERATE, description="Strength")

    # Origin
    tradition: str | None = Field(
        default=None, max_length=100, description="Tradition/school of thought"
    )
    original_source: str | None = Field(
        default=None, max_length=200, description="Original source text"
    )
    personal_interpretation: str | None = Field(
        default=None, max_length=1000, description="Personal interpretation"
    )
    why_important: str | None = Field(
        default=None, max_length=1000, description="Why this principle matters"
    )
    origin_story: str | None = Field(
        default=None, max_length=2000, description="How you came to this principle"
    )

    # Behavioral expression
    key_behaviors: list[str] = Field(
        default_factory=list, max_length=10, description="Key behaviors"
    )
    decision_criteria: list[str] = Field(
        default_factory=list, max_length=10, description="Decision criteria"
    )
    expressions: list[PrincipleExpressionRequest] = Field(
        default_factory=list, description="Context expressions"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Principle priority")
    tags: list[str] = Field(default_factory=list, max_length=20, description="Tags")


class PrincipleUpdateRequest(UpdateRequestBase):
    """Update a Principle entity.

    Field names mirror the ``Principle`` domain model 1:1 (see PrincipleCreateRequest).
    """

    title: str | None = Field(
        default=None, min_length=1, max_length=100, description="Principle title"
    )
    statement: str | None = Field(
        default=None, min_length=1, max_length=500, description="Core statement"
    )
    description: str | None = Field(default=None, max_length=1000, description="Full description")
    principle_category: PrincipleCategory | None = Field(default=None, description="Category")
    principle_source: PrincipleSource | None = Field(default=None, description="Source")
    strength: PrincipleStrength | None = Field(default=None, description="Strength")
    tradition: str | None = Field(
        default=None, max_length=100, description="Tradition/school of thought"
    )
    personal_interpretation: str | None = Field(
        default=None, max_length=1000, description="Personal interpretation"
    )
    why_important: str | None = Field(
        default=None, max_length=1000, description="Why this principle matters"
    )
    key_behaviors: list[str] | None = Field(default=None, description="Key behaviors")
    decision_criteria: list[str] | None = Field(default=None, description="Decision criteria")
    priority: Priority | None = Field(default=None, description="Principle priority")
    tags: list[str] | None = Field(default=None, description="Tags")

    def to_intent(self) -> PrincipleUpdateIntent:
        """Build the typed ``PrincipleUpdateIntent`` (ADR-066) from explicitly-set fields.

        Only fields the caller actually provided (``model_fields_set``) become non-``UNSET``,
        so the intent carries a true partial patch: an absent field is left untouched, a
        field explicitly set to ``None`` is an explicit clear. Enum fields
        (principle_category, principle_source, strength, priority) are lowered to their
        string value to match the persistence boundary.

        One request field is deliberately **not** carried: ``decision_criteria`` is absent
        from ``Principle`` / ``PrincipleDTO``, so writing it would be a junk node property.
        """
        set_fields = self.model_fields_set

        def when_set[T](name: str, value: T) -> T | Unset:
            """Carry ``value`` only if the caller set this field; else ``UNSET``.

            Generic so the intent fields stay fully typed (no ``Any``): the return is
            ``<declared field type> | Unset``, exactly what each intent field expects.
            """
            return value if name in set_fields else UNSET

        return PrincipleUpdateIntent(
            title=when_set("title", self.title),
            statement=when_set("statement", self.statement),
            description=when_set("description", self.description),
            principle_category=when_set(
                "principle_category",
                self.principle_category.value if self.principle_category is not None else None,
            ),
            principle_source=when_set(
                "principle_source",
                self.principle_source.value if self.principle_source is not None else None,
            ),
            strength=when_set(
                "strength", self.strength.value if self.strength is not None else None
            ),
            tradition=when_set("tradition", self.tradition),
            personal_interpretation=when_set(
                "personal_interpretation", self.personal_interpretation
            ),
            why_important=when_set("why_important", self.why_important),
            key_behaviors=when_set("key_behaviors", self.key_behaviors),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            tags=when_set("tags", self.tags),
        )


class AlignmentAssessmentRequest(BaseModel):
    """Request to assess alignment with a principle."""

    alignment_level: AlignmentLevel = Field(...)
    evidence: str = Field(..., min_length=1, max_length=1000)
    reflection: str | None = Field(default=None, max_length=1000)
    assessed_date: date | None = Field(default_factory=date.today)


class PrincipleLinkRequest(BaseModel):
    """Request to link a principle to goals/habits/knowledge."""

    link_type: str = Field(..., pattern="^(goal|habit|knowledge|principle)$")
    uid: str = Field(..., min_length=1)
    bidirectional: bool = Field(default=False, description="Create reverse link")


class PrincipleReflectionRequest(BaseModel):
    """Request to record a principle reflection."""

    principle_uid: str = Field(..., min_length=1)
    alignment_level: AlignmentLevel = Field(..., description="How well you lived this principle")
    evidence: str = Field(..., min_length=1, max_length=1000, description="Supporting evidence")
    trigger_type: str | None = Field(
        default=None,
        pattern="^(goal|habit|event|choice|manual)$",
        description="What prompted this reflection",
    )
    trigger_uid: str | None = Field(default=None, description="UID of triggering entity")
    conflicting_principle_uid: str | None = Field(
        default=None, description="Principle in tension with this one"
    )
    reflection_quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Self-assessed reflection quality"
    )


class PrincipleBatchImpactRequest(BaseModel):
    """Request to batch-analyze principle adoption."""

    principle_uids: list[str] = Field(..., min_length=1, max_length=50)


class PrincipleFilterRequest(BaseModel):
    """Request for filtering principles."""

    category: PrincipleCategory | None = None
    source: PrincipleSource | None = None
    strength: PrincipleStrength | None = None
    current_alignment: AlignmentLevel | None = None

    is_active: bool | None = None
    is_core: bool | None = None
    supports_learning: bool | None = None
    has_conflicts: bool | None = None

    priority: Priority | None = None
    tags: list[str] | None = None
    needs_review: bool | None = None
    well_aligned: bool | None = None


# =============================================================================
# RESULT TYPES
# =============================================================================


@dataclass(frozen=True)
class PrincipleAlignmentAssessmentResult:
    """
    Dual-track principle alignment result.

    Captures BOTH user self-assessment AND system-calculated alignment,
    enabling gap analysis between perception and measured reality.
    """

    principle_uid: str

    # USER-DECLARED (stored in alignment_history)
    user_assessment: Any  # AlignmentAssessment

    # SYSTEM-CALCULATED (computed from goals/habits/choices)
    system_alignment: AlignmentLevel
    system_score: float  # 0.0-1.0 numeric score
    system_evidence: tuple[str, ...]

    # GAP ANALYSIS
    perception_gap: float  # Absolute difference between user vs system (0.0-1.0)
    gap_direction: str  # "user_higher" | "system_higher" | "aligned"

    # INSIGHTS
    insights: tuple[str, ...]
    recommendations: tuple[str, ...]

    def has_perception_gap(self) -> bool:
        """Check if there's a meaningful gap between perception and reality."""
        return self.perception_gap >= 0.15

    def is_self_aware(self) -> bool:
        """Check if user's self-perception matches system measurement."""
        return self.gap_direction == "aligned"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "principle_uid": self.principle_uid,
            "user_assessment": {
                "assessed_date": self.user_assessment.assessed_date.isoformat(),
                "alignment_level": self.user_assessment.alignment_level.value,
                "evidence": self.user_assessment.evidence,
                "reflection": self.user_assessment.reflection,
            },
            "system_alignment": self.system_alignment.value,
            "system_score": self.system_score,
            "system_evidence": list(self.system_evidence),
            "perception_gap": self.perception_gap,
            "gap_direction": self.gap_direction,
            "insights": list(self.insights),
            "recommendations": list(self.recommendations),
            "has_perception_gap": self.has_perception_gap(),
            "is_self_aware": self.is_self_aware(),
        }
