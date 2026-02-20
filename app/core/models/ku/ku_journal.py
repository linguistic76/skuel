"""
JournalKu - Journal Domain Model
==================================

Frozen dataclass for journal entities (KuType.JOURNAL).

Inherits all fields from SubmissionKu (KuBase ~48 + 13 submission fields).
Zero extra fields — journals use the same file/processing/subject fields
as other submission types. Journal-specific metadata (mood, energy_level,
entry_date) lives in the metadata dict.

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
class JournalKu(SubmissionKu):
    """
    Immutable domain model for journals (KuType.JOURNAL).

    Inherits all fields from SubmissionKu. Zero extra fields.
    Journal-specific metadata (mood, energy_level, entry_date) lives
    in the metadata dict, not as first-class fields.
    """

    def __post_init__(self) -> None:
        """Force ku_type=JOURNAL, then delegate to SubmissionKu."""
        if self.ku_type != KuType.JOURNAL:
            object.__setattr__(self, "ku_type", KuType.JOURNAL)
        super().__post_init__()

    # =========================================================================
    # CONVERSION (generic — uses KuBase._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "JournalKu":
        """Create JournalKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"JournalKu(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"JournalKu(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, user_uid={self.user_uid})"
        )
