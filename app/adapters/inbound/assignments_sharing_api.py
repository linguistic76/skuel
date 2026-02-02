"""
Assignment Sharing API Routes
==============================

REST API for assignment sharing, visibility control, and access management.

Routes:
- POST /api/assignments/share - Share assignment with user
- POST /api/assignments/unshare - Revoke sharing
- POST /api/assignments/set-visibility - Set visibility level
- GET /api/assignments/shared-with-me - Get assignments shared with current user
- GET /api/assignments/shared-users - Get users assignment is shared with
- GET /api/assignments/public - Browse public assignments (portfolio showcase)

See: /docs/patterns/SHARING_PATTERNS.md (to be created)
"""

from typing import Any

from pydantic import BaseModel
from starlette.requests import Request

from core.auth import UserUID, require_authenticated_user
from core.models.enums.metadata_enums import Visibility
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.assignments.sharing")


# ============================================================================
# REQUEST MODELS
# ============================================================================


class ShareAssignmentRequest(BaseModel):
    """Request to share an assignment with a user."""

    assignment_uid: str
    recipient_uid: str
    role: str = "viewer"  # Role: teacher, peer, mentor, viewer


class UnshareAssignmentRequest(BaseModel):
    """Request to revoke sharing access."""

    assignment_uid: str
    recipient_uid: str


class SetVisibilityRequest(BaseModel):
    """Request to set assignment visibility."""

    assignment_uid: str
    visibility: str  # private, shared, public


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_assignments_sharing_api_routes(
    _app,
    rt,
    sharing_service,
    core_service=None,
):
    """
    Create all assignment sharing API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        sharing_service: AssignmentSharingService instance
        core_service: Optional AssignmentsCoreService for additional operations

    Returns:
        List of route handlers
    """

    @rt("/api/assignments/share", methods=["POST"])
    @boundary_handler(success_status=200)
    async def share_assignment(
        request: Request,
        body: ShareAssignmentRequest,
    ) -> Result[dict[str, Any]]:
        """
        Share an assignment with a specific user.

        Creates SHARES_WITH relationship and notifies recipient.
        Only completed assignments can be shared.

        Request body:
            {
                "assignment_uid": "assignment_abc123",
                "recipient_uid": "user_teacher",
                "role": "teacher"  // Optional: teacher, peer, mentor, viewer
            }

        Returns:
            {"success": true, "message": "Assignment shared successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.share_assignment(
            assignment_uid=body.assignment_uid,
            owner_uid=user_uid,
            recipient_uid=body.recipient_uid,
            role=body.role,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "success": True,
                "message": f"Assignment shared with {body.recipient_uid}",
            }
        )

    @rt("/api/assignments/unshare", methods=["POST"])
    @boundary_handler(success_status=200)
    async def unshare_assignment(
        request: Request,
        body: UnshareAssignmentRequest,
    ) -> Result[dict[str, Any]]:
        """
        Revoke sharing access for a user.

        Deletes SHARES_WITH relationship.

        Request body:
            {
                "assignment_uid": "assignment_abc123",
                "recipient_uid": "user_teacher"
            }

        Returns:
            {"success": true, "message": "Sharing revoked successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.unshare_assignment(
            assignment_uid=body.assignment_uid,
            owner_uid=user_uid,
            recipient_uid=body.recipient_uid,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "success": True,
                "message": f"Sharing revoked for {body.recipient_uid}",
            }
        )

    @rt("/api/assignments/set-visibility", methods=["POST"])
    @boundary_handler(success_status=200)
    async def set_visibility(
        request: Request,
        body: SetVisibilityRequest,
    ) -> Result[dict[str, Any]]:
        """
        Set assignment visibility level.

        Only completed assignments can be made SHARED or PUBLIC.

        Request body:
            {
                "assignment_uid": "assignment_abc123",
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
            assignment_uid=body.assignment_uid,
            owner_uid=user_uid,
            visibility=visibility,
        )

        if result.is_error:
            return result

        return Result.ok(
            {
                "success": True,
                "visibility": body.visibility,
            }
        )

    @rt("/api/assignments/shared-with-me")
    @boundary_handler(success_status=200)
    async def get_shared_with_me(request: Request) -> Result[dict[str, Any]]:
        """
        Get assignments shared with current user.

        Query params:
            limit: Maximum assignments to return (default: 50)

        Returns:
            {
                "assignments": [AssignmentDTO, ...],
                "count": 5
            }
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Parse query params
        params = dict(request.query_params)
        limit = int(params.get("limit", 50))

        result = await sharing_service.get_assignments_shared_with_me(
            user_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return result

        assignments = result.value

        return Result.ok(
            {
                "assignments": [
                    {
                        "uid": a.uid,
                        "user_uid": a.user_uid,
                        "original_filename": a.original_filename,
                        "assignment_type": a.assignment_type,
                        "status": a.status,
                        "processed_content": a.processed_content,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                        "visibility": a.visibility,
                        # Sharing metadata
                        "shared_role": getattr(a, "shared_role", None),
                        "shared_at": getattr(a, "shared_at", None),
                    }
                    for a in assignments
                ],
                "count": len(assignments),
            }
        )

    @rt("/api/assignments/shared-users")
    @boundary_handler(success_status=200)
    async def get_shared_users(request: Request) -> Result[dict[str, Any]]:
        """
        Get list of users an assignment is shared with.

        Query params:
            uid: Assignment UID

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
        assignment_uid = params.get("uid")

        if not assignment_uid:
            return Result.fail(
                {
                    "error": "validation",
                    "message": "Missing required parameter: uid",
                }
            )

        # Verify ownership (only owner can see who assignment is shared with)
        if core_service:
            assignment_result = await core_service.get_assignment(assignment_uid)
            if assignment_result.is_error:
                return assignment_result

            assignment = assignment_result.value
            if assignment.user_uid != user_uid:
                return Result.fail(
                    {
                        "error": "forbidden",
                        "message": "You do not own this assignment",
                    }
                )

        result = await sharing_service.get_shared_with_users(
            assignment_uid=assignment_uid,
        )

        if result.is_error:
            return result

        users = result.value

        return Result.ok(
            {
                "users": users,
                "count": len(users),
            }
        )

    @rt("/api/assignments/public")
    @boundary_handler(success_status=200)
    async def get_public_assignments(request: Request) -> Result[dict[str, Any]]:
        """
        Browse public assignments (portfolio showcase).

        Query params:
            user_uid: Optional filter by owner
            limit: Maximum assignments to return (default: 50)

        Returns:
            {
                "assignments": [AssignmentDTO, ...],
                "count": 10
            }
        """
        # No auth required - public content

        # Parse query params
        params = dict(request.query_params)
        filter_user_uid = params.get("user_uid")
        limit = int(params.get("limit", 50))

        # Query public assignments
        # Note: This uses the core service's search capabilities
        # We filter by visibility=public
        if not core_service:
            return Result.fail(
                {
                    "error": "system",
                    "message": "Core service not available",
                }
            )

        # Use BaseService search with visibility filter
        search_result = await core_service.search(
            query_text="",  # Empty query = all
            limit=limit,
            filters={"visibility": "public"},
        )

        if search_result.is_error:
            return search_result

        assignments = search_result.value

        # Filter by user if specified
        if filter_user_uid:
            assignments = [a for a in assignments if a.user_uid == filter_user_uid]

        return Result.ok(
            {
                "assignments": [
                    {
                        "uid": a.uid,
                        "user_uid": a.user_uid,
                        "original_filename": a.original_filename,
                        "assignment_type": a.assignment_type,
                        "status": a.status,
                        "processed_content": a.processed_content,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                        "visibility": a.visibility,
                    }
                    for a in assignments
                ],
                "count": len(assignments),
            }
        )

    # Return route handlers
    return [
        share_assignment,
        unshare_assignment,
        set_visibility,
        get_shared_with_me,
        get_shared_users,
        get_public_assignments,
    ]
