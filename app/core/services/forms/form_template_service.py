"""
FormTemplate Service
====================

CRUD + PathStep linking for admin-created form templates.
FormTemplates are shared content (no user_uid).

Implements CRUDOperations via BaseService inheritance (CrudOperationsMixin).
Uses _post_create/_post_update hooks for event publishing.
Overrides delete for pre-delete submission guard.
"""

from collections.abc import Mapping
from typing import Any

from core.events import publish_event
from core.events.form_events import (
    FormTemplateCreated,
    FormTemplateDeleted,
    FormTemplateUpdated,
)
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_dto import FormTemplateDTO
from core.ports.form_protocols import FormTemplateBackendOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class FormTemplateService(BaseService[FormTemplateBackendOperations, FormTemplate]):
    """
    CRUD service for FormTemplates (general-purpose form definitions).

    FormTemplates are shared content created by admins. They define form_schema
    (field specs) that get rendered as inline forms in PathSteps.

    Inherits CRUDOperations from CrudOperationsMixin (via BaseService):
    create, get, update, delete, list, get_for_user, update_for_user, delete_for_user.

    Uses _post_create/_post_update hooks for event publishing.
    Overrides delete for pre-delete submission guard.
    """

    _config = DomainConfig(
        dto_class=FormTemplateDTO,
        model_class=FormTemplate,
        entity_label="Entity",
        search_fields=("title", "instructions"),
        search_order_by="created_at",
    )

    def __init__(
        self, backend: FormTemplateBackendOperations, event_bus: EventBusOperations | None = None
    ) -> None:
        """Initialize with backend and optional event bus."""
        super().__init__(backend, "form_templates")
        self.backend = backend
        self.event_bus = event_bus
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("FormTemplateService initialized")

    # ========================================================================
    # LIFECYCLE HOOKS (event publishing)
    # ========================================================================

    async def _post_create(self, entity: FormTemplate, result: Result[FormTemplate]) -> None:
        """Publish FormTemplateCreated event after successful creation."""
        if result.is_error:
            self.logger.error(f"Failed to create form template: {result.error}")
            return

        schema_len = len(entity.form_schema) if entity.form_schema else 0
        await publish_event(
            self.event_bus,
            FormTemplateCreated(
                template_uid=entity.uid,
                title=entity.title,
                field_count=schema_len,
            ),
            self.logger,
        )

    async def _post_update(
        self,
        uid: str,
        old_entity: FormTemplate,
        updates: Mapping[str, Any],
        result: Result[FormTemplate],
    ) -> None:
        """Publish FormTemplateUpdated event after successful update."""
        if result.is_error:
            return

        await publish_event(
            self.event_bus,
            FormTemplateUpdated(
                template_uid=uid,
            ),
            self.logger,
        )

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        Delete a FormTemplate.

        Guard: Cannot delete if submissions exist (RESPONDS_TO_FORM relationships).
        Admins must delete submissions first, ensuring data integrity.
        Always cascades to remove EMBEDS_FORM relationships.

        Note: Uses override (not _post_delete hook) because the submission guard
        must run BEFORE the delete, not after.
        """
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

        result = await self.backend.delete(uid, cascade=True)
        if result.is_error:
            return Result.fail(result)

        await publish_event(
            self.event_bus,
            FormTemplateDeleted(
                template_uid=uid,
            ),
            self.logger,
        )

        return Result.ok(True)

    # ========================================================================
    # ADMIN / TEACHER READ
    # ========================================================================

    async def count_submissions(self, template_uid: str) -> Result[int]:
        """Count submissions linked to a template."""
        return await self.backend.count_submissions(template_uid)

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    async def _get_submission_count(self, template_uid: str) -> int:
        """Count submissions linked to a template via RESPONDS_TO_FORM."""
        result = await self.backend.count_submissions(template_uid)
        if result.is_error:
            return 0
        return result.value

    # ========================================================================
    # PATH STEP LINKING (domain-specific, not part of CRUDOperations)
    # ========================================================================

    async def get_forms_for_path_step(self, ps_uid: str) -> Result[list[FormTemplate]]:
        """Return all FormTemplates embedded in a PathStep via EMBEDS_FORM."""
        return await self.backend.get_forms_for_path_step(ps_uid)

    async def link_to_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Link a FormTemplate to a PathStep via EMBEDS_FORM."""
        return await self.backend.link_to_path_step(form_template_uid, ps_uid)

    async def unlink_from_path_step(self, form_template_uid: str, ps_uid: str) -> Result[bool]:
        """Remove EMBEDS_FORM link between FormTemplate and PathStep."""
        return await self.backend.unlink_from_path_step(form_template_uid, ps_uid)
