"""
JeOutput - Journal Entry Output (LLM-processed transformation)
================================================================

Frozen dataclass for journal entry outputs (EntityType.JE_OUTPUT).

A je_output is the LLM-processed transformation of a je_input text file.
It is NOT a report — reports provide feedback or analysis. A je_output is
a reformatting: the LLM converts, structures, or enriches the user's raw
content according to instructions. The user remains the sole interpreter.

Pipeline position: JE_INPUT → LLM → **JE_OUTPUT**

Extends UserOwnedEntity directly (NOT ExerciseReport — not an interpretation).

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.journal.je_output_dto import JeOutputDTO

from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.enums.submissions_enums import EnrichmentMode
from core.models.user_owned_entity import UserOwnedEntity


@dataclass(frozen=True, kw_only=True)
class JeOutput(UserOwnedEntity):
    """
    Immutable domain model for journal entry outputs (EntityType.JE_OUTPUT).

    LLM-processed transformation of a JeInput. Not feedback. Not analysis.
    The user is the sole interpreter of their journal content.
    """

    def __post_init__(self) -> None:
        """Force entity_type=JE_OUTPUT, convert enrichment_mode str→enum."""
        if self.entity_type != EntityType.JE_OUTPUT:
            object.__setattr__(self, "entity_type", EntityType.JE_OUTPUT)
        if isinstance(self.enrichment_mode, str) and not isinstance(
            self.enrichment_mode, EnrichmentMode
        ):
            object.__setattr__(self, "enrichment_mode", EnrichmentMode(self.enrichment_mode))
        super().__post_init__()

    # =========================================================================
    # OUTPUT-SPECIFIC FIELDS
    # =========================================================================
    output_content: str | None = None  # The transformed text
    output_generated_at: datetime | None = None
    source_je_input_uid: str | None = None  # FK to the JeInput this transforms
    enrichment_mode: EnrichmentMode | None = None
    output_file_path: str | None = None  # Path to generated output file on disk
    processor_type: ProcessorType | None = None  # LLM that produced this

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | JeOutputDTO") -> "JeOutput":  # type: ignore[override]
        """Create JeOutput from an EntityDTO or JeOutputDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "JeOutputDTO":  # type: ignore[override]
        """Convert to JeOutputDTO."""
        import dataclasses
        from typing import Any

        from core.models.journal.je_output_dto import JeOutputDTO

        dto_field_names = {f.name for f in dataclasses.fields(JeOutputDTO)}
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
        return JeOutputDTO(**kwargs)

    def __str__(self) -> str:
        return f"JeOutput(uid={self.uid}, title='{self.title}', source={self.source_je_input_uid})"

    def __repr__(self) -> str:
        return (
            f"JeOutput(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, source_je_input_uid={self.source_je_input_uid}, "
            f"enrichment_mode={self.enrichment_mode}, user_uid={self.user_uid})"
        )
