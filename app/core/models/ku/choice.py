"""
Choice - Choice Domain Model
================================

Frozen dataclass for choice entities (EntityType.CHOICE).

Inherits common fields from UserOwnedEntity. Adds 14 choice-specific fields:
- Decision (7): choice_type, options, selected_option_uid, decision_rationale,
  decision_criteria, constraints, stakeholders
- Decision Timing (2): decision_deadline, decided_at
- Outcome (3): satisfaction_score, actual_outcome, lessons_learned
- Choice-Curriculum Integration (2): inspiration_type, expands_possibilities

Choice-specific methods: has_high_stakes, calculate_decision_complexity,
get_decision_quality_score, get_summary, explain_existence, category, from_dto.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 5)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.choice_dto import ChoiceDTO
    from core.models.ku.entity_dto import EntityDTO

from core.models.enums.ku_enums import ChoiceType, EntityType
from core.models.ku.ku_nested_types import ChoiceOption
from core.models.ku.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class Choice(UserOwnedEntity):
    """
    Immutable domain model for choices (EntityType.CHOICE).

    Inherits common fields from UserOwnedEntity (identity, content, status,
    learning, sharing, substance, meta, embedding).

    Adds 14 choice-specific fields for decision context, timing, outcome
    tracking, and curriculum integration.
    """

    def __post_init__(self) -> None:
        """Force ku_type=CHOICE, then delegate to Entity for timestamps/status defaults."""
        if self.ku_type != EntityType.CHOICE:
            object.__setattr__(self, "ku_type", EntityType.CHOICE)
        super().__post_init__()

    # =========================================================================
    # DECISION
    # =========================================================================
    choice_type: ChoiceType | None = None
    options: tuple[ChoiceOption, ...] = ()
    selected_option_uid: str | None = None
    decision_rationale: str | None = None
    decision_criteria: tuple[str, ...] = ()  # Shared concept with Principle (Phase 6)
    constraints: tuple[str, ...] = ()
    stakeholders: tuple[str, ...] = ()

    # =========================================================================
    # DECISION TIMING
    # =========================================================================
    decision_deadline: datetime | None = None  # type: ignore[assignment]
    decided_at: datetime | None = None  # type: ignore[assignment]

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
    # CHOICE-SPECIFIC METHODS
    # =========================================================================

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

    def to_dto(self) -> "ChoiceDTO":  # type: ignore[override]
        """Convert Choice to domain-specific ChoiceDTO."""
        import dataclasses
        from typing import Any

        from core.models.ku.choice_dto import ChoiceDTO

        dto_field_names = {f.name for f in dataclasses.fields(ChoiceDTO)}
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
        return ChoiceDTO(**kwargs)

    def __str__(self) -> str:
        return f"Choice(uid={self.uid}, title='{self.title}', type={self.choice_type})"

    def __repr__(self) -> str:
        return (
            f"Choice(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, choice_type={self.choice_type}, "
            f"decided_at={self.decided_at}, user_uid={self.user_uid})"
        )
