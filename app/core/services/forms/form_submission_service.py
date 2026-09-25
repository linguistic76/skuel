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
        use_default_audience: bool = False,
    ) -> Result[FormSubmission]:
        """
        Submit a form response.

        Creates the FormSubmission entity, links it to the FormTemplate
        via RESPONDS_TO_FORM, creates OWNS relationship, and optionally
        shares with groups/users.

        ``use_default_audience`` says what an *absent* audience means, which
        only the caller knows. A surface that offers audience controls (the
        submit API) leaves it False: empty there is the submitter's choice to
        stay private. A surface with no such controls (the PathStep-embedded
        form) passes True, since the submitter had no way to say "my teachers"
        and the response would otherwise reach nobody. An explicit audience
        always wins over both.

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

        # Every audience target is checked before anything is written (ADR-088):
        # a refusal fails the submit with nothing persisted, never a committed
        # submission half-shared and duplicated on retry.
        audience_check = await self._validate_audience(user_uid, group_uid, recipient_uids)
        if audience_check.is_error:
            return Result.fail(audience_check)

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
            # Sharer attribution: the Shared-With-Me inbox resolves who shared
            # an item from created_by — every SHARES_WITH writer must stamp it.
            created_by=user_uid,
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

        # Handle sharing at submit time. An explicit audience always wins. With
        # none, the default audience applies only where the caller says an
        # absent audience meant "my teachers" — teacher reads are gated on
        # these edges (Model B), so a submission that lands without them is
        # readable by nobody but its owner and admins, but auto-sharing one
        # whose submitter *chose* to leave the audience empty would publish it
        # to their whole classroom.
        if group_uid or recipient_uids or share_with_admin:
            shared = await self._share_on_submit(
                uid, user_uid, group_uid, recipient_uids, share_with_admin
            )
            if shared.is_error:
                # Validated before the write, so a refusal here is a change
                # that landed in between; the guarded writes left no
                # unauthorised edge. Take back everything this call wrote —
                # the submission and every edge on it — and say so.
                self.logger.warning(
                    f"Compensating form submission {uid} after a refused audience write: "
                    f"{shared.expect_error()}"
                )
                cleanup = await self.backend.delete(uid, cascade=True)
                if cleanup.is_error:
                    self.logger.error(
                        f"Compensation delete of {uid} failed: {cleanup.expect_error()}"
                    )
                return Result.fail(shared)
        elif use_default_audience:
            audience = await self._share_with_default_audience(uid)
            if audience.is_error:
                # Not survivable the way a partial explicit share is. The
                # default audience is the submission's *only* audience, so a
                # failed write leaves it visible to nobody — and returning
                # success would tell the learner their answer reached their
                # teacher when it reached no one. Fail loudly so they can
                # retry; the record stays (they own it, and the backfill can
                # repair it) rather than deleting work over a transient fault.
                return Result.fail(audience)

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

    async def _validate_audience(
        self,
        user_uid: UserUID,
        group_uid: str | None,
        recipient_uids: list[str] | None,
    ) -> Result[None]:
        """Check every explicit target before the first write (ADR-088 §7).

        The group must exist, be active and be one the submitter is a member
        or owner of (the same condition the feedback-request writer guards
        on); each recipient must share a group with the submitter — R8
        co-membership, through the default group only via its owner — and
        may not be the submitter. Unknown and non-co-member recipients get
        one not-found. ``share_with_admin`` is exempt (ADR-088 §7) and is not
        checked here.
        """
        if not group_uid and not recipient_uids:
            return Result.ok(None)
        if not self.sharing_service:
            return Result.fail(
                Errors.forbidden(
                    action="share form submission",
                    reason="Cannot verify the audience — sharing service unavailable.",
                )
            )
        if group_uid:
            reachable = await self.sharing_service.reachable_groups(user_uid, [group_uid])
            if reachable.is_error:
                return Result.fail(reachable)
            if group_uid not in reachable.value:
                return Result.fail(Errors.not_found(resource="Group", identifier=group_uid))
        for recipient_uid in recipient_uids or []:
            co_member = await self.sharing_service.shares_group_with(user_uid, recipient_uid)
            if co_member.is_error:
                return Result.fail(co_member)
            if not co_member.value:
                return Result.fail(Errors.not_found(resource="User", identifier=recipient_uid))
        return Result.ok(None)

    async def _share_on_submit(
        self,
        submission_uid: str,
        user_uid: UserUID,
        group_uid: str | None,
        recipient_uids: list[str] | None,
        share_with_admin: bool,
    ) -> Result[None]:
        """Write the audience via ``UnifiedSharingService``; the first refusal is the error.

        Each write re-checks its own authorisation in its statement, so a
        refusal here is never a false confirmation: it is returned, naming
        the target, and the caller decides what to take back.
        """
        if not self.sharing_service:
            if group_uid or recipient_uids or share_with_admin:
                return Result.fail(
                    Errors.forbidden(
                        action="share form submission",
                        reason="Sharing requested but no sharing service is configured.",
                    )
                )
            return Result.ok(None)

        if group_uid:
            # Every FormSubmission group target is a feedback request to the
            # group's teachers (ADR-088 §2) — never a share with its members.
            result = await self.sharing_service.submit_to_group(
                entity_uid=EntityUID(submission_uid),
                owner_uid=user_uid,
                group_uid=group_uid,
            )
            if result.is_error:
                self.logger.warning(f"Failed to submit to group {group_uid}: {result.error}")
                return Result.fail(result)

        for recipient_uid in recipient_uids or []:
            result = await self.sharing_service.share(
                entity_uid=EntityUID(submission_uid),
                owner_uid=user_uid,
                recipient_uid=recipient_uid,
            )
            if result.is_error:
                self.logger.warning(f"Failed to share with {recipient_uid}: {result.error}")
                return Result.fail(result)

        if share_with_admin:
            admin_shared = await self._share_with_admin(submission_uid, user_uid)
            if admin_shared.is_error:
                return Result.fail(admin_shared)
        return Result.ok(None)

    async def _share_with_default_audience(self, submission_uid: str) -> Result[None]:
        """Share a submission with every group the submitter studies in.

        The forms equivalent of ``AudienceResolver.resolve_default_teachers``:
        "my teachers" is expanded at write time into the concrete groups the
        submitter is a student-member of, so read access is decided by an edge
        rather than by re-deriving a relationship at read time.

        Delegates to the backend's single-statement write rather than looping
        ``share_with_group`` per group. A per-group loop can leave a submission
        holding some of its classrooms and not others, and the backfill only
        repairs submissions with *no* audience — so a half-written one would
        stay invisible to the stranded teacher forever.

        Returns the failure rather than swallowing it — the caller decides, and
        for ``submit_form`` an unaudienced submission is not a success. Note
        that a submitter in *no* group is ``Result.ok`` with nothing written:
        that is a legitimate empty audience, not a fault, and there is no
        implicit "share with everyone" fallback.

        Backend: FormSubmissionBackend.share_with_default_audience
        """
        result = await self.backend.share_with_default_audience(submission_uid)
        if result.is_error:
            self.logger.warning(
                f"Could not resolve default audience for submission {submission_uid}: "
                f"{result.expect_error()}"
            )
            return Result.fail(result)
        return Result.ok(None)

    async def _share_with_admin(self, submission_uid: str, user_uid: UserUID) -> Result[None]:
        """Share a submission with the admin user — exempt from R8 co-membership (ADR-088 §7)."""
        if not self.sharing_service:
            return Result.fail(
                Errors.forbidden(
                    action="share form submission with admin",
                    reason="Sharing requested but no sharing service is configured.",
                )
            )

        admin_result = await self.backend.find_admin_user_uid(UserRole.ADMIN)
        if admin_result.is_error:
            return Result.fail(admin_result)
        admin_uid = admin_result.value
        if not admin_uid:
            return Result.fail(Errors.not_found(resource="User", identifier="admin"))
        result = await self.sharing_service.share(
            entity_uid=EntityUID(submission_uid),
            owner_uid=user_uid,
            recipient_uid=admin_uid,
            require_co_membership=False,
        )
        if result.is_error:
            self.logger.warning(f"Failed to share with admin: {result.error}")
            return Result.fail(result)
        return Result.ok(None)

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

    async def verify_teacher_access(self, uid: str, teacher_uid: str) -> Result[bool]:
        """Verify a teacher may read one submission (Model B gate).

        Authority is carried by the submission's own feedback request: it must
        be ``SUBMITTED_TO_GROUP`` an active group the teacher owns (ADR-088
        §2). Sharing a classroom with the *submitter* is deliberately not
        enough — a student may belong to several groups, and a submission
        sent to one teacher's group is not thereby readable by another's. A
        person share (``SHARES_WITH``) is a share, never a review grant: a
        teacher named as a recipient gets nothing here (R3, R5).

        Returns a ``forbidden`` error on refusal so callers can tell a denial
        apart from an infrastructure fault. Mirrors
        ``TeacherReviewService.verify_teacher_authority``'s error contract.

        Backend: FormSubmissionBackend.verify_teacher_submission_access
        """
        result = await self.backend.verify_teacher_submission_access(uid, teacher_uid)
        if result.is_error:
            return Result.fail(result)

        if not result.value:
            return Result.fail(
                Errors.forbidden(
                    action="read form submission",
                    reason=(
                        f"Submission {uid} is not submitted to any active group "
                        f"owned by teacher {teacher_uid}"
                    ),
                )
            )

        return Result.ok(True)

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
        """Share an existing submission (post-submit).

        Every target is validated before the first edge (ADR-088 §7); a
        refused write afterwards is returned as the error. The writes are
        idempotent MERGEs, so a retry after a refusal duplicates nothing.
        """
        # Verify ownership
        get_result = await self.get_submission(uid, user_uid)
        if get_result.is_error:
            return Result.fail(get_result)

        audience_check = await self._validate_audience(user_uid, group_uid, recipient_uids)
        if audience_check.is_error:
            return Result.fail(audience_check)

        shared = await self._share_on_submit(
            uid, user_uid, group_uid, recipient_uids, share_with_admin
        )
        if shared.is_error:
            return Result.fail(shared)
        return Result.ok(True)
