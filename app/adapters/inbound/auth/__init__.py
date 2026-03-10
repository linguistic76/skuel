"""
HTTP Authentication Adapters for SKUEL
=======================================

Session management and role-based access control decorators.
These are HTTP-coupled (Starlette Request/Response) and belong in the adapter layer.

Framework-free auth utilities (password hashing, graph auth) remain in core/auth/.

Quick Start:
    ```python
    from adapters.inbound.auth import get_current_user, require_auth, require_admin
    ```
"""

from adapters.inbound.auth.roles import (
    check_role_permission,
    get_user_role,
    is_current_user_admin,
    make_service_getter,
    require_admin,
    require_member,
    require_role,
    require_teacher,
)
from adapters.inbound.auth.session import (
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
    # Session management
    "clear_current_user",
    "get_current_user",
    "get_current_user_or_default",
    "get_is_admin",
    "get_is_teacher",
    "get_session_data",
    "get_session_middleware_config",
    "is_authenticated",
    "optional_auth",
    "require_auth",
    "require_authenticated_user",
    "require_ownership_query",
    "set_current_user",
    "set_session_data",
    "with_ownership",
    # Role-based access control
    "check_role_permission",
    "get_user_role",
    "is_current_user_admin",
    "make_service_getter",
    "require_admin",
    "require_member",
    "require_role",
    "require_teacher",
]
