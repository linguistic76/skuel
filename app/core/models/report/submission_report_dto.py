"""
SubmissionReportDTO - Submission Report DTO (Tier 2 - Transfer)
================================================================

Extends UserOwnedDTO with 5 report-specific fields matching the
SubmissionReport frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── SubmissionReportDTO(UserOwnedDTO) +5 fields
            ├── ExerciseReportDTO(SubmissionReportDTO) +0 fields
            └── JournalReportDTO(SubmissionReportDTO) +0 fields

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
class SubmissionReportDTO(UserOwnedDTO):
    """
    Mutable DTO for submission reports.

    Extends UserOwnedDTO with 5 report-specific fields:
    - report_content: str | None — the report text
    - report_generated_at: datetime | None — when report was generated
    - subject_uid: str | None — who/what this report is about
    - processor_type: ProcessorType | None — HUMAN/LLM/AUTOMATIC
    - report_file_path: str | None — generated output file path
    """

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    report_content: str | None = None
    report_generated_at: datetime | None = None
    subject_uid: str | None = None
    processor_type: ProcessorType | None = None
    report_file_path: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including report-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                "report_content": self.report_content,
                "report_generated_at": self.report_generated_at,
                "subject_uid": self.subject_uid,
                "processor_type": get_enum_value(self.processor_type),
                "report_file_path": self.report_file_path,
            }
        )

        convert_datetimes_to_iso(data, ["report_generated_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubmissionReportDTO:
        """Create SubmissionReportDTO from dictionary (from database)."""
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
                "report_generated_at",
            ],
            list_fields=["tags"],
            dict_fields=["metadata"],
            deprecated_fields=[
                "prerequisites",
                "enables",
                "related_to",
                "name",
                # Deprecated Submission fields (SubmissionReport no longer extends Submission)
                "original_filename",
                "file_path",
                "file_size",
                "file_type",
                "processing_started_at",
                "processing_completed_at",
                "processing_error",
                "processed_content",
                "processed_file_path",
                "instructions",
                "max_retention",
            ],
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
                # Report-specific fields
                "report_content",
                "report_generated_at",
                "subject_uid",
                "processor_type",
                "report_file_path",
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
        if not isinstance(other, SubmissionReportDTO):
            return False
        return self.uid == other.uid
