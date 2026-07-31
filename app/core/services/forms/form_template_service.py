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
from core.models.type_hints import UserUID
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

        A count that cannot be read refuses the delete. The guard is fail-safe:
        uncertainty about whether submissions exist is not permission to destroy
        them.

        Note: Uses override (not _post_delete hook) because the submission guard
        must run BEFORE the delete, not after.
        """
        count_result = await self._get_submission_count(uid)
        if count_result.is_error:
            # Propagate the fault rather than dressing it as the business rule.
            # "Delete the submissions first" would send an admin after work that
            # may not exist, and the advice would never resolve.
            self.logger.error(
                f"Refusing to delete template {uid}: submission count unavailable "
                f"({count_result.expect_error().message})"
            )
            return Result.fail(count_result)

        submission_count = count_result.value
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

    async def count_submissions(
        self, template_uid: str, teacher_uid: UserUID | None
    ) -> Result[int]:
        """Count submissions linked to a template, as one caller may read them.

        `teacher_uid` is required rather than defaulted so no caller silently
        publishes a cross-classroom total: `None` counts every classroom and is
        reserved for ADMIN, a teacher UID counts only what that teacher may open.

        Backend: FormTemplateBackend.count_submissions
        """
        return await self.backend.count_submissions(template_uid, teacher_uid)

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    async def _get_submission_count(self, template_uid: str) -> Result[int]:
        """Count every submission answering a template, for the deletion guard.

        Deliberately unscoped: this guards deletion, so it must see submissions
        the deleting caller may not read. Scoping it to a teacher would report 0
        for another classroom's work and let the template be deleted out from
        under it.

        Returns the failure rather than a number when the count cannot be read.
        A count is the guard's whole evidence, so collapsing an error to 0 here
        would reach `delete` as a genuine "nobody has answered this".

        Backend: FormTemplateBackend.count_submissions
        """
        return await self.backend.count_submissions(template_uid, teacher_uid=None)

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
