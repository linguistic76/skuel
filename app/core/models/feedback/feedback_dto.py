"""
FeedbackDTO - Feedback Report-Specific DTO (Tier 2 - Transfer)
================================================================

Extends SubmissionDTO with 2 feedback-specific fields matching the
Feedback frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── SubmissionDTO(UserOwnedDTO) +13 fields
            └── FeedbackDTO(SubmissionDTO) +2 fields

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
from core.models.submissions.submission_dto import SubmissionDTO


@dataclass
class FeedbackDTO(SubmissionDTO):
    """
    Mutable DTO for teacher feedback (EntityType.FEEDBACK_REPORT).

    Extends SubmissionDTO with 2 feedback-specific fields:
    - feedback: str | None — the feedback text
    - feedback_generated_at: datetime | None — when feedback was generated
    """

    # =========================================================================
    # FEEDBACK-SPECIFIC FIELDS
    # =========================================================================
    feedback: str | None = None
    feedback_generated_at: datetime | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including feedback-specific fields."""
        from core.models.dto_helpers import convert_datetimes_to_iso

        data = super().to_dict()

        data.update(
            {
                "feedback": self.feedback,
                "feedback_generated_at": self.feedback_generated_at,
            }
        )

        convert_datetimes_to_iso(data, ["feedback_generated_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackDTO:
        """Create FeedbackDTO from dictionary (from database)."""
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
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
                "feedback_generated_at",
            ],
            list_fields=["tags"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
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
                # SubmissionDTO fields
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
                "subject_uid",
                # Feedback-specific fields
                "feedback",
                "feedback_generated_at",
            },
            enum_mappings={
                "ku_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "processor_type": ProcessorType,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, FeedbackDTO):
            return False
        return self.uid == other.uid
