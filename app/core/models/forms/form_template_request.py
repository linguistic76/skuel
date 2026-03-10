"""
FormTemplate Request Models - API Validation (Tier 1 - External)
================================================================

Pydantic models for FormTemplate create/update API validation.
Reuses the same form_schema validation pattern as Exercise.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

VALID_FIELD_TYPES = {"text", "textarea", "select", "checkbox", "number", "date"}


def validate_form_field_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate a list of form field specs have required keys and valid types."""
    for i, field_spec in enumerate(specs):
        if "name" not in field_spec:
            msg = f"Field {i} missing required key 'name'"
            raise ValueError(msg)
        if "type" not in field_spec:
            msg = f"Field {i} missing required key 'type'"
            raise ValueError(msg)
        if "label" not in field_spec:
            msg = f"Field {i} missing required key 'label'"
            raise ValueError(msg)
        if field_spec["type"] not in VALID_FIELD_TYPES:
            msg = f"Field {i} has invalid type '{field_spec['type']}'. Valid: {VALID_FIELD_TYPES}"
            raise ValueError(msg)
        if field_spec["type"] == "select" and not field_spec.get("options"):
            msg = f"Field {i} with type 'select' requires 'options' list"
            raise ValueError(msg)
    return specs


class FormTemplateCreateRequest(BaseModel):
    """Pydantic request model for creating a FormTemplate."""

    title: str = Field(..., min_length=1, max_length=200, description="Form title")
    description: str | None = Field(None, description="Form description")
    instructions: str | None = Field(None, description="Instructions shown above form")
    form_schema: list[dict[str, Any]] = Field(
        ..., min_length=1, description="Form field definitions"
    )
    tags: list[str] | None = Field(None, description="Tags for categorization")

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(
        cls, v: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Validate each form field spec has required keys and valid type."""
        return validate_form_field_specs(v)


class FormTemplateUpdateRequest(BaseModel):
    """Pydantic request model for updating a FormTemplate."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    form_schema: list[dict[str, Any]] | None = None
    tags: list[str] | None = None
    status: str | None = None

    @field_validator("form_schema")
    @classmethod
    def validate_form_schema(
        cls, v: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        """Validate form_schema if provided."""
        if v is None:
            return None
        return validate_form_field_specs(v)
