"""
JeInputDTO - Journal Entry Input DTO (Tier 2 - Transfer)
==========================================================

Extends UserOwnedDTO with 12 je_input-specific fields for file storage
and processing tracking.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── JeInputDTO(UserOwnedDTO) +12 fields

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
class JeInputDTO(UserOwnedDTO):
    """
    Mutable DTO for journal entry inputs (EntityType.JE_INPUT).

    Extends UserOwnedDTO with file and processing fields.
    Journal-specific metadata (mood, energy_level, entry_date) lives
    in the metadata dict, not as first-class fields.
    """

    # =========================================================================
    # FILE
    # =========================================================================
    original_filename: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    file_type: str | None = None

    # =========================================================================
    # PROCESSING
    # =========================================================================
    processor_type: ProcessorType | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None
    max_retention: int | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including je_input-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                # File
                "original_filename": self.original_filename,
                "file_path": self.file_path,
                "file_size": self.file_size,
                "file_type": self.file_type,
                # Processing
                "processor_type": get_enum_value(self.processor_type),
                "processing_started_at": self.processing_started_at,
                "processing_completed_at": self.processing_completed_at,
                "processing_error": self.processing_error,
                "processed_content": self.processed_content,
                "processed_file_path": self.processed_file_path,
                "instructions": self.instructions,
                "max_retention": self.max_retention,
            }
        )

        convert_datetimes_to_iso(data, ["processing_started_at", "processing_completed_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JeInputDTO:
        """Create JeInputDTO from dictionary (from database)."""
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
                "processing_started_at",
                "processing_completed_at",
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
                # JeInput-specific fields
                "original_filename",
                "file_path",
                "file_size",
                "file_type",
                "processor_type",
                "processing_started_at",
                "processing_completed_at",
                "processing_error",
                "processed_content",
                "processed_file_path",
                "instructions",
                "max_retention",
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
        if not isinstance(other, JeInputDTO):
            return False
        return self.uid == other.uid
