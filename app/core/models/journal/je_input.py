"""
JeInput - Journal Entry Input (raw user content)
==================================================

Frozen dataclass for journal entry inputs (EntityType.JE_INPUT).

A je_input is raw user content — an audio recording or text file created by
the user's own initiative. No authority assigns it. No prompt triggers it.

Deepgram transcribes audio to text, but both forms are still je_input —
the format changes, the nature doesn't.

Pipeline position: **JE_INPUT** → LLM → JE_OUTPUT

Extends UserOwnedEntity directly (NOT Submission — journals are not submissions).
Carries its own file and processing fields.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.journal.je_input_dto import JeInputDTO

from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True)
class JeInput(UserOwnedEntity):
    """
    Immutable domain model for journal entry inputs (EntityType.JE_INPUT).

    Raw user content — audio or text. Self-initiated reflective writing.
    Journal-specific metadata (mood, energy_level, entry_date, source_type)
    lives in the metadata dict, not as first-class fields.
    """

    def __post_init__(self) -> None:
        """Force entity_type=JE_INPUT, then delegate to UserOwnedEntity."""
        if self.entity_type != EntityType.JE_INPUT:
            object.__setattr__(self, "entity_type", EntityType.JE_INPUT)
        super().__post_init__()

    # =========================================================================
    # FILE (uploads)
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None  # MIME type (e.g., "audio/mpeg", "text/plain")

    # =========================================================================
    # PROCESSING (Deepgram transcription + LLM formatting)
    # =========================================================================
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None  # type: ignore[assignment]
    processing_completed_at: datetime | None = None  # type: ignore[assignment]
    processing_error: str | None = None
    processed_content: str | None = None  # Transcribed/cleaned text
    processed_file_path: str | None = None
    instructions: str | None = None  # LLM processing instructions
    max_retention: int | None = None  # FIFO cleanup limit (None = permanent)

    # =========================================================================
    # TITLE GENERATION
    # =========================================================================

    @classmethod
    def generate_title(cls, user_uid: UserUID, entry_date: date, order: int) -> str:
        """Auto-generate the canonical journal entry title.

        Format: Journal — {user_id} — {Mar 02, 2026} — #{order}
        Example: Journal — mike — Mar 02, 2026 — #1
        """
        user_id = user_uid.removeprefix("user_")
        date_str = entry_date.strftime("%b %d, %Y")
        return f"Journal \u2014 {user_id} \u2014 {date_str} \u2014 #{order}"

    # =========================================================================
    # PROCESSING METHODS
    # =========================================================================

    def get_processing_duration(self) -> float | None:
        """Get processing duration in seconds, or None if not applicable."""
        if not self.processing_started_at or not self.processing_completed_at:
            return None
        delta = self.processing_completed_at - self.processing_started_at
        if isinstance(delta, timedelta):
            return delta.total_seconds()
        try:
            return float(delta.seconds)
        except AttributeError:
            try:
                return float(delta)
            except (TypeError, ValueError):
                return None

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of content (body text or processed content)."""
        text = self.content or self.processed_content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | JeInputDTO") -> "JeInput":  # type: ignore[override]
        """Create JeInput from an EntityDTO or JeInputDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "JeInputDTO":  # type: ignore[override]
        """Convert to JeInputDTO."""
        import dataclasses
        from typing import Any

        from core.models.journal.je_input_dto import JeInputDTO

        dto_field_names = {f.name for f in dataclasses.fields(JeInputDTO)}
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
        return JeInputDTO(**kwargs)

    def __str__(self) -> str:
        return f"JeInput(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"JeInput(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, user_uid={self.user_uid})"
        )
