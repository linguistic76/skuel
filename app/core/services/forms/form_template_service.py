"""
FormTemplate Service
====================

CRUD + article linking for admin-created form templates.
FormTemplates are shared content (no user_uid).
"""

from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.form_events import (
    FormTemplateCreated,
    FormTemplateDeleted,
    FormTemplateUpdated,
)
from core.models.enums.entity_enums import EntityType
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_dto import FormTemplateDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class FormTemplateService(BaseService):
    """
    CRUD service for FormTemplates (general-purpose form definitions).

    FormTemplates are shared content created by admins. They define form_schema
    (field specs) that get rendered as inline forms in Articles.
    """

    _config = DomainConfig(
        dto_class=FormTemplateDTO,
        model_class=FormTemplate,
        entity_label="Entity",
        search_fields=("title", "instructions"),
        search_order_by="created_at",
    )

    def __init__(self, backend: Any, event_bus: Any | None = None) -> None:
        """Initialize with backend and optional event bus."""
        super().__init__(backend, "form_templates")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger
        logger.info("FormTemplateService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for FormTemplate entities."""
        return "Entity"

    # ========================================================================
    # CREATE
    # ========================================================================

    async def create_form_template(
        self,
        title: str,
        form_schema: list[dict[str, Any]],
        description: str | None = None,
        instructions: str | None = None,
        tags: list[str] | None = None,
    ) -> Result[FormTemplate]:
        """Create a new FormTemplate."""
        uid = UIDGenerator.generate_uid("ft", title)

        form_template = FormTemplate(
            uid=uid,
            title=title,
            entity_type=EntityType.FORM_TEMPLATE,
            description=description,
            form_schema=tuple(form_schema),
            instructions=instructions,
            tags=tuple(tags) if tags else (),
        )

        result = await self.backend.create(form_template)
        if result.is_error:
            self.logger.error(f"Failed to create form template: {result.error}")
            return result

        await publish_event(
            self.event_bus,
            FormTemplateCreated(
                template_uid=uid,
                title=title,
                field_count=len(form_schema),
                occurred_at=datetime.now(),
            ),
            self.logger,
        )

        return Result.ok(form_template)

    # ========================================================================
    # READ
    # ========================================================================

    async def get_form_template(self, uid: str) -> Result[FormTemplate]:
        """Get a FormTemplate by UID."""
        result: Result[FormTemplate | None] = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        if result.value is None:
            return Result.fail(Errors.not_found(resource="FormTemplate", identifier=uid))
        return Result.ok(result.value)

    async def list_form_templates(self, limit: int = 50) -> Result[list[FormTemplate]]:
        """List all form templates."""
        result = await self.backend.list(limit=limit)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(result.value or [])

    # ========================================================================
    # UPDATE
    # ========================================================================

    async def update_form_template(
        self,
        uid: str,
        title: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        form_schema: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
    ) -> Result[FormTemplate]:
        """Update a FormTemplate."""
        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if instructions is not None:
            updates["instructions"] = instructions
        if form_schema is not None:
            updates["form_schema"] = form_schema
        if tags is not None:
            updates["tags"] = tags
        if status is not None:
            updates["status"] = status

        if not updates:
            return await self.get_form_template(uid)

        result = await self.backend.update(uid, updates)
        if result.is_error:
            return Result.fail(result.expect_error())

        await publish_event(
            self.event_bus,
            FormTemplateUpdated(
                template_uid=uid,
                occurred_at=datetime.now(),
            ),
            self.logger,
        )

        return await self.get_form_template(uid)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_form_template(self, uid: str) -> Result[bool]:
        """
        Delete a FormTemplate.

        Guard: Cannot delete if submissions exist (RESPONDS_TO_FORM relationships).
        Admins must delete submissions first, ensuring data integrity.
        """
        # Check for existing submissions
        submission_count = await self._get_submission_count(uid)
        if submission_count > 0:
            return Result.fail(
                Errors.business(
                    rule="template_has_submissions",
                    message=(
                        f"Cannot delete template with {submission_count} existing submission(s). "
                        "Delete submissions first."
                    ),
                )
            )

        # cascade=True to remove EMBEDS_FORM relationships
        result = await self.backend.delete(uid, cascade=True)
        if result.is_error:
            return Result.fail(result.expect_error())

        await publish_event(
            self.event_bus,
            FormTemplateDeleted(
                template_uid=uid,
                occurred_at=datetime.now(),
            ),
            self.logger,
        )

        return Result.ok(True)

    async def _get_submission_count(self, template_uid: str) -> int:
        """Count submissions linked to a template via RESPONDS_TO_FORM."""
        result = await self.backend.execute_query(
            f"""
            MATCH (fs:Entity)-[:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft:Entity {{uid: $uid}})
            RETURN count(fs) as count
            """,
            {"uid": template_uid},
        )
        if result.is_error or not result.value:
            return 0
        return result.value[0].get("count", 0)

    # ========================================================================
    # ARTICLE LINKING
    # ========================================================================

    async def link_to_article(self, form_template_uid: str, article_uid: str) -> Result[bool]:
        """Link a FormTemplate to an Article via EMBEDS_FORM."""
        return await self.backend.link_to_article(form_template_uid, article_uid)

    async def unlink_from_article(self, form_template_uid: str, article_uid: str) -> Result[bool]:
        """Remove EMBEDS_FORM link between FormTemplate and Article."""
        return await self.backend.unlink_from_article(form_template_uid, article_uid)

    async def get_for_article(self, article_uid: str) -> Result[list[dict[str, Any]]]:
        """Get all FormTemplates embedded in an article."""
        return await self.backend.get_forms_for_article(article_uid)
