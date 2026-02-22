"""
AiReport - AI Report Domain Model
======================================

Frozen dataclass for AI-generated report entities (EntityType.AI_REPORT).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Zero extra fields — AI reports use subject_uid (who the report is about)
and processed_content (AI-generated text) from Submission.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 8)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import EntityType
from core.models.ku.submission import Submission


@dataclass(frozen=True)
class AiReport(Submission):
    """
    Immutable domain model for AI-generated reports (EntityType.AI_REPORT).

    Inherits all fields from Submission. Zero extra fields.
    Uses subject_uid for "who this report is about" and
    processed_content for AI-generated text.
    """

    def __post_init__(self) -> None:
        """Force ku_type=AI_REPORT, then delegate to Submission."""
        if self.ku_type != EntityType.AI_REPORT:
            object.__setattr__(self, "ku_type", EntityType.AI_REPORT)
        super().__post_init__()

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "AiReport":
        """Create AiReport from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"AiReport(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"AiReport(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, subject_uid={self.subject_uid}, "
            f"user_uid={self.user_uid})"
        )
