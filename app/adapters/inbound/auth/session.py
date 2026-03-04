"""
Session Management for SKUEL
=============================

Cookie-based session management with optional graph-native validation.

Design Principles:
- Cookie stores session_token (signed, tamper-proof)
- Neo4j stores token_hash (SHA-256) — raw tokens never persisted
- Fast path: Read user_uid from cookie (no DB call)
- Secure path: Hash cookie token, match against token_hash in Neo4j
- Fail-fast: Invalid sessions return None (no user)
- Production guard: Dev fallback auth raises 401 in production/staging

Graph-Native Authentication:
- Sessions are stored in Neo4j as Session nodes (token_hash, not raw token)
- Cookie contains raw session_token for lookup (hashed before query)
- Session can be invalidated server-side
- Audit trail via AuthEvent nodes

Architecture:
1. SessionMiddleware handles cookie signing/verification
2. Cookie stores: session_token, user_uid, logged_in_at
3. Fast reads: get_current_user() reads user_uid from cookie
4. Secure reads: get_current_user_validated() validates token in Neo4j
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from starlette.requests import Request
from starlette.responses import RedirectResponse

from core.models.type_hints import UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.service_protocols import GraphAuthOperations

logger = get_logger("skuel.auth.session")


# ============================================================================
# SESSION CONFIGURATION
# ============================================================================

# Session cookie configuration
SESSION_COOKIE_NAME = "skuel_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_SECRET_KEY_ENV = "SESSION_SECRET_KEY"  # Environment variable name

# Default user for development (when no session exists)
# Security: Controlled via environment variable (January 2026 hardening)
# If SKUEL_DEFAULT_DEV_USER is not set, defaults to "user_mike" (underscore convention)
DEFAULT_DEV_USER = os.getenv("SKUEL_DEFAULT_DEV_USER", "user_mike")


# ============================================================================
# SESSION HELPERS
# ============================================================================


def get_current_user(request: Request) -> UserUID | None:
    """
    Get current authenticated user UID from session.

    Args:
        request: Starlette/FastHTML request object,

    Returns:
        user_uid if authenticated, None otherwise

    Usage:
        ```python
        @rt("/tasks")
        async def list_tasks(request):
            user_uid = get_current_user(request)
            if not user_uid:
                return RedirectResponse("/login")

            tasks = await service.list_tasks(user_uid=user_uid)
            ...
        ```
    """
    try:
        # Check if request has session (added by SessionMiddleware)
        session = getattr(request, "session", None)
        if session is None:
            logger.warning("Request has no session attribute - SessionMiddleware not installed?")
            return None

        # Get user_uid from session
        user_uid: str | None = session.get("user_uid")

        if user_uid:
            logger.debug(f"✅ Authenticated user found: {user_uid}")
            return UserUID(user_uid)

        # No session - return None
        logger.debug(f"ℹ️ No session found - session keys: {list(session.keys())}")
        return None

    except Exception as e:
        logger.error(f"Error getting current user from session: {e}")
        return None


def get_current_user_or_default(request: Request, default: UserUID = DEFAULT_DEV_USER) -> UserUID:
    """
    Get current user or fall back to default (for development).

    This is useful during development when you want to work without
    implementing full authentication.

    Args:
        request: Starlette/FastHTML request object,
        default: Default user UID to return if no session

    Returns:
        user_uid from session, or default,

    Usage:
        ```python
        @rt("/tasks")
        async def list_tasks(request):
            # Development-friendly: always returns a user
            user_uid = get_current_user_or_default(request)
            tasks = await service.list_tasks(user_uid=user_uid)
            ...
        ```
    """
    user_uid = get_current_user(request)
    if user_uid:
        return user_uid

    env = os.getenv("SKUEL_ENVIRONMENT", "local")
    if env in ("production", "staging"):
        logger.error("Dev fallback auth used in %s — denying access", env)
        from starlette.exceptions import HTTPException

        raise HTTPException(status_code=401, detail="Authentication required")

    logger.debug(f"No session - using default user: {default}")
    return UserUID(default)


async def get_current_user_validated(
    request: Request, graph_auth: "GraphAuthOperations"
) -> UserUID | None:
    """
    Get current user with graph-native session validation.

    This validates the session_token against Neo4j, ensuring:
    - Session exists and is not expired
    - Session has not been invalidated (e.g., after logout elsewhere)
    - User is still active

    Use this for sensitive operations where server-side session
    validation is required.

    Args:
        request: Starlette/FastHTML request object
        graph_auth: GraphAuthService instance for validation

    Returns:
        user_uid if session is valid, None otherwise

    Usage:
        ```python
        @rt("/api/account/delete", methods=["POST"])
        async def delete_account(request):
            # Validate session before destructive operation
            user_uid = await get_current_user_validated(request, graph_auth)
            if not user_uid:
                return RedirectResponse("/login")
            ...
        ```
    """
    try:
        session = getattr(request, "session", None)
        if session is None:
            return None

        session_token = session.get("session_token")
        if not session_token:
            # FAIL-FAST: No backward compat. Graph-native auth requires session_token.
            logger.warning("No session_token - graph-native auth required (no fallback)")
            return None

        # Validate session in Neo4j (optimized - no user fetch)
        result = await graph_auth.validate_session_uid(session_token)
        if result.is_error or not result.value:
            logger.warning("Session validation failed - session may have been invalidated")
            return None

        user_uid = result.value
        return UserUID(user_uid) if user_uid else None  # Returns user_uid directly

    except Exception as e:
        logger.error(f"Error validating session: {e}")
        return None


def get_session_token(request: Request) -> str | None:
    """
    Get session token from cookie.

    Args:
        request: Starlette/FastHTML request object

    Returns:
        session_token if present, None otherwise
    """
    session = getattr(request, "session", None)
    if session is None:
        return None
    return cast("str | None", session.get("session_token"))


def set_current_user(
    request: Request,
    user_uid: str,
    session_token: str | None = None,
    is_admin: bool = False,
    is_teacher: bool = False,
) -> None:
    """
    Set current user in session (log in).

    For graph-native auth, also stores session_token for server-side
    session validation. Stores is_admin for consistent navbar display.

    Args:
        request: Starlette/FastHTML request object
        user_uid: User UID to store in session
        session_token: Optional session token for graph-native auth
        is_admin: Whether user has admin role (for navbar display)

    Usage:
        ```python
        @rt("/login", methods=["POST"])
        async def login(request, username: str, password: str):
            # Authenticate with graph auth
            result = await graph_auth.sign_in(email, password, ip, user_agent)
            if result.value:
                set_current_user(
                    request,
                    user_uid=result.value["user_uid"],
                    session_token=result.value["session_token"],
                )
                return RedirectResponse("/")
        ```
    """
    session = getattr(request, "session", None)
    if session is None:
        logger.error("Cannot set user - request has no session attribute")
        logger.error("SessionMiddleware may not be installed correctly!")
        return

    session["user_uid"] = user_uid
    session["logged_in_at"] = datetime.now(UTC).isoformat()

    if session_token:
        session["session_token"] = session_token

    session["is_admin"] = is_admin
    session["is_teacher"] = is_teacher

    logger.info(
        f"Session updated: user_uid={user_uid}, is_admin={is_admin}, is_teacher={is_teacher}"
    )
    logger.debug(f"Session data: {dict(session)}")


def clear_current_user(request: Request) -> None:
    """
    Clear current user from session (log out).

    Args:
        request: Starlette/FastHTML request object,

    Usage:
        ```python
        @rt("/logout")
        async def logout(request):
            clear_current_user(request)
            return RedirectResponse("/login")
        ```
    """
    session = getattr(request, "session", None)
    if session is None:
        logger.error("Cannot clear user - request has no session attribute")
        return

    user_uid = session.get("user_uid")
    session.clear()
    logger.info(f"User logged out: {user_uid}")


def is_authenticated(request: Request) -> bool:
    """
    Check if user is authenticated.

    Args:
        request: Starlette/FastHTML request object,

    Returns:
        True if user is authenticated, False otherwise
    """
    return get_current_user(request) is not None


def get_is_admin(request: Request) -> bool:
    """
    Get is_admin flag from session (set at login).

    FAIL-FAST: No fallback. The is_admin flag is set when the user
    logs in based on user.can_manage_users(). If not in session,
    user must log out and back in.

    Args:
        request: Starlette/FastHTML request object

    Returns:
        True if user is admin, False otherwise
    """
    session = getattr(request, "session", None)
    if session is None:
        return False
    return cast("bool", session.get("is_admin", False))


def get_is_teacher(request: Request) -> bool:
    """
    Get is_teacher flag from session (set at login).

    Args:
        request: Starlette/FastHTML request object

    Returns:
        True if user is teacher or higher, False otherwise
    """
    session = getattr(request, "session", None)
    if session is None:
        return False
    return cast("bool", session.get("is_teacher", False))


def require_authenticated_user(request: Request) -> UserUID:
    """
    Get authenticated user UID or raise HTTPException.

    This is the production version of get_current_user_or_default.
    Instead of falling back to a default user, it requires real authentication.

    Args:
        request: Starlette/FastHTML request object

    Returns:
        user_uid if authenticated

    Raises:
        HTTPException(401): If user is not authenticated

    Usage:
        ```python
        @rt("/api/tasks")
        async def get_tasks(request):
            user_uid = require_authenticated_user(request)
            # Guaranteed to have real user_uid here
            tasks = await service.get_tasks(user_uid=user_uid)
            ...
        ```
    """
    user_uid = get_current_user(request)

    if not user_uid:
        logger.warning(f"Unauthenticated access attempt to {request.url.path}")
        from starlette.exceptions import HTTPException

        raise HTTPException(401, "Authentication required")

    return UserUID(user_uid)


# ============================================================================
# ROUTE DECORATORS
# ============================================================================


def require_auth(redirect_to: str = "/login"):
    """
    Decorator to require authentication for a route.

    If user is not authenticated, redirects to login page.

    Args:
        redirect_to: URL to redirect to if not authenticated,

    Usage:
        ```python
        @rt("/tasks")
        @require_auth()
        async def list_tasks(request):
            # User is guaranteed to be authenticated here
            user_uid = get_current_user(request)
            ...
        ```
    """

    def decorator(func) -> Any:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            if not is_authenticated(request):
                logger.warning(f"Unauthenticated access attempt to {request.url.path}")
                return RedirectResponse(redirect_to)

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def optional_auth(default_user: str = DEFAULT_DEV_USER):
    """
    Decorator for routes that work with or without authentication.

    Injects user_uid parameter (from session or default).

    Args:
        default_user: Default user UID if not authenticated,

    Usage:
        ```python
        @rt("/tasks")
        @optional_auth()
        async def list_tasks(request, user_uid: str):
            # user_uid is automatically injected
            tasks = await service.list_tasks(user_uid=user_uid)
            ...
        ```
    """

    def decorator(func) -> Any:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            # get_current_user_or_default already guards against prod dev fallback
            user_uid = get_current_user_or_default(request, default=default_user)
            kwargs["user_uid"] = user_uid
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def with_ownership(service_getter, uid_param: str = "uid"):
    """
    Decorator that verifies user owns the entity before allowing access.

    This decorator:
    1. Requires authentication (raises 401 if not logged in)
    2. Extracts the entity UID from path params
    3. Verifies the user owns the entity (returns 404 if not)
    4. Injects `user_uid` and `entity` into kwargs

    Args:
        service_getter: Function that returns the service (SKUEL012: use named function, not lambda)
        uid_param: Name of the path parameter containing the entity UID (default: "uid")

    Usage:
        ```python
        def get_goals_service():
            return goals_service


        @rt("/api/goals/{uid}/progress")
        @with_ownership(get_goals_service)
        @boundary_handler()
        async def update_goal_progress(request, user_uid: str, entity: Goal):
            # entity is pre-verified to belong to user_uid
            return await goals_service.update_goal_progress(entity.uid, ...)
        ```

    Security Note:
        Returns "not found" (not "access denied") to prevent information
        leakage about whether a UID exists.
    """
    from core.utils.result_simplified import Errors, Result

    def decorator(func) -> Any:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            # 1. Require authentication
            user_uid = require_authenticated_user(request)

            # 2. Get entity UID from path params
            uid = request.path_params.get(uid_param)
            if not uid:
                return Result.fail(
                    Errors.validation(
                        message=f"Missing {uid_param} in path",
                        field=uid_param,
                    )
                )

            # 3. Get service and verify ownership
            service = service_getter()
            ownership_result = await service.verify_ownership(uid, user_uid)

            if ownership_result.is_error:
                return ownership_result

            # 4. Inject user_uid and entity
            kwargs["user_uid"] = user_uid
            kwargs["entity"] = ownership_result.value

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_ownership_query(service_getter, uid_param: str = "uid") -> Any:
    """
    Decorator that verifies user owns the entity before allowing access.

    Unlike `with_ownership` which uses path params, this uses query params
    following FastHTML convention: `/api/domain/action?uid=...`

    This decorator:
    1. Requires authentication (raises 401 if not logged in)
    2. Extracts the entity UID from query params
    3. Verifies the user owns the entity (returns 404 if not)
    4. Injects `user_uid` and `entity` into kwargs

    Args:
        service_getter: Function that returns the service (SKUEL012: use named function, not lambda)
        uid_param: Name of the query parameter containing the entity UID (default: "uid")

    Usage:
        ```python
        def get_tasks_service():
            return tasks_service


        @rt("/api/tasks/complete")
        @require_ownership_query(get_tasks_service)
        @boundary_handler()
        async def complete_task(request, user_uid: str, entity: Task):
            # entity is pre-verified to belong to user_uid
            body = await request.json()
            return await tasks_service.complete_task(entity.uid, body.get("notes"))
        ```

    Security Note:
        Returns "not found" (not "access denied") to prevent information
        leakage about whether a UID exists.
    """
    from core.utils.result_simplified import Errors, Result

    def decorator(func) -> Any:
        @wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            # 1. Require authentication
            user_uid = require_authenticated_user(request)

            # 2. Get entity UID from query params (FastHTML convention)
            uid = request.query_params.get(uid_param)
            if not uid:
                return Result.fail(
                    Errors.validation(
                        message=f"Missing {uid_param} query parameter",
                        field=uid_param,
                    )
                )

            # 3. Get service and verify ownership
            service = service_getter()
            ownership_result = await service.verify_ownership(uid, user_uid)

            if ownership_result.is_error:
                return ownership_result

            # 4. Inject user_uid and entity
            kwargs["user_uid"] = user_uid
            kwargs["entity"] = ownership_result.value

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# SESSION DATA HELPERS
# ============================================================================


def get_session_data(request: Request, key: str, default: Any = None) -> Any:
    """
    Get arbitrary data from session.

    Args:
        request: Starlette/FastHTML request object,
        key: Session data key
        default: Default value if key not found

    Returns:
        Session data value or default
    """
    session = getattr(request, "session", None)
    if session is None:
        return default

    return session.get(key, default)


def set_session_data(request: Request, key: str, value: Any) -> None:
    """
    Set arbitrary data in session.

    Args:
        request: Starlette/FastHTML request object,
        key: Session data key
        value: Value to store
    """
    session = getattr(request, "session", None)
    if session is None:
        logger.error("Cannot set session data - request has no session attribute")
        return

    session[key] = value


# ============================================================================
# SESSION MIDDLEWARE CONFIGURATION HELPER
# ============================================================================


def get_session_middleware_config() -> dict:
    """
    Get SessionMiddleware configuration for SKUEL.

    Returns:
        Dict of middleware configuration parameters

    Usage in bootstrap:
        ```python
        from starlette.middleware.sessions import SessionMiddleware
        from adapters.inbound.auth.session import get_session_middleware_config

        config = get_session_middleware_config()
        app.add_middleware(SessionMiddleware, **config)
        ```
    """
    import os
    import secrets

    # Get secret key from environment or generate one (dev only)
    secret_key = os.getenv(SESSION_SECRET_KEY_ENV)
    env = os.getenv("SKUEL_ENVIRONMENT", "local")

    if not secret_key:
        if env in ("production", "staging"):
            raise RuntimeError(
                f"FATAL: {SESSION_SECRET_KEY_ENV} must be set in {env} environment"
            )
        # Development mode: generate random key (NOT persisted - sessions will invalidate on restart)
        secret_key = secrets.token_urlsafe(32)
        logger.warning(
            f"Using generated session secret (dev mode). "
            f"Set {SESSION_SECRET_KEY_ENV} environment variable for production."
        )
    else:
        logger.info(f"Using session secret from {SESSION_SECRET_KEY_ENV}")

    config = {
        "secret_key": secret_key,
        "session_cookie": SESSION_COOKIE_NAME,
        "max_age": SESSION_MAX_AGE,
        "https_only": env == "production",  # Secure only in prod
        "same_site": "strict",  # Strict CSRF protection (January 2026 hardening)
    }

    secret_source = "environment" if os.getenv(SESSION_SECRET_KEY_ENV) else "generated"
    logger.info(
        "Session security posture: environment=%s, https_only=%s, same_site=%s, "
        "secret_source=%s, dev_fallback_enabled=%s",
        env,
        config["https_only"],
        config["same_site"],
        secret_source,
        env not in ("production", "staging"),
    )

    return config


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Type aliases
    "UserUID",
    # Constants
    "DEFAULT_DEV_USER",
    "clear_current_user",
    # Core session functions
    "get_current_user",
    "get_current_user_or_default",
    "get_current_user_validated",  # Graph-native session validation
    "get_is_admin",  # Admin role check from session (January 2026)
    "get_is_teacher",  # Teacher role check from session (February 2026)
    # Session data
    "get_session_data",
    # Configuration
    "get_session_middleware_config",
    "get_session_token",
    "is_authenticated",
    "optional_auth",
    # Decorators
    "require_auth",
    "require_authenticated_user",
    "set_current_user",
    "set_session_data",
    # Ownership verification (December 2025)
    "with_ownership",
]
