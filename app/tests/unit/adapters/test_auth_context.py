"""Tests for the auth context (ContextVar) and AuthContextMiddleware.

Mirrors tests/unit/adapters/test_csrf.py — the middleware-set context shape
this auth context copies from the CSRF token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from adapters.inbound.auth.context_middleware import AuthContextMiddleware
from core.utils.auth_context import AuthState, auth_state_var, current_auth_state

if TYPE_CHECKING:
    from starlette.testclient import TestClient


def _make_request(session: dict | None) -> MagicMock:
    """Request-shaped mock with a real dict session (or none at all)."""
    request = MagicMock()
    request.session = session
    return request


def _middleware() -> AuthContextMiddleware:
    return AuthContextMiddleware(app=MagicMock())


# ============================================================================
# AuthState
# ============================================================================


class TestAuthState:
    def test_default_is_unauthenticated(self):
        state = AuthState()
        assert state.user_uid is None
        assert state.is_admin is False
        assert state.is_teacher is False
        assert state.is_authenticated is False

    def test_user_uid_implies_authenticated(self):
        assert AuthState(user_uid="user_x").is_authenticated is True

    def test_frozen(self):
        state = AuthState(user_uid="user_x")
        with pytest.raises(AttributeError):
            state.user_uid = "user_y"  # type: ignore[misc]


# ============================================================================
# current_auth_state — set / reset / default
# ============================================================================


class TestCurrentAuthState:
    def test_default_when_no_middleware(self):
        # No middleware in play — contextvar defaults to None.
        assert current_auth_state() == AuthState()

    def test_reads_contextvar(self):
        state = AuthState(user_uid="user_x", is_admin=True, is_teacher=True)
        token = auth_state_var.set(state)
        try:
            assert current_auth_state() is state
        finally:
            auth_state_var.reset(token)

    def test_reset_restores_default(self):
        token = auth_state_var.set(AuthState(user_uid="user_x"))
        auth_state_var.reset(token)
        assert current_auth_state() == AuthState()


# ============================================================================
# AuthContextMiddleware.dispatch
# ============================================================================


class TestAuthContextMiddleware:
    @pytest.mark.asyncio
    async def test_mirrors_session_into_context(self):
        request = _make_request({"user_uid": "user_x", "is_admin": True, "is_teacher": False})
        response = MagicMock()
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return response

        assert await _middleware().dispatch(request, call_next) is response
        assert seen == [AuthState(user_uid="user_x", is_admin=True, is_teacher=False)]

    @pytest.mark.asyncio
    async def test_empty_session_is_unauthenticated(self):
        request = _make_request({})
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return "response"

        await _middleware().dispatch(request, call_next)
        assert seen == [AuthState()]
        assert seen[0].is_authenticated is False

    @pytest.mark.asyncio
    async def test_context_reset_after_dispatch(self):
        request = _make_request({"user_uid": "user_x", "is_admin": True, "is_teacher": True})

        async def call_next(_req):
            return "response"

        await _middleware().dispatch(request, call_next)
        assert current_auth_state() == AuthState()

    @pytest.mark.asyncio
    async def test_context_reset_when_handler_raises(self):
        request = _make_request({"user_uid": "user_x"})

        async def call_next(_req):
            raise ValueError("handler blew up")

        with pytest.raises(ValueError, match="handler blew up"):
            await _middleware().dispatch(request, call_next)
        assert current_auth_state() == AuthState()

    @pytest.mark.asyncio
    async def test_teacher_flag_mirrored(self):
        request = _make_request({"user_uid": "user_t", "is_teacher": True})
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return "response"

        await _middleware().dispatch(request, call_next)
        assert seen[0].is_teacher is True
        assert seen[0].is_admin is False


# ============================================================================
# Middleware wiring order — end to end through a real fast_app
# ============================================================================


class TestMiddlewareWiringOrder:
    """Prove the bootstrap wiring shape sees ``request.session``.

    FastHTML appends SessionMiddleware LAST (innermost), so
    ``app.user_middleware.append(Middleware(AuthContextMiddleware))`` — the
    exact wiring in ``scripts/dev/bootstrap.py`` — places the auth context
    inside the session layer. Had it been wired with ``add_middleware()``
    (outermost), ``request.session`` access would raise and this test's
    requests would 500.
    """

    def _client(self) -> "TestClient":
        from fasthtml.common import fast_app
        from starlette.middleware import Middleware
        from starlette.responses import PlainTextResponse
        from starlette.testclient import TestClient

        app, rt = fast_app(pico=False, default_hdrs=False, secret_key="smoke-secret")
        app.user_middleware.append(Middleware(AuthContextMiddleware))

        @rt("/fake-login")
        def fake_login(request):
            request.session["user_uid"] = "user_x"
            request.session["is_admin"] = True
            return PlainTextResponse("ok")

        @rt("/whoami")
        def whoami(request):
            state = current_auth_state()
            return PlainTextResponse(f"{state.user_uid}|{state.is_admin}|{state.is_teacher}")

        return TestClient(app)

    def test_no_session_renders_unauthenticated(self):
        client = self._client()
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.text == "None|False|False"

    def test_session_flags_reach_context_through_real_stack(self):
        client = self._client()
        assert client.get("/fake-login").status_code == 200
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.text == "user_x|True|False"
