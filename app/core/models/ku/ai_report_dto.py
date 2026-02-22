"""
AiReportDTO - AI Report-Specific DTO (Tier 2 - Transfer)
==========================================================

Extends SubmissionDTO with zero additional fields. AI reports use
subject_uid and processed_content from SubmissionDTO.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── SubmissionDTO(UserOwnedDTO) +13 fields
            └── AiReportDTO(SubmissionDTO) +0 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.ku.submission_dto import SubmissionDTO


@dataclass
class AiReportDTO(SubmissionDTO):
    """
    Mutable DTO for AI-generated reports (EntityType.AI_REPORT).

    Inherits all fields from SubmissionDTO. Zero extra fields.
    Uses subject_uid for "who this report is about" and
    processed_content for AI-generated text.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AiReportDTO:
        """Create AiReportDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "processor_type": ProcessorType,
            },
            datetime_fields=[
                "created_at", "updated_at",
                "processing_started_at", "processing_completed_at",
            ],
            list_fields=["tags"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, AiReportDTO):
            return False
        return self.uid == other.uid
