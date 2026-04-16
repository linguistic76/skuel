"""
JeOutputDTO - Journal Entry Output DTO (Tier 2 - Transfer)
============================================================

Extends UserOwnedDTO with 6 je_output-specific fields for the
LLM-processed transformation.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── JeOutputDTO(UserOwnedDTO) +6 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO
from core.ports import get_enum_value


@dataclass
class JeOutputDTO(UserOwnedDTO):
    """
    Mutable DTO for journal entry outputs (EntityType.JE_OUTPUT).

    Extends UserOwnedDTO with output-specific fields.
    Not a report — a transformation of the user's raw content.
    """

    # =========================================================================
    # OUTPUT-SPECIFIC FIELDS
    # =========================================================================
    output_content: str | None = None
    output_generated_at: datetime | None = None
    source_je_input_uid: str | None = None
    enrichment_mode: str | None = None
    output_file_path: str | None = None
    processor_type: ProcessorType | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including je_output-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                "output_content": self.output_content,
                "output_generated_at": self.output_generated_at,
                "source_je_input_uid": self.source_je_input_uid,
                "enrichment_mode": self.enrichment_mode,
                "output_file_path": self.output_file_path,
                "processor_type": get_enum_value(self.processor_type),
            }
        )

        convert_datetimes_to_iso(data, ["output_generated_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JeOutputDTO:
        """Create JeOutputDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "processor_type": ProcessorType,
            },
            datetime_fields=[
                "created_at",
                "updated_at",
                "output_generated_at",
            ],
            list_fields=["tags"],
            dict_fields=["metadata"],
        )

    # =========================================================================
    # UPDATE
    # =========================================================================

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update DTO fields from a dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(
            self,
            updates,
            allowed_fields={
                # EntityDTO fields
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # UserOwnedDTO fields
                "priority",
                "visibility",
                # JeOutput-specific fields
                "output_content",
                "output_generated_at",
                "source_je_input_uid",
                "enrichment_mode",
                "output_file_path",
                "processor_type",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "processor_type": ProcessorType,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, JeOutputDTO):
            return False
        return self.uid == other.uid
