"""
AiFeedbackDTO - AI Feedback-Specific DTO (Tier 2 - Transfer)
=============================================================

Extends UserOwnedDTO with fields specific to AiFeedback (activity-level
AI or human feedback). Mirrors AiFeedback frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── AiFeedbackDTO(UserOwnedDTO) +10 fields

AiFeedback is NOT a Submission subtype — it has no file fields. It
responds to a user's aggregate activity patterns over a time window.

See: /docs/patterns/three_tier_type_system.md
See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class AiFeedbackDTO(UserOwnedDTO):
    """
    Mutable DTO for AI Feedback entities (EntityType.AI_FEEDBACK).

    Extends UserOwnedDTO with activity-feedback-specific fields.
    No file fields (original_filename, file_path, etc.) — those belong to Submission.
    """

    # =========================================================================
    # PROCESSOR
    # =========================================================================
    processor_type: ProcessorType | None = None

    # =========================================================================
    # SUBJECT
    # =========================================================================
    subject_uid: str | None = None          # user_uid this feedback is about

    # =========================================================================
    # TIME WINDOW
    # =========================================================================
    time_period: str | None = None          # "7d" | "14d" | "30d" | "90d"
    period_start: datetime | None = None
    period_end: datetime | None = None

    # =========================================================================
    # ANALYSIS CONFIGURATION
    # =========================================================================
    domains_covered: list[str] = field(default_factory=list)  # activity domain names
    depth: str | None = None                # summary | standard | detailed

    # =========================================================================
    # CONTENT
    # =========================================================================
    processed_content: str | None = None    # LLM output or human-written feedback
    processing_error: str | None = None

    # =========================================================================
    # INSIGHT REFERENCES
    # =========================================================================
    insights_referenced: list[str] = field(default_factory=list)  # insight UIDs

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, including AiFeedback-specific fields."""
        data = super().to_dict()
        if self.processor_type is not None:
            from core.ports import get_enum_value
            data["processor_type"] = get_enum_value(self.processor_type)
        data["subject_uid"] = self.subject_uid
        data["time_period"] = self.time_period
        if self.period_start is not None:
            data["period_start"] = self.period_start.isoformat()
        if self.period_end is not None:
            data["period_end"] = self.period_end.isoformat()
        data["domains_covered"] = self.domains_covered
        data["depth"] = self.depth
        data["processed_content"] = self.processed_content
        data["processing_error"] = self.processing_error
        data["insights_referenced"] = self.insights_referenced
        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AiFeedbackDTO:
        """Create AiFeedbackDTO from dictionary (from database)."""
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
                "period_start",
                "period_end",
            ],
            list_fields=["tags", "domains_covered", "insights_referenced"],
            dict_fields=["metadata"],
            deprecated_fields=["prerequisites", "enables", "related_to", "name"],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, AiFeedbackDTO):
            return False
        return self.uid == other.uid
