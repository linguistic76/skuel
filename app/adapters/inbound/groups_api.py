"""
Groups API Routes
==================

API endpoints for group management (teacher-student classes).

TEACHER role required for group creation and management.
Members (students) can view their groups and group members.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.boundary import boundary_handler
from core.auth import require_authenticated_user
from core.auth.roles import UserRole, require_role
from core.models.group.group_request import (
    GroupCreateRequest,
    GroupMemberRequest,
    GroupUpdateRequest,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import GroupOperations

logger = get_logger(__name__)


def create_groups_api_routes(
    app: Any,
    rt: Any,
    group_service: "GroupOperations",
    user_service: Any,
) -> list[Any]:
    """
    Create group API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        group_service: GroupService instance
        user_service: UserService for role checks
    """

    def get_user_service() -> Any:
        return user_service

    # ========================================================================
    # CRUD ROUTES (Teacher-only for create/update/delete)
    # ========================================================================

    @rt("/api/groups/create", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler(success_status=201)
    async def create_group(request: Request, current_user: Any) -> Result[Any]:
        """Create a new group. TEACHER+ required."""
        body = await request.json()
        req = GroupCreateRequest(**body)

        return await group_service.create_group(
            teacher_uid=current_user.uid,
            name=req.name,
            description=req.description,
            max_members=req.max_members,
        )

    @rt("/api/groups/get", methods=["GET"])
    @boundary_handler()
    async def get_group(request: Request) -> Result[Any]:
        """Get a group by UID. Accessible to owner and members."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation("Group UID is required", field="uid"))

        result = await group_service.get_group(uid)
        if result.is_error or not result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        return result

    @rt("/api/groups/update", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def update_group(request: Request, current_user: Any) -> Result[Any]:
        """Update a group. Owner only."""
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation("Group UID is required", field="uid"))

        # Verify ownership
        group_result = await group_service.get_group(uid)
        if group_result.is_error or not group_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        if group_result.value.owner_uid != current_user.uid:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        body = await request.json()
        req = GroupUpdateRequest(**body)

        return await group_service.update_group(
            uid=uid,
            name=req.name,
            description=req.description,
            max_members=req.max_members,
            is_active=req.is_active,
        )

    @rt("/api/groups/delete", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def delete_group(request: Request, current_user: Any) -> Result[Any]:
        """Delete a group. Owner only."""
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation("Group UID is required", field="uid"))

        # Verify ownership
        group_result = await group_service.get_group(uid)
        if group_result.is_error or not group_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        if group_result.value.owner_uid != current_user.uid:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        return await group_service.delete_group(uid)

    # ========================================================================
    # LIST ROUTES
    # ========================================================================

    @rt("/api/groups/list", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def list_groups(request: Request, current_user: Any) -> Result[Any]:
        """List teacher's groups. TEACHER+ required."""
        return await group_service.list_teacher_groups(current_user.uid)

    @rt("/api/groups/mine", methods=["GET"])
    @boundary_handler()
    async def my_groups(request: Request) -> Result[Any]:
        """List groups the current user is a member of."""
        user_uid = require_authenticated_user(request)
        return await group_service.get_user_groups(user_uid)

    # ========================================================================
    # MEMBERSHIP ROUTES (Owner-only for add/remove)
    # ========================================================================

    @rt("/api/groups/{uid}/members/add", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def add_member(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Add a member to a group. Owner only."""
        # Verify ownership
        group_result = await group_service.get_group(uid)
        if group_result.is_error or not group_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        if group_result.value.owner_uid != current_user.uid:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        body = await request.json()
        req = GroupMemberRequest(**body)

        return await group_service.add_member(
            group_uid=uid,
            user_uid=req.user_uid,
            role=req.role,
        )

    @rt("/api/groups/{uid}/members/remove", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def remove_member(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Remove a member from a group. Owner only."""
        # Verify ownership
        group_result = await group_service.get_group(uid)
        if group_result.is_error or not group_result.value:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))
        if group_result.value.owner_uid != current_user.uid:
            return Result.fail(Errors.not_found(resource="Group", identifier=uid))

        body = await request.json()
        req = GroupMemberRequest(**body)

        return await group_service.remove_member(
            group_uid=uid,
            user_uid=req.user_uid,
        )

    @rt("/api/groups/{uid}/members", methods=["GET"])
    @boundary_handler()
    async def list_members(request: Request, uid: str) -> Result[Any]:
        """List group members. Accessible to owner and members."""
        require_authenticated_user(request)
        return await group_service.get_members(uid)

    logger.info("✅ Groups API routes registered")
    return []
