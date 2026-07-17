"""
Auth Context Middleware — per-request session→ContextVar mirror
================================================================

Mirrors the session's auth flags (``user_uid``, ``is_admin``, ``is_teacher``)
into ``core/utils/auth_context.py`` once per request so page chrome
(BasePage / navbar) can read auth state without importing this layer. Same
shape as ``CSRFMiddleware`` + ``csrf_token_context`` (set before ``call_next``,
reset in ``finally``).

Ordering constraint: this middleware reads ``request.session``, so it MUST run
INSIDE Starlette's ``SessionMiddleware``. FastHTML appends the session
middleware LAST to the constructor list (innermost of that set), and
``app.add_middleware()`` inserts at position 0 (outermost) — so the bootstrap
wires this via ``app.user_middleware.append(Middleware(AuthContextMiddleware))``
after ``fast_app()`` returns, never via ``add_middleware()``.

The session readers in ``adapters/inbound/auth/session.py`` remain the single
source of truth for session-key knowledge — this middleware delegates to them
rather than re-reading the keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from adapters.inbound.auth.session import get_current_user, get_is_admin, get_is_teacher
from core.utils.auth_context import AuthState, auth_state_var

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response

    from adapters.inbound.fasthtml_types import Request


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Set the request-scoped auth context from the session, reset after."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        state = AuthState(
            user_uid=get_current_user(request),
            is_admin=get_is_admin(request),
            is_teacher=get_is_teacher(request),
        )
        ctx_token = auth_state_var.set(state)
        try:
            return await call_next(request)
        finally:
            auth_state_var.reset(ctx_token)


__all__ = ["AuthContextMiddleware"]
