"""
FormSubmission Service
======================

Submit, list, delete, and share user form responses.
FormSubmissions are user-owned content linked to FormTemplates.
"""

from datetime import datetime
from typing import Any

from core.events import publish_event
from core.events.form_events import FormSubmissionDeleted, FormSubmitted
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.user_enums import UserRole
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_submission_dto import FormSubmissionDTO
from core.models.forms.form_template import FormTemplate
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.ports.form_protocols import FormSubmissionBackendOperations, FormTemplateOperations
from core.ports.infrastructure_protocols import EventBusOperations
from core.ports.sharing_protocols import SharingOperations
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.services.forms.form_content import build_form_processed_content
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class FormSubmissionService(BaseService[FormSubmissionBackendOperations, FormSubmission]):
    """
    Service for FormSubmissions (user responses to FormTemplates).

    FormSubmissions are user-owned. Users can submit, view their own,
    and delete their own submissions. Sharing uses UnifiedSharingService.
    """

    _config = DomainConfig(
        dto_class=FormSubmissionDTO,
        model_class=FormSubmission,
        entity_label="Entity",
        search_fields=("title", "processed_content"),
        search_order_by="created_at",
        user_ownership_relationship=RelationshipName.OWNS,
    )

    def __init__(
        self,
        backend: FormSubmissionBackendOperations,
        form_template_service: FormTemplateOperations,
        event_bus: EventBusOperations | None = None,
        sharing_service: SharingOperations | None = None,
    ) -> None:
        """Initialize with backend and required template service."""
        super().__init__(backend, "form_submissions")
        self.backend = backend
        self.form_template_service = form_template_service
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.logger = logger  # type: ignore[assignment]  # structlog BoundLogger
        logger.info("FormSubmissionService initialized")

    # ========================================================================
    # SUBMIT
    # ========================================================================

    async def submit_form(
        self,
        user_uid: UserUID,
        form_template_uid: str,
        form_data: dict[str, Any],
        title: str | None = None,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[FormSubmission]:
        """
        Submit a form response.

        Creates the FormSubmission entity, links it to the FormTemplate
        via RESPONDS_TO_FORM, creates OWNS relationship, and optionally
        shares with groups/users.

        Validates that:
        1. The FormTemplate exists
        2. The form_data conforms to the template's form_schema
        """
        # Fetch full template for validation (not just existence check)
        template_result = await self._get_template(form_template_uid)
        if template_result.is_error:
            return Result.fail(template_result)
        template = template_result.value

        # Validate form_data against template schema
        validation_errors = template.validate_response(form_data)
        if validation_errors:
            return Result.fail(
                Errors.validation(
                    f"Form response validation failed: {'; '.join(validation_errors)}",
                    field="form_data",
                )
            )

        display_title = title or f"Form Response ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        uid = UIDGenerator.generate_uid("fs", display_title)

        schema_hash = template.schema_hash()
        processed_content = build_form_processed_content(
            template_title=template.title,
            template_uid=form_template_uid,
            schema=template.form_schema,
            form_data=form_data,
        )

        submission = FormSubmission(
            uid=uid,
            title=display_title,
            entity_type=EntityType.FORM_SUBMISSION,
            user_uid=user_uid,
            form_template_uid=form_template_uid,
            form_data=form_data,
            processed_content=processed_content,
            template_schema_hash=schema_hash,
            status=EntityStatus.COMPLETED,
        )

        # Atomically create node + OWNS + RESPONDS_TO_FORM in one query
        result = await self.backend.create_with_relationships(
            submission, user_uid, form_template_uid
        )
        if result.is_error:
            self.logger.error(f"Failed to create form submission: {result.error}")
            return result

        # Handle sharing at submit time
        await self._share_on_submit(uid, user_uid, group_uid, recipient_uids, share_with_admin)

        # Publish event
        await publish_event(
            self.event_bus,
            FormSubmitted(
                submission_uid=uid,
                user_uid=user_uid,
                template_uid=form_template_uid,
            ),
            self.logger,
        )

        return Result.ok(submission)

    async def _get_template(self, form_template_uid: str) -> Result[FormTemplate]:
        """Fetch a FormTemplate via the template service."""
        result = await self.form_template_service.get(form_template_uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found("FormTemplate", form_template_uid))
        return Result.ok(result.value)

    async def _share_on_submit(
        self,
        submission_uid: str,
        user_uid: UserUID,
        group_uid: str | None,
        recipient_uids: list[str] | None,
        share_with_admin: bool,
    ) -> None:
        """Handle optional sharing at submit time via UnifiedSharingService."""
        if not self.sharing_service:
            if group_uid or recipient_uids or share_with_admin:
                self.logger.warning("Sharing requested but no sharing_service configured")
            return

        if group_uid:
            result = await self.sharing_service.share_with_group(
                entity_uid=EntityUID(submission_uid),
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                self.logger.warning(f"Failed to share with group {group_uid}: {result.error}")

        if recipient_uids:
            for recipient_uid in recipient_uids:
                result = await self.sharing_service.share(
                    entity_uid=EntityUID(submission_uid),
                    owner_uid=user_uid,
                    recipient_uid=recipient_uid,
                )
                if result.is_error:
                    self.logger.warning(f"Failed to share with {recipient_uid}: {result.error}")

        if share_with_admin:
            await self._share_with_admin(submission_uid, user_uid)

    async def _share_with_admin(self, submission_uid: str, user_uid: UserUID) -> None:
        """Share a submission with the admin user (using UserRole enum)."""
        if not self.sharing_service:
            self.logger.warning("share_with_admin called but no sharing_service configured")
            return

        admin_result = await self.backend.find_admin_user_uid(UserRole.ADMIN)
        if admin_result.is_ok and admin_result.value:
            admin_uid = admin_result.value
            result = await self.sharing_service.share(
                entity_uid=EntityUID(submission_uid),
                owner_uid=user_uid,
                recipient_uid=admin_uid,
            )
            if result.is_error:
                self.logger.warning(f"Failed to share with admin: {result.error}")
        else:
            self.logger.warning("share_with_admin requested but no admin user found")

    # ========================================================================
    # READ
    # ========================================================================

    async def get_submission(self, uid: str, user_uid: UserUID) -> Result[FormSubmission]:
        """Get a FormSubmission by UID, verifying ownership."""
        result: Result[FormSubmission | None] = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))
        # Ownership check — return 404 (not 403) per SKUEL pattern
        if result.value.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))
        return Result.ok(result.value)

    async def get_my_submissions(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[dict[str, Any]]]:
        """Get a user's form submissions."""
        return await self.backend.list_by_user(user_uid, limit=limit)

    # ========================================================================
    # ADMIN / TEACHER READ
    # ========================================================================

    async def get_submissions_for_template(
        self, form_template_uid: str, teacher_uid: UserUID | None
    ) -> Result[list[dict[str, Any]]]:
        """Submissions for a template, restricted to the caller's classrooms.

        Rows carry the submitter's identity and answers, so `teacher_uid` is
        required rather than defaulted: passing `None` grants a cross-classroom
        read and is reserved for ADMIN callers. A teacher UID yields only
        submissions authored by students in an active Group that teacher owns —
        the same authority the submission detail page checks per row.

        Backend: FormSubmissionBackend.get_submissions_for_template
        """
        return await self.backend.get_submissions_for_template(form_template_uid, teacher_uid)

    async def get_submission_admin(self, uid: str) -> Result[FormSubmission]:
        """Get submission by UID without ownership check (admin/teacher use)."""
        result: Result[FormSubmission | None] = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))
        return Result.ok(result.value)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_submission(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Delete a user's form submission (ownership-verified)."""
        # Verify ownership first
        get_result = await self.get_submission(uid, user_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        # cascade=True to remove OWNS + RESPONDS_TO_FORM relationships
        result = await self.backend.delete(uid, cascade=True)
        if result.is_error:
            return Result.fail(result)

        # Publish event
        await publish_event(
            self.event_bus,
            FormSubmissionDeleted(
                submission_uid=uid,
                user_uid=user_uid,
            ),
            self.logger,
        )

        return Result.ok(True)

    # ========================================================================
    # SHARING (post-submit)
    # ========================================================================

    async def share_submission(
        self,
        uid: str,
        user_uid: UserUID,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[bool]:
        """Share an existing submission (post-submit)."""
        # Verify ownership
        get_result = await self.get_submission(uid, user_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        await self._share_on_submit(uid, user_uid, group_uid, recipient_uids, share_with_admin)
        return Result.ok(True)
