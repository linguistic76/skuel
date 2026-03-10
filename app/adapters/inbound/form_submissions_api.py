"""
Form Submissions API - User Routes
====================================

User-facing routes for submitting, viewing, and sharing form responses.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.forms.form_submission_request import FormSubmissionCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.forms.form_submission_service import FormSubmissionService

logger = get_logger(__name__)


def create_form_submissions_api_routes(
    app: Any,
    rt: Any,
    form_submission_service: "FormSubmissionService",
    user_service: Any = None,
) -> list[Any]:
    """Create form submission API routes (authenticated users)."""

    # ========================================================================
    # SUBMIT
    # ========================================================================

    @rt("/api/form-submissions/submit", methods=["POST"])
    @boundary_handler(success_status=201)
    async def submit_form(request: Request) -> Result[Any]:
        """Submit a form response."""
        user_uid = require_authenticated_user(request)

        try:
            body = await request.json()
            req = FormSubmissionCreateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        return await form_submission_service.submit_form(
            user_uid=user_uid,
            form_template_uid=req.form_template_uid,
            form_data=req.form_data,
            title=req.title,
            group_uid=req.group_uid,
            recipient_uids=req.recipient_uids,
            share_with_admin=req.share_with_admin,
        )

    # ========================================================================
    # READ
    # ========================================================================

    @rt("/api/form-submissions", methods=["GET"])
    @boundary_handler()
    async def list_my_submissions(request: Request) -> Result[Any]:
        """List the authenticated user's form submissions."""
        user_uid = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", "50"))
        return await form_submission_service.get_my_submissions(user_uid, limit=limit)

    @rt("/api/form-submissions/get", methods=["GET"])
    @boundary_handler()
    async def get_form_submission(request: Request) -> Result[Any]:
        """Get a form submission by UID (ownership-verified)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await form_submission_service.get_submission(uid, user_uid)

    # ========================================================================
    # DELETE
    # ========================================================================

    @rt("/api/form-submissions/delete", methods=["DELETE"])
    @boundary_handler()
    async def delete_form_submission(request: Request) -> Result[Any]:
        """Delete a user's form submission (ownership-verified)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))
        return await form_submission_service.delete_submission(uid, user_uid)

    # ========================================================================
    # SHARE (post-submit)
    # ========================================================================

    @rt("/api/form-submissions/share", methods=["POST"])
    @boundary_handler()
    async def share_form_submission(request: Request) -> Result[Any]:
        """Share an existing form submission with groups/users/admin."""
        user_uid = require_authenticated_user(request)

        try:
            body = await request.json()
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid request body: {e}", field="body"))

        uid = body.get("uid")
        if not uid:
            return Result.fail(Errors.validation("uid is required", field="uid"))

        return await form_submission_service.share_submission(
            uid=uid,
            user_uid=user_uid,
            group_uid=body.get("group_uid"),
            recipient_uids=body.get("recipient_uids"),
            share_with_admin=body.get("share_with_admin", False),
        )

    return []
