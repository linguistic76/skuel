"""
Choice Request Models
======================

Pydantic models for the Choice Activity Domain API boundaries.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from datetime import datetime

from pydantic import BaseModel, Field

from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums import Domain, Priority
from core.models.enums.choice_enums import ChoiceType
from core.models.request_base import CreateRequestBase, UpdateRequestBase
from core.models.sentinels import UNSET, Unset

# =============================================================================
# NESTED REQUEST MODELS (used by create requests)
# =============================================================================


class ChoiceOptionRequest(BaseModel):
    """Request model for creating an option within a Choice entity."""

    title: str = Field(min_length=1, max_length=200, description="Option title")
    description: str = Field(default="", max_length=1000, description="Option description")
    feasibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: float = Field(default=0.5, ge=0.0, le=1.0)
    potential_impact: float = Field(default=0.5, ge=0.0, le=1.0)
    resource_requirement: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_duration: int | None = Field(default=None, ge=1, description="Duration in minutes")
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# =============================================================================
# CREATE / UPDATE REQUESTS
# =============================================================================


class ChoiceCreateRequest(CreateRequestBase):
    """Create a Choice entity (knowledge about decisions you make)."""

    title: str = Field(min_length=1, max_length=200, description="Choice title")
    description: str = Field(min_length=1, max_length=1000, description="Choice description")

    # Decision characteristics
    choice_type: ChoiceType = Field(default=ChoiceType.MULTIPLE, description="Choice type")
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    decision_context: str | None = Field(
        default=None,
        max_length=1000,
        description="Circumstance forcing the decision (not the rationale for the option chosen)",
    )
    decision_deadline: datetime | None = Field(default=None, description="Decision deadline")
    decision_criteria: list[str] = Field(default_factory=list, description="Criteria for deciding")
    constraints: list[str] = Field(default_factory=list, description="Constraints")
    stakeholders: list[str] = Field(default_factory=list, description="Stakeholders")

    # Options
    options: list[ChoiceOptionRequest] = Field(
        default_factory=list, description="Available options"
    )

    # Organization
    priority: Priority = Field(default=Priority.MEDIUM, description="Choice priority")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Cross-domain relationships
    informed_by_knowledge_uids: list[str] = Field(
        default_factory=list, description="KU UIDs informing this choice"
    )


class ChoiceUpdateRequest(UpdateRequestBase):
    """Update a Choice entity."""

    title: str | None = Field(
        default=None, min_length=1, max_length=200, description="Choice title"
    )
    description: str | None = Field(
        default=None, min_length=1, max_length=1000, description="Choice description"
    )
    choice_type: ChoiceType | None = Field(default=None, description="Choice type")
    domain: Domain | None = Field(default=None, description="Domain")
    decision_context: str | None = Field(
        default=None,
        max_length=1000,
        description="Circumstance forcing the decision (not the rationale for the option chosen)",
    )
    decision_deadline: datetime | None = Field(default=None, description="Decision deadline")
    decision_criteria: list[str] | None = Field(default=None, description="Criteria for deciding")
    constraints: list[str] | None = Field(default=None, description="Constraints")
    stakeholders: list[str] | None = Field(default=None, description="Stakeholders")
    completed_at: datetime | None = Field(
        default=None,
        description="When the choice was completed (explicit stamp; None clears it on reopen)",
    )
    priority: Priority | None = Field(default=None, description="Choice priority")
    tags: list[str] | None = Field(default=None, description="Tags")

    def to_intent(self) -> ChoiceUpdateIntent:
        """Build the typed ``ChoiceUpdateIntent`` (ADR-066) from explicitly-set fields.

        Only fields the caller actually provided (``model_fields_set``) become non-``UNSET``,
        so the intent carries a true partial patch: an absent field is left untouched, a
        field explicitly set to ``None`` is an explicit clear. Enum fields (choice_type,
        domain, priority) are lowered to their string value to match the persistence
        boundary.

        ``ChoiceUpdateRequest`` carries no cross-domain edge fields, so there is nothing to
        drop — the create-only ``informed_by_knowledge_uids`` edge lives on
        ``ChoiceCreateRequest``, not here.
        """
        set_fields = self.model_fields_set

        def when_set[T](name: str, value: T) -> T | Unset:
            """Carry ``value`` only if the caller set this field; else ``UNSET``.

            Generic so the intent fields stay fully typed (no ``Any``): the return is
            ``<declared field type> | Unset``, exactly what each intent field expects.
            """
            return value if name in set_fields else UNSET

        return ChoiceUpdateIntent(
            title=when_set("title", self.title),
            description=when_set("description", self.description),
            choice_type=when_set(
                "choice_type", self.choice_type.value if self.choice_type is not None else None
            ),
            domain=when_set("domain", self.domain.value if self.domain is not None else None),
            decision_context=when_set("decision_context", self.decision_context),
            decision_deadline=when_set("decision_deadline", self.decision_deadline),
            decision_criteria=when_set("decision_criteria", self.decision_criteria),
            constraints=when_set("constraints", self.constraints),
            stakeholders=when_set("stakeholders", self.stakeholders),
            completed_at=when_set("completed_at", self.completed_at),
            priority=when_set(
                "priority", self.priority.value if self.priority is not None else None
            ),
            tags=when_set("tags", self.tags),
        )


class ChoiceEvaluationRequest(BaseModel):
    """Request model for evaluating choice outcomes."""

    satisfaction_score: int = Field(..., ge=1, le=5, description="Satisfaction score (1-5)")
    actual_outcome: str = Field(
        ..., min_length=1, max_length=1000, description="Actual outcome description"
    )
    lessons_learned: list[str] = Field(default_factory=list, description="Lessons learned")


class ChoiceDecisionRequest(BaseModel):
    """Request model for making a decision on a choice."""

    selected_option_uid: str = Field(..., description="UID of selected option")
    decision_rationale: str | None = Field(
        default=None, max_length=1000, description="Rationale for decision"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence level")
    decided_at: datetime | None = Field(default=None, description="Decision timestamp")
