"""
Auth Context Middleware — per-request session enforcement + ContextVar mirror
==============================================================================

Two jobs, in order, once per request:

1. **Enforce the graph session.** Authenticated requests carry a
   ``session_token`` in the signed cookie; this middleware validates it
   against the graph (``validate_session_uid``: session not revoked, not
   expired, LIVE User still active — plus the 5-min-batched last-active
   touch, all one statement). A revoked or expired session clears the cookie
   session, so the request — and every request after it — proceeds as
   unauthenticated and the user is forced back through login. This is what
   makes server-side revocation (password change/reset, role change,
   deactivation, account deletion) actually bite; without it a stolen or
   stale cookie would stay live for its full 30-day max_age.

2. **Mirror auth flags into the ContextVar.** The post-enforcement session
   flags (``user_uid``, ``is_admin``, ``is_teacher``) are copied into
   ``core/utils/auth_context.py`` so page chrome (BasePage / navbar) can read
   auth state without importing this layer. Same shape as ``CSRFMiddleware``
   + ``csrf_token_context`` (set before ``call_next``, reset in ``finally``).

Enforcement semantics:

- Anonymous requests (no ``user_uid`` in the session) skip validation — the
  local-dev default-user flow never writes the session, so it is unaffected.
- ``user_uid`` without ``session_token`` is cleared: graph-native auth has no
  cookie-only sessions (fail-fast, no legacy path), and a session that has no
  server-side node cannot be revoked.
- A validation *error* (Neo4j unreachable) responds 503 WITHOUT clearing the
  cookie — deny the request, keep the session; it recovers with the database.
- Static/health/PWA paths are exempt: browsers send the session cookie on
  subresource fetches, and validating a page's dozen asset requests would
  multiply the per-request read for zero enforcement value.

Cost: one indexed statement on ``Session.token_hash`` per authenticated
request (validity + live-User check + batched last-active touch, one round
trip). WebSocket scopes pass through ``BaseHTTPMiddleware`` untouched — the one
WebSocket channel (``/ws/agent``) performs its own challenge handshake at
connect (adapters/inbound/device_routes.py) instead.

Ordering constraint: this middleware reads ``request.session``, so it MUST run
INSIDE Starlette's ``SessionMiddleware``. FastHTML appends the session
middleware LAST to the constructor list (innermost of that set), and
``app.add_middleware()`` inserts at position 0 (outermost) — so the bootstrap
wires this via ``app.user_middleware.append(Middleware(AuthContextMiddleware,
graph_auth=...))`` after ``fast_app()`` returns, never via ``add_middleware()``.

The session readers in ``adapters/inbound/auth/session.py`` remain the single
source of truth for session-key knowledge — this middleware delegates to them
rather than re-reading the keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from adapters.inbound.auth.session import get_current_user, get_is_admin, get_is_teacher
from core.utils.auth_context import AuthState, auth_state_var
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response
    from starlette.types import ASGIApp

    from adapters.inbound.fasthtml_types import Request
    from core.ports.service_protocols import GraphAuthOperations

logger = get_logger("skuel.auth.context_middleware")

# Subresource + liveness paths where validating adds cost but no enforcement
# (mirrors the CSRF mint exemptions in adapters/inbound/csrf.py). /logout is
# exempt for a different reason: its whole job is clearing the cookie session,
# which must stay possible during a graph outage — enforcement would 503 the
# one request that needs no validation to be safe.
_ENFORCE_EXEMPT_PREFIXES: tuple[str, ...] = ("/static/",)
_ENFORCE_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/health/ready",
        "/metrics",
        "/manifest.json",
        "/service-worker.js",
        "/favicon.ico",
        "/robots.txt",
        "/logout",
    }
)


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Enforce the graph session, then mirror auth state into the ContextVar."""

    def __init__(self, app: ASGIApp, graph_auth: GraphAuthOperations) -> None:
        if graph_auth is None:
            raise ValueError(
                "AuthContextMiddleware requires graph_auth — session revocation "
                "is unenforceable without server-side validation"
            )
        super().__init__(app)
        self._graph_auth = graph_auth

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        denial = await self._enforce_graph_session(request)
        if denial is not None:
            return denial

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

    async def _enforce_graph_session(self, request: Request) -> Response | None:
        """Validate the cookie's graph session; None means "proceed".

        Clears the session (→ request proceeds unauthenticated, routes send
        the user to login) when the graph says the session is revoked or
        expired; returns a 503 without touching the cookie when validation
        itself fails.
        """
        path = request.url.path
        if path in _ENFORCE_EXEMPT_PATHS or path.startswith(_ENFORCE_EXEMPT_PREFIXES):
            return None

        session = getattr(request, "session", None)
        if not session or not session.get("user_uid"):
            return None

        session_token = session.get("session_token")
        if not session_token:
            logger.warning(
                "Session with user_uid=%s has no session_token — clearing "
                "(graph-native auth has no cookie-only sessions)",
                session.get("user_uid"),
            )
            session.clear()
            return None

        result = await self._graph_auth.validate_session_uid(session_token)
        if result.is_error:
            logger.error(
                "Graph session validation failed for user_uid=%s: %s",
                session.get("user_uid"),
                result.expect_error().message,
            )
            return PlainTextResponse("Session validation temporarily unavailable", status_code=503)

        if result.value is None:
            logger.info(
                "Revoked/expired graph session for user_uid=%s — forcing re-login",
                session.get("user_uid"),
            )
            session.clear()

        return None


__all__ = ["AuthContextMiddleware"]
