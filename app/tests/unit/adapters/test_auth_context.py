"""Tests for the auth context (ContextVar) and AuthContextMiddleware.

Mirrors tests/unit/adapters/test_csrf.py — the middleware-set context shape
this auth context copies from the CSRF token. The enforcement tests cover the
per-request graph-session validation that makes server-side revocation
(password change, role change, deactivation) actually log users out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from adapters.inbound.auth.context_middleware import AuthContextMiddleware
from core.utils.auth_context import AuthState, auth_state_var, current_auth_state
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from starlette.testclient import TestClient


class _StubGraphAuth:
    """validate_session_uid stub — swap ``result`` to steer a test."""

    def __init__(self, result: Result | None = None) -> None:
        self.result: Result = result if result is not None else Result.ok("user_x")
        self.calls: list[str] = []

    async def validate_session_uid(self, session_token: str) -> Result:
        self.calls.append(session_token)
        return self.result


def _make_request(session: dict | None, path: str = "/app") -> MagicMock:
    """Request-shaped mock with a real dict session (or none at all)."""
    request = MagicMock()
    request.session = session
    request.url.path = path
    return request


def _middleware(graph_auth: _StubGraphAuth | None = None) -> AuthContextMiddleware:
    return AuthContextMiddleware(app=MagicMock(), graph_auth=graph_auth or _StubGraphAuth())


def _valid_session(**extra) -> dict:
    return {"user_uid": "user_x", "session_token": "tok", **extra}


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
# AuthContextMiddleware.dispatch — ContextVar mirror
# ============================================================================


class TestAuthContextMiddleware:
    @pytest.mark.asyncio
    async def test_mirrors_session_into_context(self):
        request = _make_request(_valid_session(is_admin=True, is_teacher=False))
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
        request = _make_request(_valid_session(is_admin=True, is_teacher=True))

        async def call_next(_req):
            return "response"

        await _middleware().dispatch(request, call_next)
        assert current_auth_state() == AuthState()

    @pytest.mark.asyncio
    async def test_context_reset_when_handler_raises(self):
        request = _make_request(_valid_session())

        async def call_next(_req):
            raise ValueError("handler blew up")

        with pytest.raises(ValueError, match="handler blew up"):
            await _middleware().dispatch(request, call_next)
        assert current_auth_state() == AuthState()

    @pytest.mark.asyncio
    async def test_teacher_flag_mirrored(self):
        request = _make_request(_valid_session(is_teacher=True))
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return "response"

        await _middleware().dispatch(request, call_next)
        assert seen[0].is_teacher is True
        assert seen[0].is_admin is False


# ============================================================================
# AuthContextMiddleware — graph-session enforcement
# ============================================================================


class TestGraphSessionEnforcement:
    def test_graph_auth_required(self):
        with pytest.raises(ValueError, match="graph_auth"):
            AuthContextMiddleware(app=MagicMock(), graph_auth=None)

    @pytest.mark.asyncio
    async def test_valid_session_passes_and_validates_once(self):
        stub = _StubGraphAuth()
        session = _valid_session(is_admin=True)
        request = _make_request(session)
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return "response"

        await _middleware(stub).dispatch(request, call_next)
        assert stub.calls == ["tok"]
        assert session["user_uid"] == "user_x"  # untouched
        assert seen[0].is_authenticated is True

    @pytest.mark.asyncio
    async def test_revoked_session_cleared_and_request_proceeds_anonymous(self):
        stub = _StubGraphAuth(Result.ok(None))
        session = _valid_session(is_admin=True)
        request = _make_request(session)
        handler_response = MagicMock()
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return handler_response

        response = await _middleware(stub).dispatch(request, call_next)
        assert response is handler_response  # request proceeds — routes decide 401/redirect
        assert session == {}  # cookie session cleared → forced re-login
        assert seen[0].is_authenticated is False
        assert seen[0].is_admin is False

    @pytest.mark.asyncio
    async def test_validation_error_denies_without_clearing(self):
        stub = _StubGraphAuth(Result.fail(Errors.database(operation="validate", message="down")))
        session = _valid_session()
        request = _make_request(session)
        called: list[bool] = []

        async def call_next(_req):
            called.append(True)
            return "response"

        response = await _middleware(stub).dispatch(request, call_next)
        assert response.status_code == 503  # deny this request...
        assert session["session_token"] == "tok"  # ...but the session survives the outage
        assert called == []

    @pytest.mark.asyncio
    async def test_anonymous_request_skips_validation(self):
        stub = _StubGraphAuth()

        async def call_next(_req):
            return "response"

        await _middleware(stub).dispatch(_make_request({}), call_next)
        await _middleware(stub).dispatch(_make_request(None), call_next)
        assert stub.calls == []

    @pytest.mark.asyncio
    async def test_exempt_paths_skip_validation(self):
        stub = _StubGraphAuth()

        async def call_next(_req):
            return "response"

        for path in ("/static/css/output.css", "/health", "/health/ready", "/favicon.ico"):
            await _middleware(stub).dispatch(_make_request(_valid_session(), path=path), call_next)
        assert stub.calls == []

    @pytest.mark.asyncio
    async def test_user_uid_without_token_is_cleared(self):
        # Graph-native auth has no cookie-only sessions — nothing server-side
        # could ever revoke one, so it is treated as logged out.
        stub = _StubGraphAuth()
        session = {"user_uid": "user_x", "is_admin": True}
        request = _make_request(session)
        seen: list[AuthState] = []

        async def call_next(_req):
            seen.append(current_auth_state())
            return "response"

        await _middleware(stub).dispatch(request, call_next)
        assert session == {}
        assert stub.calls == []
        assert seen[0].is_authenticated is False


# ============================================================================
# Middleware wiring order — end to end through a real fast_app
# ============================================================================


class TestMiddlewareWiringOrder:
    """Prove the bootstrap wiring shape sees ``request.session``.

    FastHTML appends SessionMiddleware LAST (innermost), so
    ``app.user_middleware.append(Middleware(AuthContextMiddleware, ...))`` —
    the exact wiring in ``scripts/dev/bootstrap.py`` — places the auth context
    inside the session layer. Had it been wired with ``add_middleware()``
    (outermost), ``request.session`` access would raise and this test's
    requests would 500.
    """

    def _client(self, stub: _StubGraphAuth) -> "TestClient":
        from fasthtml.common import fast_app
        from starlette.middleware import Middleware
        from starlette.responses import PlainTextResponse
        from starlette.testclient import TestClient

        app, rt = fast_app(pico=False, default_hdrs=False, secret_key="smoke-secret")
        app.user_middleware.append(Middleware(AuthContextMiddleware, graph_auth=stub))

        @rt("/fake-login")
        def fake_login(request):
            request.session["user_uid"] = "user_x"
            request.session["session_token"] = "tok"
            request.session["is_admin"] = True
            return PlainTextResponse("ok")

        @rt("/whoami")
        def whoami(request):
            state = current_auth_state()
            return PlainTextResponse(f"{state.user_uid}|{state.is_admin}|{state.is_teacher}")

        return TestClient(app)

    def test_no_session_renders_unauthenticated(self):
        client = self._client(_StubGraphAuth())
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.text == "None|False|False"

    def test_session_flags_reach_context_through_real_stack(self):
        client = self._client(_StubGraphAuth())
        assert client.get("/fake-login").status_code == 200
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.text == "user_x|True|False"

    def test_revocation_forces_logout_through_real_stack(self):
        # Log in, then revoke server-side: the next request must come back
        # anonymous AND rewrite the cookie so the one after stays anonymous.
        stub = _StubGraphAuth()
        client = self._client(stub)
        assert client.get("/fake-login").status_code == 200
        assert client.get("/whoami").text == "user_x|True|False"

        stub.result = Result.ok(None)  # server-side revocation
        assert client.get("/whoami").text == "None|False|False"

        stub.result = Result.ok("user_x")  # backend valid again — but the
        assert client.get("/whoami").text == "None|False|False"  # cookie is gone
