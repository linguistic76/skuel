"""
JournalReportDTO - Journal Report DTO (Tier 2 - Transfer)
============================================================

Extends SubmissionReportDTO with zero additional fields.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── SubmissionReportDTO(UserOwnedDTO) +5 fields
            └── JournalReportDTO(SubmissionReportDTO) +0 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.report.submission_report_dto import SubmissionReportDTO


@dataclass
class JournalReportDTO(SubmissionReportDTO):
    """
    Mutable DTO for journal reports (EntityType.JOURNAL_REPORT).

    Inherits all fields from SubmissionReportDTO. Zero extra fields.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalReportDTO:
        """Create JournalReportDTO from dictionary (from database)."""
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
                # Deprecated Submission fields
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

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, JournalReportDTO):
            return False
        return self.uid == other.uid
