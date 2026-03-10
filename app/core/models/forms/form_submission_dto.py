"""
FormSubmissionDTO - Transfer Tier for FormSubmission
====================================================

Mutable DTO extending UserOwnedDTO with form submission fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility
from core.models.user_owned_dto import UserOwnedDTO


@dataclass
class FormSubmissionDTO(UserOwnedDTO):
    """Mutable DTO for FormSubmission entities."""

    # =========================================================================
    # FORM SUBMISSION FIELDS
    # =========================================================================
    form_template_uid: str | None = None
    form_data: dict[str, Any] | None = field(default=None)
    processed_content: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        data = super().to_dict()
        data["form_template_uid"] = self.form_template_uid
        # Store form_data as JSON string in Neo4j
        data["form_data"] = json.dumps(self.form_data) if self.form_data else None
        data["processed_content"] = self.processed_content
        return data

    # =========================================================================
    # DESERIALIZATION
    # =========================================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormSubmissionDTO:
        """Create DTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        # Pre-parse form_data from JSON string
        raw_data = data.get("form_data")
        if isinstance(raw_data, str):
            try:
                data["form_data"] = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError):
                data["form_data"] = None

        return dto_from_dict(
            cls,
            data,
            enum_fields={
                "entity_type": EntityType,
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
            datetime_fields=["created_at", "updated_at"],
            list_fields=["tags"],
            dict_fields=["metadata", "form_data"],
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
                "title",
                "content",
                "summary",
                "description",
                "status",
                "tags",
                "metadata",
                "priority",
                "visibility",
                # FormSubmission-specific
                "form_data",
                "processed_content",
            },
            enum_mappings={
                "status": EntityStatus,
                "domain": Domain,
                "visibility": Visibility,
            },
        )
        # Handle form_data JSON string
        if "form_data" in updates and isinstance(updates["form_data"], str):
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                self.form_data = json.loads(updates["form_data"])

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, FormSubmissionDTO):
            return False
        return self.uid == other.uid
