"""
Feedback - Feedback Report Domain Model
============================================

Frozen dataclass for teacher feedback entities (EntityType.FEEDBACK_REPORT).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Adds 2 feedback-specific fields:
- feedback: str | None — the feedback text
- feedback_generated_at: datetime | None — when feedback was generated

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 8)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.reports.feedback_dto import FeedbackDTO

from core.models.enums.entity_enums import EntityType
from core.models.reports.submission import Submission


@dataclass(frozen=True)
class Feedback(Submission):
    """
    Immutable domain model for teacher feedback (EntityType.FEEDBACK_REPORT).

    Inherits all fields from Submission. Adds 2 feedback-specific fields.
    Uses subject_uid (from Submission) for "who this feedback is about".
    """

    def __post_init__(self) -> None:
        """Force ku_type=FEEDBACK_REPORT, then delegate to Submission."""
        if self.ku_type != EntityType.FEEDBACK_REPORT:
            object.__setattr__(self, "ku_type", EntityType.FEEDBACK_REPORT)
        super().__post_init__()

    # =========================================================================
    # FEEDBACK-SPECIFIC FIELDS
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | FeedbackDTO") -> "Feedback":  # type: ignore[override]
        """Create Feedback from an EntityDTO or FeedbackDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "FeedbackDTO":  # type: ignore[override]
        """Convert Feedback to domain-specific FeedbackDTO."""
        import dataclasses
        from typing import Any

        from core.models.reports.feedback_dto import FeedbackDTO

        dto_field_names = {f.name for f in dataclasses.fields(FeedbackDTO)}
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
        return FeedbackDTO(**kwargs)

    def __str__(self) -> str:
        return f"Feedback(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"Feedback(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"feedback={'yes' if self.feedback else 'no'}, "
            f"user_uid={self.user_uid})"
        )
