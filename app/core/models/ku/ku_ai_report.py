"""
AiReportKu - AI Report Domain Model
======================================

Frozen dataclass for AI-generated report entities (KuType.AI_REPORT).

Inherits all fields from SubmissionKu (KuBase ~48 + 13 submission fields).
Zero extra fields — AI reports use subject_uid (who the report is about)
and processed_content (AI-generated text) from SubmissionKu.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 8)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import KuType
from core.models.ku.ku_submission import SubmissionKu


@dataclass(frozen=True)
class AiReportKu(SubmissionKu):
    """
    Immutable domain model for AI-generated reports (KuType.AI_REPORT).

    Inherits all fields from SubmissionKu. Zero extra fields.
    Uses subject_uid for "who this report is about" and
    processed_content for AI-generated text.
    """

    def __post_init__(self) -> None:
        """Force ku_type=AI_REPORT, then delegate to SubmissionKu."""
        if self.ku_type != KuType.AI_REPORT:
            object.__setattr__(self, "ku_type", KuType.AI_REPORT)
        super().__post_init__()

    # =========================================================================
    # CONVERSION (generic — uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "AiReportKu":
        """Create AiReportKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"AiReportKu(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"AiReportKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"user_uid={self.user_uid})"
        )
