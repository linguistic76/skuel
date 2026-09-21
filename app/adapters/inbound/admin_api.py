"""
Admin API Routes - User Management API
=======================================

API routes for admin-only user management operations.

All routes require ADMIN role and use the @require_admin decorator.

Routes (the target user rides as the ``uid`` query parameter, never a path segment):
- GET /api/admin/users - List all users (paginated, filterable)
- GET /api/admin/users/get?uid= - Get user details
- POST /api/admin/users/role?uid= - Change user role (body ``{"role": ...}``)
- POST /api/admin/users/deactivate?uid= - Deactivate user account (body ``{"reason": ...}``, optional)
- POST /api/admin/users/activate?uid= - Reactivate user account
- POST /api/admin/users/hard-delete?uid= - GDPR erasure (destroys user + OWNS tree)
- POST /api/admin/users/reset-password?uid= - Mint a password-reset token for a user

The three account actions (role / deactivate / activate) serve two callers through
one door each: an API client posts JSON and reads a JSON payload; the admin user
detail page posts its form (``parse_body`` reads either encoding by Content-Type)
with ``HX-Request`` and reads back the rendered account card — see
``_account_action_response``.

Security:
- All routes require authentication (401 if not logged in)
- All routes require ADMIN role (403 if insufficient permissions)
- Returns appropriate HTTP status codes

Version: 1.0.0
Date: 2025-12-06
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypedDict

from fasthtml.common import FtResponse

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_body
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories import is_not_found, refuse
from core.models.entity_requests import ChangeUserRoleRequest, DeactivateUserRequest
from core.models.enums import UserRole
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.admin.pages import account_fragment
from ui.admin.types import UserCardData
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from core.models.user.user import User
    from core.ports import GraphAuthOperations

logger = get_logger("skuel.routes.admin_api")


class AdminUserRolePayload(TypedDict):
    """JSON shape of a role change: the user's new role."""

    uid: str
    username: str
    role: str
    message: str


class AdminUserStatusPayload(TypedDict):
    """JSON shape of an activate/deactivate: the user's new active flag."""

    uid: str
    username: str
    is_active: bool
    message: str


def _account_action_response[P](
    request: Request,
    result: Result[User],
    payload: Callable[[User], P],
    toast: str,
) -> Result[P] | FtResponse:
    """The one answer shape of the three account actions.

    An HTMX request reads back what the page swaps: the rendered account card with
    the header badges out of band and the outcome as a toast header, or — for a uid
    no user has — the rendered not-found refusal at 404 (``refuse``, swapped in on
    its ``X-SKUEL-Refusal`` header). Any other failure stays a JSON ``Result``, whose
    toast headers the page's ``htmx:afterRequest`` listener surfaces while the card
    stays in place to retry. A non-HTMX caller reads the JSON payload either way.
    """
    if result.is_error:
        if request.headers.get("HX-Request") and is_not_found(result.expect_error()):
            return refuse(result.expect_error(), render_error_banner, "User")
        return Result.fail(result)
    user = result.value
    if request.headers.get("HX-Request"):
        return FtResponse(
            account_fragment(UserCardData.from_user(user)),
            headers={"X-Toast-Message": toast, "X-Toast-Type": "success"},
        )
    return Result.ok(payload(user))


def _role_payload(user: User) -> AdminUserRolePayload:
    return {
        "uid": user.uid,
        "username": user.title,
        "role": user.role.value,
        "message": f"Role updated to {user.role.value}",
    }


def _status_payload(user: User) -> AdminUserStatusPayload:
    return {
        "uid": user.uid,
        "username": user.title,
        "is_active": user.is_active,
        "message": "User account activated" if user.is_active else "User account deactivated",
    }


def create_admin_api_routes(
    app: Any,
    rt: Any,
    user_service: Any,
    graph_auth: GraphAuthOperations | None = None,
) -> None:
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

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # LIST USERS
    # ========================================================================

    @rt("/api/admin/users")
    @require_admin(get_user_service)
    @boundary_handler()
    async def list_users(
        request: Request,
        current_user: Any = None,
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
    @require_admin(get_user_service)
    @boundary_handler()
    async def get_user_details(
        request: Request,
        uid: str,
        current_user: Any = None,
    ):
        """
        Get detailed user information (ADMIN only).

        Query Parameters:
            uid: User UID to retrieve

        Returns:
            JSON object with full user details
        """
        found = require_found(await user_service.get_user(uid), "User", uid)
        if found.is_error:
            return found

        user = found.value
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
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def change_user_role(
        request: Request,
        uid: str,
        current_user: Any = None,
    ) -> Result[AdminUserRolePayload] | FtResponse:
        """
        Change a user's role (ADMIN only).

        Query Parameters:
            uid: User UID to update

        Request Body (JSON or form, by Content-Type):
            role: New role (registered, member, teacher, admin)

        Returns:
            JSON object with updated user details; the rendered account card
            to an HTMX request.
        """
        parsed = await parse_body(request, ChangeUserRoleRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        new_role_str = parsed.value.role

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
        return _account_action_response(
            request, result, _role_payload, f"Role updated to {new_role.value}"
        )

    # ========================================================================
    # DEACTIVATE USER
    # ========================================================================

    @rt("/api/admin/users/deactivate")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def deactivate_user(
        request: Request,
        uid: str,
        current_user: Any = None,
    ) -> Result[AdminUserStatusPayload] | FtResponse:
        """
        Deactivate a user account (ADMIN only).

        Query Parameters:
            uid: User UID to deactivate

        Request Body (JSON or form, optional):
            reason: Reason for deactivation

        Returns:
            JSON object with updated user details; the rendered account card
            to an HTMX request.
        """
        parsed = await parse_body(request, DeactivateUserRequest)
        if parsed.is_error:
            return Result.fail(parsed)

        result = await user_service.deactivate_user(
            target_user_uid=uid,
            admin_user_uid=current_user.uid,
            reason=parsed.value.reason,
        )
        return _account_action_response(
            request, result, _status_payload, "User account deactivated"
        )

    # ========================================================================
    # ACTIVATE USER
    # ========================================================================

    @rt("/api/admin/users/activate")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def activate_user(
        request: Request,
        uid: str,
        current_user: Any = None,
    ) -> Result[AdminUserStatusPayload] | FtResponse:
        """
        Reactivate a user account (ADMIN only).

        Query Parameters:
            uid: User UID to reactivate

        Returns:
            JSON object with updated user details; the rendered account card
            to an HTMX request.
        """
        result = await user_service.activate_user(
            target_user_uid=uid,
            admin_user_uid=current_user.uid,
        )
        return _account_action_response(request, result, _status_payload, "User account activated")

    # ========================================================================
    # HARD-DELETE USER (GDPR ERASURE)
    # ========================================================================

    @rt("/api/admin/users/hard-delete")
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def hard_delete_user(
        request: Request,
        uid: str,
        current_user: Any = None,
    ):
        """
        Hard-delete a user and every OWNS-linked entity (ADMIN only, GDPR erasure).

        Irreversible. Destroys the User node plus every owned entity (UserEntry,
        Task, Goal, Habit, ...). For routine deletions use
        POST /api/admin/users/deactivate instead — that soft-deletes, scrubs PII,
        and preserves teacher-visible history.

        Query Parameters:
            uid: User UID to erase.

        Request Body (JSON, required):
            confirm: Must be the literal string ``"erase"`` (typo guard).
            reason: Free-form justification recorded on the emitted event.

        Returns:
            JSON object with count of deleted nodes.
        """
        try:
            body = await request.json()
        except Exception:  # safety-net: HTTP error boundary — malformed JSON
            return Result.fail(
                Errors.validation(
                    "Request body must be JSON with 'confirm' and 'reason' fields",
                    field="body",
                )
            )

        confirm = body.get("confirm", "")
        reason = body.get("reason", "")

        if confirm != "erase":
            return Result.fail(
                Errors.validation(
                    "Hard-delete requires confirm='erase' to guard against typos",
                    field="confirm",
                    value=confirm,
                )
            )

        if not reason.strip():
            return Result.fail(
                Errors.validation(
                    "Hard-delete requires a non-empty reason for audit trail",
                    field="reason",
                )
            )

        result = await user_service.hard_delete_user(
            target_user_uid=uid,
            admin_user_uid=current_user.uid,
            reason=reason,
        )

        if result.is_error:
            return result

        deleted_count = result.value or 0
        logger.warning(
            f"Admin {current_user.uid} hard-deleted user {uid}: "
            f"{deleted_count} nodes erased (reason={reason!r})"
        )
        return Result.ok(
            {
                "uid": uid,
                "deleted_count": deleted_count,
                "message": f"User {uid} and {deleted_count - 1} owned entities erased",
            }
        )

    # ========================================================================
    # GENERATE PASSWORD RESET TOKEN (Admin-Initiated)
    # ========================================================================

    @rt("/api/admin/users/reset-password")
    @require_admin(get_user_service)
    @boundary_handler()
    async def generate_reset_token(
        request: Request,
        uid: str,
        current_user: Any = None,
    ):
        """
        Generate a password reset token for a user (ADMIN only).

        This is admin-initiated password reset - no email is sent.
        The admin receives the token and shares it with the user securely.

        Query Parameters:
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
            user_uid=UserUID(uid),
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

    logger.info("Admin API routes registered")


__all__ = ["create_admin_api_routes"]
