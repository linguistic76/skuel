"""
Journal - Journal Domain Model
==================================

Frozen dataclass for journal entities (EntityType.JOURNAL).

Inherits all fields from Submission (Entity ~48 + 13 submission fields).
Zero extra fields — journals use the same file/processing/subject fields
as other submission types. Journal-specific metadata (mood, energy_level,
entry_date) lives in the metadata dict.

See: /.claude/plans/ku-decomposition-domain-types.md
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.submissions.journal_dto import JournalDTO

from core.models.enums.entity_enums import EntityType
from core.models.submissions.submission import Submission


@dataclass(frozen=True)
class Journal(Submission):
    """
    Immutable domain model for journals (EntityType.JOURNAL).

    Inherits all fields from Submission. Zero extra fields.
    Journal-specific metadata (mood, energy_level, entry_date) lives
    in the metadata dict, not as first-class fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=JOURNAL, then delegate to Submission."""
        if self.entity_type != EntityType.JOURNAL:
            object.__setattr__(self, "entity_type", EntityType.JOURNAL)
        super().__post_init__()

    # =========================================================================
    # TITLE GENERATION
    # =========================================================================

    @classmethod
    def generate_title(cls, user_uid: str, entry_date: date, order: int) -> str:
        """Auto-generate the canonical journal title.

        Format: Journal — {user_id} — {Mar 02, 2026} — #{order}
        Example: Journal — mike — Mar 02, 2026 — #1
        """
        user_id = user_uid.removeprefix("user_")
        date_str = entry_date.strftime("%b %d, %Y")
        return f"Journal \u2014 {user_id} \u2014 {date_str} \u2014 #{order}"

    # =========================================================================
    # CONVERSION (generic — uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | JournalDTO") -> "Journal":  # type: ignore[override]
        """Create Journal from an EntityDTO or JournalDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "JournalDTO":  # type: ignore[override]
        """Convert Journal to domain-specific JournalDTO."""
        import dataclasses
        from typing import Any

        from core.models.submissions.journal_dto import JournalDTO

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
