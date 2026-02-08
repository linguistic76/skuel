"""
Role-Based Access Control for SKUEL
====================================

Decorators and helpers for role-based route protection.

Design Principles:
- Fail-fast: Missing role = immediate 403
- Hierarchy-aware: ADMIN has all permissions
- Consistent with existing @require_auth pattern
- Returns appropriate HTTP status codes

Role Hierarchy:
    REGISTERED < MEMBER < TEACHER < ADMIN

Each role inherits permissions from lower roles.

IMPORTANT - Two Authentication Patterns:
=========================================

SKUEL uses two authentication patterns in routes, each for different purposes:

Pattern 1: Role Decorators → `current_user: User` (full entity)
---------------------------------------------------------------
Role decorators (@require_admin, @require_teacher, etc.) inject the FULL User
entity as `current_user` into kwargs. This is needed because role checking
requires fetching the user from the database anyway.

    ```python
    @rt("/api/admin/users")
    @require_admin(get_user_service)
    async def list_users(request, current_user):
        # current_user is the FULL User entity (has .uid, .role, .email, etc.)
        admin_uid = current_user.uid
        admin_role = current_user.role
    ```

Pattern 2: Direct Auth → `user_uid: str` (just the identifier)
--------------------------------------------------------------
Most API routes extract user_uid directly via require_authenticated_user().
This is more efficient when you only need the identifier (no DB fetch).

    ```python
    from core.auth import require_authenticated_user


    @rt("/api/tasks")
    async def list_tasks(request):
        # user_uid is just the string identifier (e.g., "user.mike")
        user_uid = require_authenticated_user(request)
        tasks = await service.list_tasks(user_uid=user_uid)
    ```

When to Use Which:
- Role-protected routes: Use @require_admin/@require_teacher → `current_user`
- Standard API routes: Use require_authenticated_user() → `user_uid`
- UI routes (optional auth): Use get_current_user_or_default() → `user_uid`

See also: /docs/patterns/AUTH_PATTERNS.md for complete documentation.

Usage:
    ```python
    from core.auth import require_role, require_admin, require_teacher
    from core.models.enums import UserRole


    # Define service getter (SKUEL012: no lambdas)
    def get_user_service():
        return services.user_service


    # Require specific role
    @rt("/api/admin/users")
    @require_role(UserRole.ADMIN, get_user_service)
    async def list_users(request, current_user): ...


    # Shortcut for admin-only routes
    @rt("/api/admin/users/{uid}/role")
    @require_admin(get_user_service)
    async def change_role(request, current_user): ...


    # Shortcut for teacher-only routes
    @rt("/api/ku")
    @require_teacher(get_user_service)
    async def create_ku(request, current_user): ...
    ```
"""

import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any

from starlette.exceptions import HTTPException
from starlette.requests import Request

from core.auth.session import get_current_user, require_authenticated_user
from core.models.enums import UserRole
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.auth.roles")


# ============================================================================
# ROLE CHECKING HELPERS
# ============================================================================


async def get_user_role(request: Request, user_service: Any) -> UserRole | None:
    """
    Get the role of the currently authenticated user.

    Args:
        request: Starlette request object
        user_service: UserService instance

    Returns:
        UserRole if user exists, None otherwise
    """
    user_uid = get_current_user(request)
    if not user_uid:
        return None

    result = await user_service.get_user(user_uid)
    if result.is_error or not result.value:
        return None

    return result.value.role


async def is_current_user_admin(request: Request, user_service: Any) -> bool:
    """
    Check if the current user has admin role.

    Useful for conditional UI rendering (e.g., showing Admin Dashboard in navbar).

    Args:
        request: Starlette request object
        user_service: UserService instance

    Returns:
        True if user is authenticated and has ADMIN role, False otherwise

    Usage:
        ```python
        is_admin = await is_current_user_admin(request, services.user_service)
        navbar = create_navbar(
            current_user=user_uid, is_authenticated=True, is_admin=is_admin
        )
        ```
    """
    role = await get_user_role(request, user_service)
    if role is None:
        return False
    return role.has_permission(UserRole.ADMIN)


def check_role_permission(user: Any, required_role: UserRole) -> Result[bool]:
    """
    Service-level role permission check.

    Returns Result for consistent error handling pattern.

    Args:
        user: User entity
        required_role: Required role level

    Returns:
        Result[True] if permitted, Result.fail if not
    """
    if not user:
        return Result.fail(Errors.not_found(resource="User", identifier="current"))

    if not user.has_permission(required_role):
        return Result.fail(
            Errors.business(
                rule="role_permission",
                message=f"Requires {required_role.value} role or higher",
            )
        )

    return Result.ok(True)


# ============================================================================
# ROLE-BASED ROUTE DECORATORS
# ============================================================================


def require_role(required_role: UserRole, user_service_getter: Callable[[], Any]):
    """
    Decorator to require a specific role (or higher) for a route.

    Uses hierarchy-aware permission checking.
    Injects `current_user` into kwargs for convenience.

    Args:
        required_role: Minimum required role
        user_service_getter: Function that returns the UserService

    Usage:
        ```python
        def get_user_service():
            return services.user_service


        @rt("/api/admin/users")
        @require_role(UserRole.ADMIN, get_user_service)
        async def list_all_users(request, current_user):
            # current_user is the full User entity
            ...
        ```

    HTTP Status Codes:
        - 401: Not authenticated
        - 403: Authenticated but insufficient role
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            # 1. Require authentication (raises 401 if not logged in)
            user_uid = require_authenticated_user(request)

            # 2. Get user service and fetch user
            user_service = user_service_getter()
            result = await user_service.get_user(user_uid)

            if result.is_error or not result.value:
                logger.warning(f"Role check failed - user not found: {user_uid}")
                raise HTTPException(403, "Access denied")

            user = result.value

            # 3. Check role hierarchy
            if not user.has_permission(required_role):
                logger.warning(
                    f"Role check failed for {user_uid}: "
                    f"has {user.role.value}, needs {required_role.value}"
                )
                raise HTTPException(403, f"Requires {required_role.value} role or higher")

            # 4. Inject current_user (full User entity) into kwargs
            # NOTE: This is the FULL User entity, not just user_uid string.
            # Routes using role decorators receive current_user: User
            # while routes using require_authenticated_user() get user_uid: str
            kwargs["current_user"] = user

            if asyncio.iscoroutinefunction(func):
                return await func(request, *args, **kwargs)
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_member(user_service_getter: Callable[[], Any]):
    """
    Shortcut for @require_role(UserRole.MEMBER, ...).

    Requires paid subscription (Member or higher).

    Usage:
        ```python
        def get_user_service():
            return services.user_service


        @rt("/api/premium/feature")
        @require_member(get_user_service)
        async def premium_feature(request, current_user): ...
        ```
    """
    return require_role(UserRole.MEMBER, user_service_getter)


def require_teacher(user_service_getter: Callable[[], Any]):
    """
    Shortcut for @require_role(UserRole.TEACHER, ...).

    Requires Teacher role for content creation.

    Usage:
        ```python
        def get_user_service():
            return services.user_service


        @rt("/api/ku")
        @require_teacher(get_user_service)
        async def create_knowledge_unit(request, current_user): ...
        ```
    """
    return require_role(UserRole.TEACHER, user_service_getter)


def require_admin(user_service_getter: Callable[[], Any]):
    """
    Shortcut for @require_role(UserRole.ADMIN, ...).

    Requires Admin role for user management.

    Usage:
        ```python
        def get_user_service():
            return services.user_service


        @rt("/api/admin/users")
        @require_admin(get_user_service)
        async def list_users(request, current_user): ...
        ```
    """
    return require_role(UserRole.ADMIN, user_service_getter)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Helpers
    "check_role_permission",
    "get_user_role",
    "is_current_user_admin",
    # Decorators
    "require_admin",
    "require_member",
    "require_role",
    "require_teacher",
]
