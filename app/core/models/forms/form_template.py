"""
FormTemplate - General-Purpose Form Definition
===============================================

Frozen dataclass for admin-created form templates. Extends Entity directly
(not Curriculum) — doesn't need 21 Curriculum fields.

FormTemplates define a form_schema (list of field specs) that gets rendered
as inline forms in Articles via EMBEDS_FORM relationships.

Hierarchy:
    Entity (~19 fields)
    └── FormTemplate(Entity) +2 fields (form_schema, instructions)

See: /docs/user-guides/form-submissions.md
"""

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType

if TYPE_CHECKING:
    from core.models.forms.form_template_dto import FormTemplateDTO


@dataclass(frozen=True)
class FormTemplate(Entity):
    """
    Immutable domain model for form templates (EntityType.FORM_TEMPLATE).

    A FormTemplate defines:
    1. **form_schema** — Field specifications (name, type, label, options, etc.)
    2. **instructions** — Optional instructions displayed above the form

    Shared content (admin-created, no user_uid).
    """

    # =========================================================================
    # FORM-SPECIFIC FIELDS
    # =========================================================================
    form_schema: tuple[dict[str, Any], ...] | None = None
    instructions: str | None = None

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __post_init__(self) -> None:
        """Force entity_type and parse form_schema from JSON if needed."""
        object.__setattr__(self, "entity_type", EntityType.FORM_TEMPLATE)

        # Parse form_schema from JSON string (Neo4j stores as string)
        if isinstance(self.form_schema, str):
            try:
                parsed = json.loads(self.form_schema)
                if isinstance(parsed, list):
                    object.__setattr__(self, "form_schema", tuple(parsed))
                else:
                    object.__setattr__(self, "form_schema", None)
            except (json.JSONDecodeError, TypeError):
                object.__setattr__(self, "form_schema", None)
        elif isinstance(self.form_schema, list):
            object.__setattr__(self, "form_schema", tuple(self.form_schema))

        super().__post_init__()

    # =========================================================================
    # QUERIES
    # =========================================================================

    def has_form_schema(self) -> bool:
        """Check if this template has a valid form schema."""
        return self.form_schema is not None and len(self.form_schema) > 0

    def is_valid(self) -> bool:
        """Validate minimum required fields."""
        return bool(self.title) and self.has_form_schema()

    def validate_response(self, form_data: dict[str, Any]) -> list[str]:
        """
        Validate form_data against this template's form_schema.

        Checks:
        - Required fields are present and non-empty
        - Field names match schema (no unknown fields)
        - Text/textarea min_length and max_length constraints
        - Text field pattern (regex) constraints
        - Select field values are in allowed options
        - Number fields contain numeric values and respect min/max

        Returns list of validation error messages (empty = valid).
        """
        errors: list[str] = []
        if not self.form_schema:
            errors.append("Template has no form_schema defined")
            return errors

        schema_names = {spec["name"] for spec in self.form_schema}

        # Check for unknown fields
        errors.extend(
            f"Unknown field '{key}' not in template schema"
            for key in form_data
            if key not in schema_names
        )

        for spec in self.form_schema:
            name = spec["name"]
            field_type = spec.get("type", "text")
            required = spec.get("required", False)
            value = form_data.get(name)

            # Required field check
            if required and (value is None or (isinstance(value, str) and not value.strip())):
                errors.append(f"Required field '{name}' is missing or empty")
                continue

            # Skip further validation if value is empty/missing and not required
            if value is None or (isinstance(value, str) and not value.strip()):
                continue

            # Select field: value must be in options
            if field_type == "select":
                options = spec.get("options", [])
                if options and value not in options:
                    errors.append(
                        f"Field '{name}' value '{value}' not in allowed options: {options}"
                    )

            # Text/textarea: min_length, max_length, pattern
            if field_type in ("text", "textarea") and isinstance(value, str):
                min_length = spec.get("min_length")
                max_length = spec.get("max_length")
                if min_length is not None and len(value) < min_length:
                    errors.append(
                        f"Field '{name}' must be at least {min_length} characters"
                    )
                if max_length is not None and len(value) > max_length:
                    errors.append(
                        f"Field '{name}' must be at most {max_length} characters"
                    )

            if field_type == "text" and isinstance(value, str):
                pattern = spec.get("pattern")
                if pattern is not None:
                    try:
                        if not re.fullmatch(pattern, value):
                            errors.append(
                                f"Field '{name}' does not match required pattern"
                            )
                    except re.error:
                        pass  # Invalid regex in schema — skip pattern check

            # Number field: value must be numeric
            if field_type == "number":
                try:
                    num_val = float(value) if isinstance(value, str) else value
                    if not isinstance(num_val, int | float):
                        errors.append(f"Field '{name}' must be a number")
                    else:
                        min_val = spec.get("min")
                        max_val = spec.get("max")
                        if min_val is not None and num_val < min_val:
                            errors.append(f"Field '{name}' must be >= {min_val}")
                        if max_val is not None and num_val > max_val:
                            errors.append(f"Field '{name}' must be <= {max_val}")
                except (ValueError, TypeError):
                    errors.append(f"Field '{name}' must be a number, got '{value}'")

        return errors

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def _from_dto(cls, dto: "FormTemplateDTO") -> Self:
        """Create FormTemplate from DTO."""
        return cls(
            uid=dto.uid,
            title=dto.title,
            entity_type=EntityType.FORM_TEMPLATE,
            parent_entity_uid=dto.parent_entity_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            content=dto.content,
            summary=dto.summary,
            description=dto.description,
            word_count=dto.word_count,
            status=dto.status,
            tags=tuple(dto.tags) if dto.tags else (),
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=dto.metadata or {},
            form_schema=tuple(dto.form_schema) if dto.form_schema else None,
            instructions=dto.instructions,
        )

    def to_dto(self) -> "FormTemplateDTO":
        """Convert to FormTemplateDTO."""
        from core.models.forms.form_template_dto import FormTemplateDTO

        return FormTemplateDTO(
            uid=self.uid,
            title=self.title,
            entity_type=self.entity_type,
            parent_entity_uid=self.parent_entity_uid,
            domain=self.domain,
            created_by=self.created_by,
            content=self.content,
            summary=self.summary,
            description=self.description,
            word_count=self.word_count,
            status=self.status,
            tags=list(self.tags),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=dict(self.metadata) if self.metadata else {},
            form_schema=list(self.form_schema) if self.form_schema else None,
            instructions=self.instructions,
        )

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __str__(self) -> str:
        fields = len(self.form_schema) if self.form_schema else 0
        return f"FormTemplate(uid={self.uid}, title='{self.title}', fields={fields})"

    def __repr__(self) -> str:
        return (
            f"FormTemplate(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, form_schema={self.form_schema is not None})"
        )
