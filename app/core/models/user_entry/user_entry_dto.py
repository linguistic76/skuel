"""
UserEntryDTO - Transfer DTO for UserEntry (ADR-054)
====================================================

Mirrors `UserEntry` (frozen dataclass) as a mutable DTO for data movement
between layers. Replaces `SubmissionDTO`, `ExerciseSubmissionDTO`,
`JeInputDTO`, and `JeOutputDTO`.

Hierarchy:
    EntityDTO (~18 common fields)
    └── UserOwnedDTO(EntityDTO) +3 fields (user_uid, visibility, priority)
        └── UserEntryDTO(UserOwnedDTO) +15 user-entry fields

See: /docs/patterns/three_tier_type_system.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class UserEntryDTO(UserOwnedDTO):
    """
    Mutable DTO for unified user-authored content (ADR-054).

    Extends `UserOwnedDTO` with:
    - File (4): original_filename, file_path, file_size, file_type
    - Processing (9): pipeline, private, timestamps, error, content, file,
                      instructions, max_retention
    - Modality (1): modality
    """

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.USER_ENTRY, kw_only=True)

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
    pipeline: Pipeline = Pipeline.NONE
    private: bool = False  # companion-retrieval opt-out (see UserEntry docstring)
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    processing_error: str | None = None
    processed_content: str | None = None
    processed_file_path: str | None = None
    instructions: str | None = None
    journal_mode: str | None = None
    max_retention: int | None = None

    # =========================================================================
    # MODALITY
    # =========================================================================
    modality: SubmissionModality | None = None

    # =========================================================================
    # DECLARED EXERCISE INTENT (vault living channel — see UserEntry docstring)
    # =========================================================================
    fulfills_exercise_uid: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        from core.models.dto_helpers import dto_to_dict

        return dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain", "visibility", "pipeline", "modality"],
            datetime_fields=[
                "created_at",
                "updated_at",
                "processing_started_at",
                "processing_completed_at",
            ],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserEntryDTO:
        """Create UserEntryDTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "pipeline",
                "modality",
            ),
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
                # UserEntry-specific fields
                "original_filename",
                "file_path",
                "file_size",
                "file_type",
                "pipeline",
                "processing_started_at",
                "processing_completed_at",
                "processing_error",
                "processed_content",
                "processed_file_path",
                "instructions",
                "journal_mode",
                "max_retention",
                "modality",
            },
            enum_mappings=enum_fields_for(
                "entity_type",
                "status",
                "domain",
                "visibility",
                "pipeline",
                "modality",
            ),
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, UserEntryDTO):
            return False
        return self.uid == other.uid
