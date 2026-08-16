"""
FormTemplateDTO - Transfer Tier for FormTemplate
=================================================

Mutable DTO extending EntityDTO with form-specific fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from core.models.entity_dto import EntityDTO
from core.models.enum_field_registry import enum_fields_for
from core.models.enums.entity_enums import EntityType
from core.utils.type_converters import get_enum_value


@dataclass
class FormTemplateDTO(EntityDTO):
    """Mutable DTO for FormTemplate entities."""

    # Honest leaf default (base EntityDTO requires entity_type — G6).
    entity_type: EntityType = field(default=EntityType.FORM_TEMPLATE, kw_only=True)

    # =========================================================================
    # FORM-SPECIFIC FIELDS
    # =========================================================================
    form_schema: list[dict[str, Any]] | None = field(default=None)
    instructions: str | None = None

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary using generic helper."""
        import json

        from core.models.dto_helpers import dto_to_dict

        data = dto_to_dict(
            self,
            enum_fields=["entity_type", "status", "domain"],
            datetime_fields=["created_at", "updated_at"],
        )
        data["form_schema"] = json.dumps(self.form_schema) if self.form_schema else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormTemplateDTO:
        """Create DTO from dictionary (from database)."""
        from core.models.dto_helpers import dto_from_dict

        # Pre-parse form_schema from JSON string
        raw_schema = data.get("form_schema")
        if isinstance(raw_schema, str):
            try:
                data["form_schema"] = json.loads(raw_schema)
            except json.JSONDecodeError, TypeError:
                data["form_schema"] = None

        return dto_from_dict(
            cls,
            data,
            enum_fields=enum_fields_for("entity_type", "status", "domain"),
            datetime_fields=["created_at", "updated_at"],
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
                "title",
                "content",
                "summary",
                "description",
                "word_count",
                "domain",
                "status",
                "tags",
                "metadata",
                # FormTemplate-specific
                "form_schema",
                "instructions",
            },
            enum_mappings=enum_fields_for("entity_type", "status", "domain"),
        )
        # Handle form_schema JSON string
        if "form_schema" in updates and isinstance(updates["form_schema"], str):
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                self.form_schema = json.loads(updates["form_schema"])

    def __eq__(self, other: object) -> bool:
        """Equality based on UID."""
        if not isinstance(other, FormTemplateDTO):
            return False
        return self.uid == other.uid


# Suppress unused import warning — get_enum_value used in parent's to_dict
_USE = get_enum_value
