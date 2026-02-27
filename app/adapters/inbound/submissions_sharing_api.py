"""
Report Sharing API Routes
==============================

REST API for report sharing, visibility control, and access management.

Routes:
- POST /api/submissions/share - Share report with user
- POST /api/submissions/unshare - Revoke sharing
- POST /api/submissions/set-visibility - Set visibility level
- GET /api/submissions/shared-with-me - Get reports shared with current user
- GET /api/submissions/shared-users - Get users report is shared with
- GET /api/submissions/public - Browse public reports (portfolio showcase)

See: /docs/patterns/SHARING_PATTERNS.md (to be created)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.submission_protocols import (
        SubmissionOperations,
        SubmissionSharingOperations,
    )

from pydantic import BaseModel
from starlette.requests import Request

from adapters.inbound.auth import UserUID, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from core.models.enums.metadata_enums import Visibility
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.submissions.sharing")


# ============================================================================
# REQUEST MODELS
# ============================================================================


class ShareReportRequest(BaseModel):
    """Request to share a report with a user."""

    report_uid: str
    recipient_uid: str
    role: str = "viewer"  # Role: teacher, peer, mentor, viewer


class UnshareReportRequest(BaseModel):
    """Request to revoke sharing access."""

    report_uid: str
    recipient_uid: str


class SetVisibilityRequest(BaseModel):
    """Request to set report visibility."""

    report_uid: str
    visibility: str  # private, shared, public


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_submissions_sharing_api_routes(
    _app: Any,
    rt: Any,
    sharing_service: "SubmissionSharingOperations",
    core_service: "SubmissionOperations | None" = None,
) -> list[Any]:
    """
    Create all report sharing API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        sharing_service: ReportSharingService instance
        core_service: Optional SubmissionsCoreService for additional operations

    Returns:
        List of route handlers
    """

    @rt("/api/submissions/share", methods=["POST"])
    @boundary_handler(success_status=200)
    async def share_report(
        request: Request,
        body: ShareReportRequest,
    ) -> Result[dict[str, Any]]:
        """
        Share a report with a specific user.

        Creates SHARES_WITH relationship and notifies recipient.
        Only completed reports can be shared.

        Request body:
            {
                "report_uid": "report_abc123",
                "recipient_uid": "user_teacher",
                "role": "teacher"  // Optional: teacher, peer, mentor, viewer
            }

        Returns:
            {"success": true, "message": "Report shared successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.share_report(
            ku_uid=body.report_uid,
            owner_uid=user_uid,
            recipient_uid=body.recipient_uid,
            role=body.role,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "message": f"Report shared with {body.recipient_uid}",
            }
        )

    @rt("/api/submissions/unshare", methods=["POST"])
    @boundary_handler(success_status=200)
    async def unshare_report(
        request: Request,
        body: UnshareReportRequest,
    ) -> Result[dict[str, Any]]:
        """
        Revoke sharing access for a user.

        Deletes SHARES_WITH relationship.

        Request body:
            {
                "report_uid": "report_abc123",
                "recipient_uid": "user_teacher"
            }

        Returns:
            {"success": true, "message": "Sharing revoked successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.unshare_report(
            ku_uid=body.report_uid,
            owner_uid=user_uid,
            recipient_uid=body.recipient_uid,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "message": f"Sharing revoked for {body.recipient_uid}",
            }
        )

    @rt("/api/submissions/set-visibility", methods=["POST"])
    @boundary_handler(success_status=200)
    async def set_visibility(
        request: Request,
        body: SetVisibilityRequest,
    ) -> Result[dict[str, Any]]:
        """
        Set report visibility level.

        Only completed reports can be made SHARED or PUBLIC.

        Request body:
            {
                "report_uid": "report_abc123",
                "visibility": "public"  // private, shared, public
            }

        Returns:
            {"success": true, "visibility": "public"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Validate visibility value
        try:
            visibility = Visibility(body.visibility)
        except ValueError:
            return Result.fail(
                {
                    "error": "validation",
                    "message": f"Invalid visibility value: {body.visibility}",
                }
            )

        result = await sharing_service.set_visibility(
            ku_uid=body.report_uid,
            owner_uid=user_uid,
            visibility=visibility,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "visibility": body.visibility,
            }
        )

    @rt("/api/submissions/shared-with-me")
    @boundary_handler(success_status=200)
    async def get_shared_with_me(request: Request) -> Result[dict[str, Any]]:
        """
        Get reports shared with current user.

        Query params:
            limit: Maximum reports to return (default: 50)

        Returns:
            {
                "reports": [ReportDTO, ...],
                "count": 5
            }
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Parse query params
        params = dict(request.query_params)
        limit = int(params.get("limit", 50))

        result = await sharing_service.get_reports_shared_with_me(
            user_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result)

        reports = result.value

        return Result.ok(
            {
                "reports": [
                    {
                        "uid": a.uid,
                        "user_uid": a.user_uid,
                        "original_filename": a.original_filename,
                        "report_type": a.report_type,
                        "status": a.status,
                        "processed_content": a.processed_content,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                        "visibility": a.visibility,
                        # Sharing metadata
                        "shared_role": getattr(a, "shared_role", None),
                        "shared_at": getattr(a, "shared_at", None),
                    }
                    for a in reports
                ],
                "count": len(reports),
            }
        )

    @rt("/api/submissions/shared-users")
    @boundary_handler(success_status=200)
    async def get_shared_users(request: Request) -> Result[dict[str, Any]]:
        """
        Get list of users a report is shared with.

        Query params:
            uid: Report UID

        Returns:
            {
                "users": [
                    {
                        "user_uid": "user_teacher",
                        "user_name": "Teacher Name",
                        "role": "teacher",
                        "shared_at": "2026-02-02T12:00:00"
                    },
                    ...
                ],
                "count": 2
            }
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Parse query params
        params = dict(request.query_params)
        report_uid = params.get("uid")

        if not report_uid:
            return Result.fail(
                {
                    "error": "validation",
                    "message": "Missing required parameter: uid",
                }
            )

        # Verify ownership (only owner can see who report is shared with)
        if core_service:
            report_result = await core_service.get_report(report_uid)
            if report_result.is_error:
                return Result.fail(report_result)

            report = report_result.value
            if report.user_uid != user_uid:
                return Result.fail(
                    {
                        "error": "forbidden",
                        "message": "You do not own this report",
                    }
                )

        result = await sharing_service.get_shared_with_users(
            ku_uid=report_uid,
        )

        if result.is_error:
            return Result.fail(result)

        users = result.value

        return Result.ok(
            {
                "users": users,
                "count": len(users),
            }
        )

    @rt("/api/submissions/public")
    @boundary_handler(success_status=200)
    async def get_public_reports(request: Request) -> Result[dict[str, Any]]:
        """
        Browse public reports (portfolio showcase).

        Query params:
            user_uid: Optional filter by owner
            limit: Maximum reports to return (default: 50)

        Returns:
            {
                "reports": [ReportDTO, ...],
                "count": 10
            }
        """
        # No auth required - public content

        # Parse query params
        params = dict(request.query_params)
        filter_user_uid = params.get("user_uid")
        limit = int(params.get("limit", 50))

        # Query public reports
        # Note: This uses the core service's search capabilities
        # We filter by visibility=public
        if not core_service:
            return Result.fail(
                {
                    "error": "system",
                    "message": "Core service not available",
                }
            )

        # Use BaseService search - note: visibility filtering would need to be done post-query
        # or via a custom method since BaseService.search doesn't support filters parameter
        search_result = await core_service.search(
            query="",  # Empty query = all
            limit=limit,
        )

        if search_result.is_error:
            return Result.fail(search_result)

        reports = search_result.value

        # Filter by user if specified
        if filter_user_uid:
            reports = [a for a in reports if a.user_uid == filter_user_uid]

        return Result.ok(
            {
                "reports": [
                    {
                        "uid": a.uid,
                        "user_uid": a.user_uid,
                        "original_filename": a.original_filename,
                        "report_type": a.report_type,
                        "status": a.status,
                        "processed_content": a.processed_content,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                        "visibility": a.visibility,
                    }
                    for a in reports
                ],
                "count": len(reports),
            }
        )

    # Return route handlers
    return [
        share_report,
        unshare_report,
        set_visibility,
        get_shared_with_me,
        get_shared_users,
        get_public_reports,
    ]
