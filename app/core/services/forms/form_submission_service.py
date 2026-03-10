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
        shares with groups/users.

        Validates that the FormTemplate exists before creating anything.
        """
        # Verify template exists before creating submission
        template_check = await self.backend.execute_query(
            """
            MATCH (ft:Entity {uid: $ft_uid, entity_type: 'form_template'})
            RETURN ft.uid as uid
            """,
            {"ft_uid": form_template_uid},
        )
        if template_check.is_error:
            return Result.fail(Errors.database(operation="submit_form", message=str(template_check.error)))
        if not template_check.value:
            return Result.fail(Errors.not_found(resource="FormTemplate", identifier=form_template_uid))

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

        # Create entity via backend (proper DTO serialization for all fields)
        result = await self.backend.create(submission)
        if result.is_error:
            self.logger.error(f"Failed to create form submission: {result.error}")
            return result

        # Create OWNS + RESPONDS_TO_FORM relationships
        # Template existence already verified above, so these should succeed
        rel_result = await self.backend.execute_query(
            f"""
            MATCH (fs:Entity {{uid: $fs_uid}})
            MATCH (u:User {{uid: $user_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(fs)
            WITH fs
            MATCH (ft:Entity {{uid: $ft_uid, entity_type: 'form_template'}})
            MERGE (fs)-[r:{RelationshipName.RESPONDS_TO_FORM.value}]->(ft)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"fs_uid": uid, "user_uid": user_uid, "ft_uid": form_template_uid},
        )
        if rel_result.is_error:
            self.logger.error(f"Failed to create submission relationships: {rel_result.error}")

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
            if group_uid or recipient_uids or share_with_admin:
                self.logger.warning("Sharing requested but no sharing_service configured")
            return

        if group_uid:
            result = await self.sharing_service.share_with_group(
                entity_uid=submission_uid,
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                self.logger.warning(f"Failed to share with group {group_uid}: {result.error}")

        if recipient_uids:
            for recipient_uid in recipient_uids:
                result = await self.sharing_service.share(
                    entity_uid=submission_uid,
                    owner_uid=user_uid,
                    target_uid=recipient_uid,
                )
                if result.is_error:
                    self.logger.warning(f"Failed to share with {recipient_uid}: {result.error}")

        if share_with_admin:
            # Share with admin by looking up admin user and sharing directly
            admin_result = await self.backend.execute_query(
                """
                MATCH (u:User) WHERE u.role = 'admin' OR u.role = 'ADMIN'
                RETURN u.uid as uid LIMIT 1
                """,
                {},
            )
            if admin_result.is_ok and admin_result.value:
                admin_uid = admin_result.value[0]["uid"]
                result = await self.sharing_service.share(
                    entity_uid=submission_uid,
                    owner_uid=user_uid,
                    target_uid=admin_uid,
                )
                if result.is_error:
                    self.logger.warning(f"Failed to share with admin: {result.error}")
            else:
                self.logger.warning("share_with_admin requested but no admin user found")

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

        # cascade=True to remove OWNS + RESPONDS_TO_FORM relationships
        result = await self.backend.delete(uid, cascade=True)
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
