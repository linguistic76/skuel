"""
FormSubmission Service
======================

Submit, list, delete, and share user form responses.
FormSubmissions are user-owned content linked to FormTemplates.
"""

from datetime import datetime
from typing import Any

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.forms.form_submission import FormSubmission
from core.models.forms.form_submission_dto import FormSubmissionDTO
from core.models.relationship_names import RelationshipName
from core.services.base_service import BaseService
from core.services.domain_config import DomainConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger(__name__)


class FormSubmissionService(BaseService):
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
        backend: Any,
        event_bus: Any | None = None,
        sharing_service: Any | None = None,
    ) -> None:
        """Initialize with backend, optional event bus, and sharing service."""
        super().__init__(backend, "form_submissions")
        self.backend = backend
        self.event_bus = event_bus
        self.sharing_service = sharing_service
        self.logger = logger
        logger.info("FormSubmissionService initialized")

    @property
    def entity_label(self) -> str:
        """Return the graph label for FormSubmission entities."""
        return "Entity"

    # ========================================================================
    # SUBMIT
    # ========================================================================

    async def submit_form(
        self,
        user_uid: str,
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
        shares with groups/users/admin.
        """
        display_title = title or f"Form Response ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        uid = UIDGenerator.generate_uid("fs", display_title)

        # Build processed_content for search/embedding
        processed_content = "\n".join(
            f"{k}: {v}" for k, v in form_data.items() if v
        )

        submission = FormSubmission(
            uid=uid,
            title=display_title,
            entity_type=EntityType.FORM_SUBMISSION,
            user_uid=user_uid,
            form_template_uid=form_template_uid,
            form_data=form_data,
            processed_content=processed_content,
            status=EntityStatus.COMPLETED,
        )

        # Create entity
        result = await self.backend.create(submission)
        if result.is_error:
            self.logger.error(f"Failed to create form submission: {result.error}")
            return result

        # Create OWNS relationship
        owns_result = await self.backend.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (fs:Entity {{uid: $fs_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(fs)
            RETURN true as success
            """,
            {"user_uid": user_uid, "fs_uid": uid},
        )
        if owns_result.is_error:
            self.logger.warning(f"Failed to create OWNS relationship: {owns_result.error}")

        # Create RESPONDS_TO_FORM relationship
        link_result = await self.backend.execute_query(
            f"""
            MATCH (fs:Entity {{uid: $fs_uid}})
            MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
            MERGE (fs)-[r:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"fs_uid": uid, "ft_uid": form_template_uid},
        )
        if link_result.is_error:
            self.logger.warning(f"Failed to create RESPONDS_TO_FORM: {link_result.error}")

        # Handle sharing at submit time
        await self._share_on_submit(uid, user_uid, group_uid, recipient_uids, share_with_admin)

        return Result.ok(submission)

    async def _share_on_submit(
        self,
        submission_uid: str,
        user_uid: str,
        group_uid: str | None,
        recipient_uids: list[str] | None,
        share_with_admin: bool,
    ) -> None:
        """Handle optional sharing at submit time via UnifiedSharingService."""
        if not self.sharing_service:
            return

        if group_uid:
            await self.sharing_service.share_with_group(
                entity_uid=submission_uid,
                group_uid=group_uid,
                shared_by=user_uid,
            )

        if recipient_uids:
            for recipient_uid in recipient_uids:
                await self.sharing_service.share(
                    entity_uid=submission_uid,
                    owner_uid=user_uid,
                    target_uid=recipient_uid,
                )

        if share_with_admin:
            # Share with admin role — uses the admin sharing pattern
            await self.sharing_service.share_with_admin(
                entity_uid=submission_uid,
                shared_by=user_uid,
            )

    # ========================================================================
    # READ
    # ========================================================================

    async def get_submission(self, uid: str, user_uid: str) -> Result[FormSubmission]:
        """Get a FormSubmission by UID, verifying ownership."""
        result: Result[FormSubmission | None] = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        if result.value is None:
            return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))
        # Ownership check — return 404 (not 403) per SKUEL pattern
        if result.value.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))
        return Result.ok(result.value)

    async def get_my_submissions(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[dict[str, Any]]]:
        """Get a user's form submissions."""
        return await self.backend.list_by_user(user_uid, limit=limit)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete_submission(self, uid: str, user_uid: str) -> Result[bool]:
        """Delete a user's form submission (ownership-verified)."""
        # Verify ownership first
        get_result = await self.get_submission(uid, user_uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        result = await self.backend.delete(uid)
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(True)

    # ========================================================================
    # SHARING (post-submit)
    # ========================================================================

    async def share_submission(
        self,
        uid: str,
        user_uid: str,
        group_uid: str | None = None,
        recipient_uids: list[str] | None = None,
        share_with_admin: bool = False,
    ) -> Result[bool]:
        """Share an existing submission (post-submit)."""
        # Verify ownership
        get_result = await self.get_submission(uid, user_uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        await self._share_on_submit(uid, user_uid, group_uid, recipient_uids, share_with_admin)
        return Result.ok(True)
