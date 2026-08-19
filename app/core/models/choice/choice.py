"""
Choice - Choice Domain Model
================================

Frozen dataclass for choice entities (EntityType.CHOICE).

Inherits common fields from UserOwnedEntity. Adds 15 choice-specific fields:
- Decision (8): choice_type, options, selected_option_uid, decision_context,
  decision_rationale, decision_criteria, constraints, stakeholders
- Decision Timing (2): decision_deadline, decided_at
- Outcome (3): satisfaction_score, actual_outcome, lessons_learned
- Choice-Curriculum Integration (2): inspiration_type, expands_possibilities

Choice-specific methods: has_high_stakes, calculate_decision_complexity,
get_decision_quality_score, get_summary, explain_existence, category, from_dto.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.choice.choice_dto import ChoiceDTO
    from core.models.entity_dto import EntityDTO

from core.models.choice.choice_option import ChoiceOption
from core.models.enums.activity_enums import EngagementState
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityType
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class Choice(UserOwnedEntity):
    """
    Immutable domain model for choices (EntityType.CHOICE).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 15 choice-specific fields for decision context, timing, outcome
    tracking, and curriculum integration.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.CHOICE, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=CHOICE, then delegate to Entity for timestamps/status defaults."""
        if self.entity_type != EntityType.CHOICE:
            raise ValueError(
                f"Choice constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        super().__post_init__()

    # =========================================================================
    # DECISION
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: tuple[ChoiceOption, ...] = ()
    selected_option_uid: str | None = None
    # The circumstance the decision is made in — what is going on that forces a
    # choice. Distinct from ``decision_rationale``, which is the reasoning that
    # justifies the option finally selected: context is authored up front and
    # survives whichever way the choice goes, rationale is written at decision time.
    decision_context: str | None = None
    decision_rationale: str | None = None
    decision_criteria: tuple[str, ...] = ()  # Shared concept with Principle
    constraints: tuple[str, ...] = ()
    stakeholders: tuple[str, ...] = ()

    # =========================================================================
    # DECISION TIMING
    # =========================================================================
    decision_deadline: datetime | None = None
    decided_at: datetime | None = None

    # =========================================================================
    # OUTCOME
    # =========================================================================
    satisfaction_score: int | None = None  # 1-5 scale
    actual_outcome: str | None = None
    lessons_learned: tuple[str, ...] = ()

    # =========================================================================
    # CHOICE-CURRICULUM INTEGRATION
    # =========================================================================
    inspiration_type: str | None = None
    expands_possibilities: bool = False

    # =========================================================================
    # CROSS-DOMAIN LINKS
    # =========================================================================
    source_path_step_uid: str | None = None  # CHOICE -> PS

    # =========================================================================
    # PS+ACTIVITY LIFECYCLE
    # =========================================================================
    # Back-reference is (Choice)-[:SPAWNED_FROM]->(ChoiceTemplate).
    engagement_state: EngagementState | None = None  # None = standalone instance

    # =========================================================================
    # CHOICE-SPECIFIC METHODS
    # =========================================================================

    def is_deadline_past(self) -> bool:
        """Check if decision deadline has passed."""
        if not self.decision_deadline:
            return False
        return self.decision_deadline.date() < date.today()

    def has_high_stakes(self) -> bool:
        """Check if choice has high stakes."""
        return bool(self.stakeholders) or bool(self.constraints)

    def calculate_decision_complexity(self) -> float:
        """Calculate decision complexity (0.0-1.0)."""
        score = 0.0
        if self.options:
            score += min(0.3, len(self.options) * 0.1)
        if self.decision_criteria:
            score += min(0.3, len(self.decision_criteria) * 0.1)
        if self.stakeholders:
            score += min(0.2, len(self.stakeholders) * 0.1)
        if self.constraints:
            score += min(0.2, len(self.constraints) * 0.1)
        return min(1.0, score)

    def get_decision_quality_score(self) -> float:
        """Get quality score for a decision."""
        if not self.decided_at:
            return 0.0
        score = 0.3  # Base for having decided
        if self.decision_rationale:
            score += 0.3
        if self.satisfaction_score:
            score += 0.2 * (self.satisfaction_score / 5.0)
        if self.actual_outcome:
            score += 0.2
        return min(1.0, score)

    @property
    def category(self) -> str | None:
        """Choice category -- uses choice_type, falls back to domain."""
        if self.choice_type:
            return self.choice_type.value
        return self.domain.value if self.domain else None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the choice."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this choice exists."""
        return (
            self.decision_rationale or self.description or self.summary or f"choice: {self.title}"
        )

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | ChoiceDTO") -> "Choice":
        """Create Choice from an EntityDTO or ChoiceDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ChoiceDTO":
        """Convert Choice to domain-specific ChoiceDTO."""

        from core.models.choice.choice_dto import ChoiceDTO
        from core.models.dto_helpers import domain_to_dto

        return domain_to_dto(self, ChoiceDTO)

    def __str__(self) -> str:
        return f"Choice(uid={self.uid}, title='{self.title}', type={self.choice_type})"

    def __repr__(self) -> str:
        return (
            f"Choice(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, choice_type={self.choice_type}, "
            f"decided_at={self.decided_at}, user_uid={self.user_uid})"
        )
