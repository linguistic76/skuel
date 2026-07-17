"""
Request-Scoped Auth Context
============================

The render surface for per-request auth state. The inbound middleware
(``adapters/inbound/auth/context_middleware.py``) mirrors the session's auth
flags here once per request; page chrome (BasePage / navbar) reads them back
without a plumbed ``request`` argument.

Lives in ``core/utils`` so the dependency arrows stay inward — the middleware
(adapters → core) writes, layout components (ui → core) read. The session
itself stays the single source of truth: this is a per-request mirror, never
an alternative store. Routes keep using the ``adapters.inbound.auth`` session
readers directly.

When no middleware has run (unit renders, WebSocket paths BaseHTTPMiddleware
does not wrap), readers degrade to the unauthenticated default — the same
behavior the session readers have when ``request.session`` is absent.

See: ``core/utils/csrf_token_context.py`` for the same shape used by the CSRF
token, and lint rule SKUEL027 (no runtime ``adapters`` imports in ``ui/``) for
the boundary this context exists to satisfy.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthState:
    """Auth flags for the in-flight request, mirrored from the session."""

    user_uid: str | None = None
    is_admin: bool = False
    is_teacher: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.user_uid is not None


_UNAUTHENTICATED = AuthState()

# Scope is per request/task — set (and reset) by AuthContextMiddleware.dispatch.
auth_state_var: ContextVar[AuthState | None] = ContextVar("auth_state_var", default=None)


def current_auth_state() -> AuthState:
    """Return the auth state for the in-flight request.

    Unauthenticated default when no middleware has set the context.
    """
    return auth_state_var.get() or _UNAUTHENTICATED
