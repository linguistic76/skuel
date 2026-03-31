"""
ExerciseReportDTO - Exercise Report DTO (Tier 2 - Transfer)
=============================================================

Extends UserOwnedDTO with 6 report-specific fields.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields
        └── ExerciseReportDTO(UserOwnedDTO) +5 fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO
from core.ports import get_enum_value


@dataclass
class ExerciseReportDTO(UserOwnedDTO):
    """
    Mutable DTO for exercise reports (EntityType.EXERCISE_REPORT).

    Extends UserOwnedDTO with 6 report-specific fields:
    - report_content: str | None — the report text
    - report_generated_at: datetime | None — when report was generated
    - subject_uid: str | None — who/what this report is about
    - processor_type: ProcessorType | None — HUMAN/LLM/AUTOMATIC
    - assessment_outcome: AssessmentOutcome | None — APPROVED/NEEDS_REVISION/AI_EVALUATED
    - report_file_path: str | None — generated output file path
    """

    # =========================================================================
    # REPORT-SPECIFIC FIELDS
    # =========================================================================
    report_content: str | None = None
    report_generated_at: datetime | None = None
    subject_uid: str | None = None
    processor_type: ProcessorType | None = None
    assessment_outcome: AssessmentOutcome | None = None
    report_file_path: str | None = None
    assessment_score: float | None = None  # 0.0-1.0 score for assessments

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
                "assessment_outcome": get_enum_value(self.assessment_outcome),
                "report_file_path": self.report_file_path,
                "assessment_score": self.assessment_score,
            }
        )

        convert_datetimes_to_iso(data, ["report_generated_at"])

        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExerciseReportDTO:
        """Create ExerciseReportDTO from dictionary (from database)."""
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
                "assessment_outcome": AssessmentOutcome,
            },
            datetime_fields=[
                "created_at",
                "updated_at",
                "report_generated_at",
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
                # Report-specific fields
                "report_content",
                "report_generated_at",
                "subject_uid",
                "processor_type",
                "assessment_outcome",
                "report_file_path",
                "assessment_score",
            },
            enum_mappings={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
                "processor_type": ProcessorType,
                "assessment_outcome": AssessmentOutcome,
            },
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ExerciseReportDTO):
            return False
        return self.uid == other.uid
