"""
AiFeedback - AI Feedback Domain Model
======================================

Frozen dataclass for AI-generated (or human-written) feedback about a user's
activity patterns over a time period (EntityType.AI_FEEDBACK).

Distinct from FEEDBACK_REPORT — which responds to a specific submitted artifact.
AiFeedback responds to a user's aggregate behavior over a time window.

ProcessorType discriminates the source:
    ProcessorType.AUTOMATIC — system-generated on a schedule (default)
    ProcessorType.LLM       — AI reasoned over activity graph data (on-demand)
    ProcessorType.HUMAN     — admin reviewed activity domains manually

Inherits from UserOwnedEntity directly (NOT Submission — no file fields apply).

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.feedback.ai_feedback_dto import AiFeedbackDTO

from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class AiFeedback(UserOwnedEntity):
    """
    Immutable domain model for AI Feedback entities (EntityType.AI_FEEDBACK).

    Represents feedback about a user's aggregate activity patterns over a time period.
    Distinct from FEEDBACK_REPORT (which responds to a specific submission artifact).

    Fields:
        processor_type: Source of the feedback (AUTOMATIC/LLM/HUMAN)
        subject_uid: User whose activity this feedback is about
        time_period: Sliding window (7d, 14d, 30d, 90d)
        period_start: Exact start of the analysis window
        period_end: Exact end of the analysis window
        domains_covered: Activity domains included in analysis
        depth: Analysis depth (summary, standard, detailed)
        processed_content: Generated feedback text (LLM output or human-written)
        processing_error: Error message if generation failed
        insights_referenced: UIDs of active insights used in generation
    """

    def __post_init__(self) -> None:
        """Force ku_type=AI_FEEDBACK, then delegate to UserOwnedEntity."""
        if self.ku_type != EntityType.AI_FEEDBACK:
            object.__setattr__(self, "ku_type", EntityType.AI_FEEDBACK)
        if self.status is None:
            object.__setattr__(self, "status", EntityStatus.COMPLETED)
        super().__post_init__()

    # =========================================================================
    # PROCESSOR
    # =========================================================================
    processor_type: ProcessorType | None = None

    # =========================================================================
    # SUBJECT
    # =========================================================================
    subject_uid: str | None = None          # user_uid this feedback is about

    # =========================================================================
    # TIME WINDOW
    # =========================================================================
    time_period: str | None = None          # "7d" | "14d" | "30d" | "90d"
    period_start: datetime | None = None
    period_end: datetime | None = None

    # =========================================================================
    # ANALYSIS CONFIGURATION
    # =========================================================================
    domains_covered: tuple[str, ...] = field(default_factory=tuple)  # activity domain names
    depth: str | None = None                # summary | standard | detailed

    # =========================================================================
    # CONTENT
    # =========================================================================
    processed_content: str | None = None    # LLM output or human-written feedback
    processing_error: str | None = None

    # =========================================================================
    # INSIGHT REFERENCES
    # =========================================================================
    insights_referenced: tuple[str, ...] = field(default_factory=tuple)  # insight UIDs

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | AiFeedbackDTO") -> "AiFeedback":  # type: ignore[override]
        """Create AiFeedback from an EntityDTO or AiFeedbackDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "AiFeedbackDTO":  # type: ignore[override]
        """Convert AiFeedback to domain-specific AiFeedbackDTO."""
        import dataclasses
        from typing import Any

        from core.models.feedback.ai_feedback_dto import AiFeedbackDTO

        dto_field_names = {f.name for f in dataclasses.fields(AiFeedbackDTO)}
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
        return AiFeedbackDTO(**kwargs)

    def __str__(self) -> str:
        return f"AiFeedback(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"AiFeedback(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"time_period={self.time_period}, processor_type={self.processor_type})"
        )
