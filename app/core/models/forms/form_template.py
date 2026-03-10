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
