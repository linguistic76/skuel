"""
Journal - Journal Domain Model
==================================

Frozen dataclass for journal entities (EntityType.JOURNAL).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Zero extra fields — journals use the same file/processing/subject fields
as other submission types. Journal-specific metadata (mood, energy_level,
entry_date) lives in the metadata dict.

See: /.claude/plans/ku-decomposition-domain-types.md (Phase 8)
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.journal_dto import JournalDTO
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import EntityType
from core.models.ku.submission import Submission


@dataclass(frozen=True)
class Journal(Submission):
    """
    Immutable domain model for journals (EntityType.JOURNAL).

    Inherits all fields from Submission. Zero extra fields.
    Journal-specific metadata (mood, energy_level, entry_date) lives
    in the metadata dict, not as first-class fields.
    """

    def __post_init__(self) -> None:
        """Force ku_type=JOURNAL, then delegate to Submission."""
        if self.ku_type != EntityType.JOURNAL:
            object.__setattr__(self, "ku_type", EntityType.JOURNAL)
        super().__post_init__()

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO | JournalDTO") -> "Journal":  # type: ignore[override]
        """Create Journal from a KuDTO or JournalDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "JournalDTO":  # type: ignore[override]
        """Convert Journal to JournalDTO (not generic KuDTO)."""
        import dataclasses
        from typing import Any

        from core.models.ku.journal_dto import JournalDTO

        dto_field_names = {f.name for f in dataclasses.fields(JournalDTO)}
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
        return JournalDTO(**kwargs)

    def __str__(self) -> str:
        return f"Journal(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Journal(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, user_uid={self.user_uid})"
        )
