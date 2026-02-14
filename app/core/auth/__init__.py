"""
Authentication and Session Management for SKUEL
===============================================

Simple, secure session-based authentication using Starlette's SessionMiddleware.

Quick Start:
    ```python
    # In routes - get current user
    from core.auth import get_current_user


    @rt("/tasks")
    async def list_tasks(request):
        user_uid = get_current_user(request)
        if not user_uid:
            return RedirectResponse("/login")
        ...


    # Or use decorator for development (auto-fallback to default user)
    from core.auth import get_current_user_or_default


    @rt("/tasks")
    async def list_tasks(request):
        user_uid = get_current_user_or_default(request)  # Never None
        ...


    # Or require authentication
    from core.auth import require_auth


    @rt("/tasks")
    @require_auth()
    async def list_tasks(request):
        user_uid = get_current_user(request)  # Guaranteed not None
        ...
    ```

Installation:
    The SessionMiddleware is automatically installed in bootstrap.py.
    No manual setup needed in routes.
"""

from core.auth.roles import (
    check_role_permission,
    get_user_role,
    is_current_user_admin,
    require_admin,
    require_member,
    require_role,
    require_teacher,
)
from core.auth.session import (
    DEFAULT_DEV_USER,
    UserUID,
    clear_current_user,
    get_current_user,
    get_current_user_or_default,
    get_is_admin,
    get_is_teacher,
    get_session_data,
    get_session_middleware_config,
    is_authenticated,
    optional_auth,
    require_auth,
    require_authenticated_user,
    require_ownership_query,
    set_current_user,
    set_session_data,
    with_ownership,
)

__all__ = [
    # Type aliases
    "UserUID",
    # Constants
    "DEFAULT_DEV_USER",
    # Role-based access control
    "check_role_permission",
    "clear_current_user",
    "get_current_user",
    "get_current_user_or_default",
    "get_is_admin",
    "get_is_teacher",
    "get_session_data",
    "get_session_middleware_config",
    "get_user_role",
    "is_authenticated",
    "is_current_user_admin",
    "optional_auth",
    "require_admin",
    "require_auth",
    "require_authenticated_user",
    "require_member",
    "require_ownership_query",
    "require_role",
    "require_teacher",
    "set_current_user",
    "set_session_data",
    "with_ownership",
]
