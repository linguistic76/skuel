"""
FeedbackKu - Feedback Report Domain Model
============================================

Frozen dataclass for teacher feedback entities (KuType.FEEDBACK_REPORT).

Inherits all fields from SubmissionKu (KuBase ~48 + 13 submission fields).
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
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType
from core.models.ku.ku_submission import SubmissionKu


@dataclass(frozen=True)
class FeedbackKu(SubmissionKu):
    """
    Immutable domain model for teacher feedback (KuType.FEEDBACK_REPORT).

    Inherits all fields from SubmissionKu. Adds 2 feedback-specific fields.
    Uses subject_uid (from SubmissionKu) for "who this feedback is about".
    """

    def __post_init__(self) -> None:
        """Force ku_type=FEEDBACK_REPORT, then delegate to SubmissionKu."""
        if self.ku_type != KuType.FEEDBACK_REPORT:
            object.__setattr__(self, "ku_type", KuType.FEEDBACK_REPORT)
        super().__post_init__()

    # =========================================================================
    # FEEDBACK-SPECIFIC FIELDS
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # CONVERSION (generic — uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "FeedbackKu":
        """Create FeedbackKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"FeedbackKu(uid={self.uid}, title='{self.title}', subject={self.subject_uid})"

    def __repr__(self) -> str:
        return (
            f"FeedbackKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"feedback={'yes' if self.feedback else 'no'}, "
            f"user_uid={self.user_uid})"
        )
