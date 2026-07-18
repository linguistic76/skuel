"""
Authentication API Routes
==========================

Debug and diagnostic endpoints for authentication system.

Routes:
- GET /debug-session - Debug session state (admin-only)
- GET /whoami - Show current user info (admin-only)

Security:
- All routes require ADMIN role
- Exposes session internals and user identity

Version: 2.1.0
Date: 2026-01-21
"""

from typing import Any

from fasthtml.common import H1, Div, P, Pre

from adapters.inbound.auth import (
    get_current_user,
    is_authenticated,
    make_service_getter,
    require_admin,
)
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.components import ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.primitives import ButtonLink

logger = get_logger("skuel.routes.auth_api")


def create_auth_api_routes(
    app: Any,
    rt: Any,
    graph_auth: Any,
    user_service: Any = None,
) -> list[Any]:
    """
    Create authentication API routes (debug endpoints).

    Args:
        app: FastHTML app instance
        rt: Route decorator
        graph_auth: Graph authentication service
        user_service: Optional user service for admin checks

    Returns:
        List of created routes
    """
    routes: list[Any] = []

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # DEBUG ENDPOINTS (ADMIN-ONLY)
    # ========================================================================

    @rt("/debug-session")
    @require_admin(get_user_service)
    def debug_session(request: Request, current_user: Any = None) -> Any:
        """
        Debug session state.

        Security: Admin-only - exposes session internals.
        """
        try:
            session = getattr(request, "session", None)
            session_data = dict(session) if session else {}
        except AttributeError:
            session_data = {}
        user_uid = get_current_user(request)

        return Div(
            H1("Session Debug (Admin)"),
            P(f"User UID from helper: {user_uid}"),
            P(f"Session has user_uid: {'user_uid' in session_data}"),
            Pre(str(session_data)),
        )

    @rt("/whoami")
    @require_admin(get_user_service)
    def whoami(request: Request, current_user: Any = None) -> Any:
        """
        Show current user info.

        Security: Admin-only - exposes user identity details.
        """
        user_uid = get_current_user(request)
        is_auth = is_authenticated(request)

        return Div(
            H1("Current User (Admin)", cls="text-3xl font-bold mb-6"),
            Card(
                CardHeader(CardTitle("Session Information")),
                CardBody(
                    Div(
                        P("User UID:", cls="font-medium"),
                        P(user_uid or "None", cls="text-muted-foreground font-mono"),
                        cls="mb-3",
                    ),
                    Div(
                        P("Authenticated:", cls="font-medium"),
                        P("Yes" if is_auth else "No", cls="text-muted-foreground"),
                        cls="mb-3",
                    ),
                    Div(
                        P("Session Status:", cls="font-medium"),
                        P(
                            "Active session" if is_auth else "No session",
                            cls="text-muted-foreground",
                        ),
                        cls="mb-6",
                    ),
                    Div(
                        ButtonLink(
                            "Logout" if is_auth else "Login",
                            href="/logout" if is_auth else "/login",
                            cls=ButtonT.secondary,
                        ),
                        ButtonLink("Home", href="/", cls=ButtonT.secondary),
                        cls="flex gap-3",
                    ),
                ),
                cls="max-w-2xl",
            ),
            cls="container mx-auto p-6",
        )

    # Collect all routes
    routes.extend(
        [
            debug_session,
            whoami,
        ]
    )

    logger.info(f"Auth API routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_auth_api_routes"]
