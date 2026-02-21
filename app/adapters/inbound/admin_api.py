"""
Admin API Routes - User Management API
=======================================

API routes for admin-only user management operations.

All routes require ADMIN role and use the @require_admin decorator.

Routes:
- GET /api/admin/users - List all users (paginated, filterable)
- GET /api/admin/users/{uid} - Get user details
- POST /api/admin/users/{uid}/role - Change user role
- POST /api/admin/users/{uid}/deactivate - Deactivate user account
- POST /api/admin/users/{uid}/activate - Reactivate user account

Security:
- All routes require authentication (401 if not logged in)
- All routes require ADMIN role (403 if insufficient permissions)
- Returns appropriate HTTP status codes

Version: 1.0.0
Date: 2025-12-06
"""

from typing import TYPE_CHECKING, Any

from starlette.requests import Request

from adapters.inbound.boundary import boundary_handler
from core.auth import require_admin
from core.models.enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import GraphAuthOperations

logger = get_logger("skuel.routes.admin_api")


def create_admin_api_routes(
    app: Any,
    rt: Any,
    user_service: Any,
    graph_auth: "GraphAuthOperations | None" = None,
) -> list[Any]:
    """
    Create admin API routes for user management.

    All routes require ADMIN role.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        user_service: UserService instance
        graph_auth: Optional graph authentication service

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    # Named function to replace lambda (SKUEL012 compliance)
    def get_user_service_instance():
        """Get user service instance (deferred access for decorator)."""
        return user_service

    # ========================================================================
    # LIST USERS
    # ========================================================================

    @rt("/api/admin/users")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def list_users(
        request: Request,
        current_user: Any,
        limit: int = 100,
        offset: int = 0,
        role: str | None = None,
        active_only: bool = True,
    ):
        """
        List all users (ADMIN only).

        Query Parameters:
            limit: Maximum number of users to return (default: 100)
            offset: Pagination offset (default: 0)
            role: Filter by role (registered, member, teacher, admin)
            active_only: Only return active users (default: true)

        Returns:
            JSON array of user objects
        """
        # Parse role filter if provided
        role_filter = UserRole.from_string(role) if role else None

        result = await user_service.list_users(
            admin_user_uid=current_user.uid,
            limit=limit,
            offset=offset,
            role_filter=role_filter,
            active_only=active_only,
        )

        if result.is_error:
            return result

        # Convert users to JSON-serializable format
        users = result.value or []
        return Result.ok(
            [
                {
                    "uid": u.uid,
                    "username": u.title,
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": u.role.value,
                    "is_active": u.is_active,
                    "is_verified": u.is_verified,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                }
                for u in users
            ]
        )

    # ========================================================================
    # GET USER DETAILS
    # ========================================================================

    @rt("/api/admin/users/get")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def get_user_details(
        request: Request,
        current_user: Any,
        uid: str,
    ):
        """
        Get detailed user information (ADMIN only).

        Path Parameters:
            uid: User UID to retrieve

        Returns:
            JSON object with full user details
        """
        result = await user_service.get_user(uid)

        if result.is_error:
            return result

        if not result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=uid))

        user = result.value
        return Result.ok(
            {
                "uid": user.uid,
                "username": user.title,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role.value,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "is_premium": user.is_premium,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
                "preferences": {
                    "learning_level": user.preferences.learning_level.value,
                    "theme": user.preferences.theme,
                    "timezone": user.preferences.timezone,
                },
            }
        )

    # ========================================================================
    # CHANGE USER ROLE
    # ========================================================================

    @rt("/api/admin/users/role")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def change_user_role(
        request: Request,
        current_user: Any,
        uid: str,
    ):
        """
        Change a user's role (ADMIN only).

        Path Parameters:
            uid: User UID to update

        Request Body (JSON):
            role: New role (registered, member, teacher, admin)

        Returns:
            JSON object with updated user details
        """
        try:
            body = await request.json()
        except Exception:
            return Result.fail(Errors.validation(message="Invalid JSON body", field="body"))

        new_role_str = body.get("role")
        if not new_role_str:
            return Result.fail(Errors.validation(message="Missing 'role' field", field="role"))

        new_role = UserRole.from_string(new_role_str)
        if not new_role:
            return Result.fail(
                Errors.validation(
                    message=f"Invalid role: {new_role_str}. "
                    f"Valid roles: registered, member, teacher, admin",
                    field="role",
                    value=new_role_str,
                )
            )

        result = await user_service.update_role(
            target_user_uid=uid,
            new_role=new_role,
            admin_user_uid=current_user.uid,
        )

        if result.is_error:
            return result

        user = result.value
        return Result.ok(
            {
                "uid": user.uid,
                "username": user.title,
                "role": user.role.value,
                "message": f"Role updated to {user.role.value}",
            }
        )

    # ========================================================================
    # DEACTIVATE USER
    # ========================================================================

    @rt("/api/admin/users/deactivate")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def deactivate_user(
        request: Request,
        current_user: Any,
        uid: str,
    ):
        """
        Deactivate a user account (ADMIN only).

        Path Parameters:
            uid: User UID to deactivate

        Request Body (JSON, optional):
            reason: Reason for deactivation

        Returns:
            JSON object with updated user details
        """
        reason = ""
        try:
            body = await request.json()
            reason = body.get("reason", "")
        except Exception:
            # Body is optional for deactivation
            pass

        result = await user_service.deactivate_user(
            target_user_uid=uid,
            admin_user_uid=current_user.uid,
            reason=reason,
        )

        if result.is_error:
            return result

        user = result.value
        return Result.ok(
            {
                "uid": user.uid,
                "username": user.title,
                "is_active": user.is_active,
                "message": "User account deactivated",
            }
        )

    # ========================================================================
    # ACTIVATE USER
    # ========================================================================

    @rt("/api/admin/users/activate")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def activate_user(
        request: Request,
        current_user: Any,
        uid: str,
    ):
        """
        Reactivate a user account (ADMIN only).

        Path Parameters:
            uid: User UID to reactivate

        Returns:
            JSON object with updated user details
        """
        result = await user_service.activate_user(
            target_user_uid=uid,
            admin_user_uid=current_user.uid,
        )

        if result.is_error:
            return result

        user = result.value
        return Result.ok(
            {
                "uid": user.uid,
                "username": user.title,
                "is_active": user.is_active,
                "message": "User account activated",
            }
        )

    # ========================================================================
    # GENERATE PASSWORD RESET TOKEN (Admin-Initiated)
    # ========================================================================

    @rt("/api/admin/users/reset-password")
    @require_admin(get_user_service_instance)
    @boundary_handler()
    async def generate_reset_token(
        request: Request,
        current_user: Any,
        uid: str,
    ):
        """
        Generate a password reset token for a user (ADMIN only).

        This is admin-initiated password reset - no email is sent.
        The admin receives the token and shares it with the user securely.

        Path Parameters:
            uid: User UID to generate reset token for

        Returns:
            JSON object with reset token and instructions
        """
        # Check if graph_auth is available
        if not graph_auth:
            return Result.fail(
                Errors.system(
                    message="Authentication service unavailable",
                    service="graph_auth",
                )
            )

        # Get client info for audit trail
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        result = await graph_auth.admin_generate_reset_token(
            user_uid=uid,
            admin_uid=current_user.uid,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if result.is_error:
            return result

        token = result.value
        return Result.ok(
            {
                "user_uid": uid,
                "reset_token": token,
                "expires_in": "1 hour",
                "instructions": (
                    "Share this token with the user securely. "
                    "They can use it at /reset-password to set a new password. "
                    "The token expires in 1 hour."
                ),
            }
        )

    # Collect all routes
    routes.extend(
        [
            list_users,
            get_user_details,
            change_user_role,
            deactivate_user,
            activate_user,
            generate_reset_token,
        ]
    )

    logger.info(f"Admin API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_admin_api_routes"]
