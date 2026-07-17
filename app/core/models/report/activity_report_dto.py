"""
ActivityReportDTO - Activity Report-Specific DTO (Tier 2 - Transfer)
=====================================================================

Extends UserOwnedDTO with fields specific to ActivityReport (activity-level
AI or human feedback). Mirrors ActivityReport frozen dataclass (Tier 3).

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── ActivityReportDTO(UserOwnedDTO) +14 fields

ActivityReport is NOT a Submission subtype — it has no file fields. It
responds to a user's aggregate activity patterns over a time window.

See: /docs/patterns/three_tier_type_system.md
See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import ReportSource
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class ActivityReportDTO(UserOwnedDTO):
    """
    Mutable DTO for Activity Report entities (EntityType.ACTIVITY_REPORT).

    Extends UserOwnedDTO with activity-feedback-specific fields.
    No file fields (original_filename, file_path, etc.) — those belong to Submission.
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.ACTIVITY_REPORT, kw_only=True)

    # Generated artifact: COMPLETED is the only valid status (see
    # _VALID_STATUSES_BY_TYPE) — override EntityDTO's DRAFT default so a
    # status-omitted DTO can't produce an out-of-set report via from_dto().
    status: EntityStatus = field(default=EntityStatus.COMPLETED, kw_only=True)

    # =========================================================================
    # PROCESSOR
    # =========================================================================
    processor_type: ReportSource | None = None

    # =========================================================================
    # SUBJECT
    # =========================================================================
    subject_uid: str | None = None  # user_uid this feedback is about

    # =========================================================================
    # TIME WINDOW
    # =========================================================================
    time_period: str | None = None  # "7d" | "14d" | "30d" | "90d"
    period_start: datetime | None = None
    period_end: datetime | None = None

    # =========================================================================
    # ANALYSIS CONFIGURATION
    # =========================================================================
    domains_covered: list[str] = field(default_factory=list)  # activity domain names
    depth: str | None = None  # summary | standard | detailed

    # =========================================================================
    # CONTENT
    # =========================================================================
    processed_content: str | None = None  # LLM output or human-written feedback
    processing_error: str | None = None

    # =========================================================================
    # INSIGHT REFERENCES
    # =========================================================================
    insights_referenced: list[str] = field(default_factory=list)  # insight UIDs

    # =========================================================================
    # ANNOTATION
    # =========================================================================
    user_annotation: str | None = None  # Additive commentary alongside AI synthesis
    user_revision: str | None = None  # User-curated replacement for sharing
    annotation_mode: str | None = None  # "additive" | "revision" | None
    annotation_updated_at: datetime | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "visibility", "processor_type"],
            datetime_fields=[
                "created_at",
                "updated_at",
                "period_start",
                "period_end",
                "annotation_updated_at",
            ],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActivityReportDTO:
        """Create ActivityReportDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "processor_type",
            ),
            datetime_fields=[
                "created_at",
                "updated_at",
                "period_start",
                "period_end",
                "annotation_updated_at",
            ],
            list_fields=["tags", "domains_covered", "insights_referenced"],
            dict_fields=["metadata"],
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, ActivityReportDTO):
            return False
        return self.uid == other.uid
