"""
Submission Sharing API Routes
==============================

REST API for submission sharing, visibility control, and access management.

Routes:
- POST /api/submissions/share - Share submission with user
- POST /api/submissions/unshare - Revoke sharing
- POST /api/submissions/set-visibility - Set visibility level
- GET /api/submissions/shared-with-me - Get submissions shared with current user
- GET /api/submissions/shared-users - Get users submission is shared with
- GET /api/submissions/public - Browse public submissions (portfolio showcase)

See: /docs/patterns/SHARING_PATTERNS.md (to be created)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.sharing_protocols import SharingOperations
    from core.ports.submission_protocols import SubmissionOperations

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


class ShareSubmissionRequest(BaseModel):
    """Request to share a submission with a user."""

    submission_uid: str
    recipient_uid: str
    role: str = "viewer"  # Role: teacher, peer, mentor, viewer


class UnshareSubmissionRequest(BaseModel):
    """Request to revoke sharing access."""

    submission_uid: str
    recipient_uid: str


class SetVisibilityRequest(BaseModel):
    """Request to set submission visibility."""

    submission_uid: str
    visibility: str  # private, shared, public


class ShareWithGroupRequest(BaseModel):
    """Request to share an entity with a group."""

    entity_uid: str
    group_uid: str
    share_version: str = "original"


class UnshareFromGroupRequest(BaseModel):
    """Request to revoke group-level sharing."""

    entity_uid: str
    group_uid: str


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_submissions_sharing_api_routes(
    _app: Any,
    rt: Any,
    sharing_service: "SharingOperations",
    core_service: "SubmissionOperations | None" = None,
) -> list[Any]:
    """
    Create all submission sharing API routes.

    Args:
        _app: FastHTML app instance
        rt: Route decorator
        sharing_service: UnifiedSharingService instance
        core_service: Optional SubmissionsCoreService for additional operations

    Returns:
        List of route handlers
    """

    @rt("/api/submissions/share", methods=["POST"])
    @boundary_handler(success_status=200)
    async def share_submission(
        request: Request,
        body: ShareSubmissionRequest,
    ) -> Result[dict[str, Any]]:
        """
        Share a submission with a specific user.

        Creates SHARES_WITH relationship and notifies recipient.
        Only completed submissions can be shared.

        Request body:
            {
                "submission_uid": "submission_abc123",
                "recipient_uid": "user_teacher",
                "role": "teacher"  // Optional: teacher, peer, mentor, viewer
            }

        Returns:
            {"success": true, "message": "Submission shared successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.share(
            entity_uid=body.submission_uid,
            owner_uid=user_uid,
            recipient_uid=body.recipient_uid,
            role=body.role,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "message": f"Submission shared with {body.recipient_uid}",
            }
        )

    @rt("/api/submissions/unshare", methods=["POST"])
    @boundary_handler(success_status=200)
    async def unshare_submission(
        request: Request,
        body: UnshareSubmissionRequest,
    ) -> Result[dict[str, Any]]:
        """
        Revoke sharing access for a user.

        Deletes SHARES_WITH relationship.

        Request body:
            {
                "submission_uid": "submission_abc123",
                "recipient_uid": "user_teacher"
            }

        Returns:
            {"success": true, "message": "Sharing revoked successfully"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.unshare(
            entity_uid=body.submission_uid,
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
        Set submission visibility level.

        Only completed submissions can be made SHARED or PUBLIC.

        Request body:
            {
                "submission_uid": "submission_abc123",
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
            entity_uid=body.submission_uid,
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
        Get submissions shared with current user.

        Query params:
            limit: Maximum submissions to return (default: 50)

        Returns:
            {
                "submissions": [SubmissionDTO, ...],
                "count": 5
            }
        """
        user_uid: UserUID = require_authenticated_user(request)

        # Parse query params
        params = dict(request.query_params)
        limit = int(params.get("limit", 50))

        result = await sharing_service.get_shared_with_me(
            user_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result)

        submissions = result.value

        return Result.ok(
            {
                "submissions": [
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
                    for a in submissions
                ],
                "count": len(submissions),
            }
        )

    @rt("/api/submissions/shared-users")
    @boundary_handler(success_status=200)
    async def get_shared_users(request: Request) -> Result[dict[str, Any]]:
        """
        Get list of users a submission is shared with.

        Query params:
            uid: Submission UID

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
        submission_uid = params.get("uid")

        if not submission_uid:
            return Result.fail(
                {
                    "error": "validation",
                    "message": "Missing required parameter: uid",
                }
            )

        # Verify ownership (only owner can see who submission is shared with)
        if core_service:
            submission_result = await core_service.get_submission(submission_uid)
            if submission_result.is_error:
                return Result.fail(submission_result)

            submission = submission_result.value
            if submission is None or submission.user_uid != user_uid:
                return Result.fail(
                    {
                        "error": "forbidden",
                        "message": "You do not own this submission",
                    }
                )

        result = await sharing_service.get_shared_with(
            entity_uid=submission_uid,
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
        Browse public submissions (portfolio showcase).

        Query params:
            user_uid: Optional filter by owner
            limit: Maximum submissions to return (default: 50)

        Returns:
            {
                "submissions": [SubmissionDTO, ...],
                "count": 10
            }
        """
        # No auth required - public content

        # Parse query params
        params = dict(request.query_params)
        filter_user_uid = params.get("user_uid")
        limit = int(params.get("limit", 50))

        # Query public submissions
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

        submissions = search_result.value

        # Filter by user if specified
        if filter_user_uid:
            submissions = [a for a in submissions if a.user_uid == filter_user_uid]

        return Result.ok(
            {
                "submissions": [
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
                    for a in submissions
                ],
                "count": len(submissions),
            }
        )

    @rt("/api/share/group", methods=["POST"])
    @boundary_handler(success_status=200)
    async def share_with_group(
        request: Request,
        body: ShareWithGroupRequest,
    ) -> Result[dict[str, Any]]:
        """
        Share an entity with all members of a group.

        Creates a SHARED_WITH_GROUP relationship from the entity to the group.
        All group members gain access when entity visibility is SHARED.

        Request body:
            {
                "entity_uid": "task_abc123",
                "group_uid": "group_xyz789",
                "share_version": "original"  // Optional
            }

        Returns:
            {"success": true, "message": "Shared with group group_xyz789"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.share_with_group(
            entity_uid=body.entity_uid,
            owner_uid=user_uid,
            group_uid=body.group_uid,
            share_version=body.share_version,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "message": f"Shared with group {body.group_uid}",
            }
        )

    @rt("/api/share/ungroup", methods=["POST"])
    @boundary_handler(success_status=200)
    async def unshare_from_group(
        request: Request,
        body: UnshareFromGroupRequest,
    ) -> Result[dict[str, Any]]:
        """
        Revoke group-level access to an entity.

        Deletes the SHARED_WITH_GROUP relationship. Direct SHARES_WITH
        relationships are not affected.

        Request body:
            {
                "entity_uid": "task_abc123",
                "group_uid": "group_xyz789"
            }

        Returns:
            {"success": true, "message": "Group sharing revoked"}
        """
        user_uid: UserUID = require_authenticated_user(request)

        result = await sharing_service.unshare_from_group(
            entity_uid=body.entity_uid,
            owner_uid=user_uid,
            group_uid=body.group_uid,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "success": True,
                "message": f"Group sharing revoked for {body.group_uid}",
            }
        )

    @rt("/api/shared-with-me/groups")
    @boundary_handler(success_status=200)
    async def get_shared_via_groups(request: Request) -> Result[dict[str, Any]]:
        """
        Get entities shared with current user through group membership.

        Returns entities where user is a member of a group that has
        SHARED_WITH_GROUP access. Excludes user's own entities.

        Query params:
            limit: Maximum entities to return (default: 50)

        Returns:
            {
                "entities": [
                    {
                        "entity": {...},
                        "group_uid": "group_xyz789",
                        "group_name": "Physics 101",
                        "share_version": "original",
                        "shared_at": "2026-03-01T12:00:00"
                    },
                    ...
                ],
                "count": 3
            }
        """
        user_uid: UserUID = require_authenticated_user(request)

        params = dict(request.query_params)
        limit = int(params.get("limit", 50))

        result = await sharing_service.get_shared_with_me_via_groups(
            user_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result)

        entities = result.value

        return Result.ok(
            {
                "entities": entities,
                "count": len(entities),
            }
        )

    # Return route handlers
    return [
        share_submission,
        unshare_submission,
        set_visibility,
        get_shared_with_me,
        get_shared_users,
        get_public_reports,
        share_with_group,
        unshare_from_group,
        get_shared_via_groups,
    ]
