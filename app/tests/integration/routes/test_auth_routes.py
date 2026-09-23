"""
Route tests for the authentication UI handlers (``adapters/inbound/auth_ui.py``).

Every test calls the real handler through a collector ``rt`` harness —
``create_auth_ui_routes`` registers into a dict and the test invokes the
function with a request stub — so what is asserted is what the handler does:
which service calls it makes, what it renders, what it writes to the session.
``GraphAuthService`` and ``UserService`` are mocks; their own behaviour is
pinned in ``tests/unit/auth/test_graph_auth_service.py`` and, against a real
graph, ``tests/integration/test_login_roundtrip.py``.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml
from starlette.datastructures import FormData

from core.utils.result_simplified import Errors, Result
from tests.fixtures.csrf import attach_csrf

_PASSWORD = "password123"

_REGISTRATION_FORM = {
    "username": "newuser",
    "email": "new@example.com",
    "display_name": "New User",
    "password": _PASSWORD,
    "confirm_password": _PASSWORD,
    "accept_terms": "1",
}


def _handlers(graph_auth: MagicMock | None = None, user_service: MagicMock | None = None) -> dict:
    """The auth UI handlers, keyed by path."""
    from adapters.inbound.auth_ui import create_auth_ui_routes

    registered: dict = {}

    def rt_collector(path: str, *_a, **_kw):
        def decorator(fn):
            registered[path] = fn
            return fn

        return decorator

    create_auth_ui_routes(MagicMock(), rt_collector, graph_auth or MagicMock(), user_service)
    return registered


def _post(path: str, fields: dict[str, str], session: dict | None = None):
    """A CSRF-valid POST request stub carrying ``fields`` as its form body."""
    form_data = FormData(list(fields.items()))

    async def _form() -> FormData:
        return form_data

    return attach_csrf(
        SimpleNamespace(
            method="POST",
            session={} if session is None else session,
            form=_form,
            client=SimpleNamespace(host="10.0.0.9"),
            headers={"user-agent": "pytest"},
            cookies={},
            url=SimpleNamespace(path=path),
        )
    )


def _signed_in(user_uid: str = "user_alice") -> Result:
    """What ``sign_in`` returns on success."""
    user = MagicMock()
    user.can_manage_users.return_value = False
    user.can_create_curriculum.return_value = False
    return Result.ok({"user_uid": user_uid, "session_token": "tok-new", "user": user})


def _graph_auth() -> MagicMock:
    graph_auth = MagicMock()
    graph_auth.sign_up = AsyncMock(
        return_value=Result.ok({"user_uid": "user_new", "email": "new@example.com"})
    )
    # Auto-login fails → register_submit redirects to /login?registered=true,
    # a clean success signal without exercising session mechanics.
    graph_auth.sign_in = AsyncMock(
        return_value=Result.fail(Errors.system("no session in tests", operation="sign_in"))
    )
    return graph_auth


@pytest.fixture(autouse=True)
def _route_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNUP_INVITE_CODE", raising=False)

    # Pin the credential funnel to the process env: the route resolves the
    # invite code via get_credential(), which would otherwise read the dev
    # machine's real keyring — and auto-migrate monkeypatched test values
    # INTO it. Env-only keeps these tests hermetic.
    import adapters.inbound.auth_ui as auth_ui_module

    def _env_only_credential(key: str, fallback_to_env: bool = True) -> str | None:
        return os.getenv(key)

    monkeypatch.setattr(auth_ui_module, "get_credential", _env_only_credential)

    from adapters.inbound.rate_limit import reset_buckets_for_testing

    reset_buckets_for_testing()


class TestRegistrationRefusals:
    """A form the request model rejects never reaches ``sign_up``; the page
    comes back carrying the model's message."""

    @pytest.mark.parametrize(
        ("override", "message"),
        [
            ({"confirm_password": "different123"}, "Passwords do not match"),
            ({"accept_terms": "0"}, "You must accept the Terms of Service"),
            ({"email": ""}, "Email is required"),
            ({"password": "", "confirm_password": ""}, "Password is required"),
        ],
    )
    async def test_invalid_form_is_refused_before_sign_up(
        self, override: dict[str, str], message: str
    ) -> None:
        graph_auth = _graph_auth()

        response = await _handlers(graph_auth)["/register/submit"](
            request=_post("/register/submit", {**_REGISTRATION_FORM, **override})
        )

        graph_auth.sign_up.assert_not_awaited()
        assert message in to_xml(response)

    async def test_sign_up_refusal_is_shown_and_no_session_is_made(self) -> None:
        graph_auth = _graph_auth()
        graph_auth.sign_up.return_value = Result.fail(
            Errors.validation(message="An account with this email already exists", field="email")
        )
        request = _post("/register/submit", _REGISTRATION_FORM)

        response = await _handlers(graph_auth)["/register/submit"](request=request)

        assert "An account with this email already exists" in to_xml(response)
        graph_auth.sign_in.assert_not_awaited()
        assert request.session == {}


class TestLoginSubmit:
    """POST /login/submit: email or username in, a fresh session out."""

    async def test_email_login_replaces_the_session_and_lands_on_today(self) -> None:
        graph_auth = _graph_auth()
        graph_auth.sign_in.return_value = _signed_in("user_alice")
        user_service = MagicMock()
        user_service.get_user_by_username = AsyncMock()
        request = _post(
            "/login/submit",
            {"username": "alice@example.com", "password": _PASSWORD},
            session={"user_uid": "user_previous", "stale": "x"},
        )

        response = await _handlers(graph_auth, user_service)["/login/submit"](request=request)

        assert response.status_code == 303
        assert response.headers["location"] == "/today"
        assert graph_auth.sign_in.await_args.kwargs["email"] == "alice@example.com"
        assert graph_auth.sign_in.await_args.kwargs["password"] == _PASSWORD
        user_service.get_user_by_username.assert_not_awaited()
        assert request.session["user_uid"] == "user_alice"
        assert request.session["session_token"] == "tok-new"
        assert "stale" not in request.session

    async def test_username_login_signs_in_with_the_resolved_email(self) -> None:
        graph_auth = _graph_auth()
        graph_auth.sign_in.return_value = _signed_in("user_alice")
        user_service = MagicMock()
        user_service.get_user_by_username = AsyncMock(
            return_value=Result.ok(SimpleNamespace(email="alice@example.com"))
        )
        request = _post("/login/submit", {"username": "alice", "password": _PASSWORD})

        response = await _handlers(graph_auth, user_service)["/login/submit"](request=request)

        user_service.get_user_by_username.assert_awaited_once_with("alice")
        assert graph_auth.sign_in.await_args.kwargs["email"] == "alice@example.com"
        assert response.headers["location"] == "/today"

    async def test_unknown_username_is_refused_without_sign_in(self) -> None:
        graph_auth = _graph_auth()
        user_service = MagicMock()
        user_service.get_user_by_username = AsyncMock(return_value=Result.ok(None))
        request = _post("/login/submit", {"username": "ghost", "password": _PASSWORD})

        response = await _handlers(graph_auth, user_service)["/login/submit"](request=request)

        graph_auth.sign_in.assert_not_awaited()
        assert "Invalid username or password" in to_xml(response)
        assert request.session == {}

    async def test_refused_sign_in_leaves_the_session_untouched(self) -> None:
        graph_auth = _graph_auth()
        graph_auth.sign_in.return_value = Result.fail(
            Errors.business("auth", "Invalid email or password")
        )
        request = _post(
            "/login/submit",
            {"username": "alice@example.com", "password": "wrong"},
            session={"user_uid": "user_previous"},
        )

        response = await _handlers(graph_auth)["/login/submit"](request=request)

        assert "Invalid email or password" in to_xml(response)
        assert request.session == {"user_uid": "user_previous"}

    async def test_blank_password_is_refused_before_sign_in(self) -> None:
        graph_auth = _graph_auth()

        response = await _handlers(graph_auth)["/login/submit"](
            request=_post("/login/submit", {"username": "alice@example.com", "password": ""})
        )

        graph_auth.sign_in.assert_not_awaited()
        assert "Password is required" in to_xml(response)


class TestSessionManagement:
    """Tests for session-related functionality."""

    def test_is_authenticated_with_session(self):
        """Test is_authenticated returns True when user in session."""
        from adapters.inbound.auth.session import is_authenticated

        class MockRequest:
            session = {"user_uid": "user_test"}

        assert is_authenticated(MockRequest()) is True

    def test_is_authenticated_without_session(self):
        """Test is_authenticated returns False when no user in session."""
        from adapters.inbound.auth.session import is_authenticated

        class MockRequest:
            session = {}

        assert is_authenticated(MockRequest()) is False

    def test_get_current_user_returns_uid(self):
        """Test get_current_user returns user UID from session."""
        from adapters.inbound.auth.session import get_current_user

        class MockRequest:
            session = {"user_uid": "user_test"}

        assert get_current_user(MockRequest()) == "user_test"

    def test_get_current_user_returns_none(self):
        """Test get_current_user returns None when no session."""
        from adapters.inbound.auth.session import get_current_user

        class MockRequest:
            session = {}

        assert get_current_user(MockRequest()) is None

    def test_set_current_user_sets_session(self):
        """Test set_current_user sets session data."""
        from adapters.inbound.auth.session import set_current_user

        class MockRequest:
            session = {}

        set_current_user(MockRequest(), "user_test")
        assert MockRequest.session.get("user_uid") == "user_test"

    def test_set_current_user_with_token(self):
        """Test set_current_user sets session with token."""
        from adapters.inbound.auth.session import set_current_user

        class MockRequest:
            session = {}

        set_current_user(MockRequest(), "user_test", session_token="token-abc")
        assert MockRequest.session.get("user_uid") == "user_test"
        assert MockRequest.session.get("session_token") == "token-abc"

    def test_clear_current_user_clears_session(self):
        """Test clear_current_user clears session."""
        from adapters.inbound.auth.session import clear_current_user

        class MockRequest:
            session = {"user_uid": "user_test", "session_token": "token", "other": "data"}

        clear_current_user(MockRequest())
        assert MockRequest.session == {}


class TestRedirectBehavior:
    """An already-authenticated visitor to an auth page is sent to the one
    landing — ``/today`` for every role (ADR-058, amended) — through the real
    handlers, never a restated constant."""

    @staticmethod
    def _authenticated_request(is_admin: bool):
        return SimpleNamespace(
            session={"user_uid": "user_x", "session_token": "tok", "is_admin": is_admin}
        )

    @pytest.mark.parametrize("path", ["/login", "/register", "/reset-password"])
    @pytest.mark.parametrize("is_admin", [False, True])
    def test_auth_pages_send_an_authenticated_visitor_to_today(
        self, path: str, is_admin: bool
    ) -> None:
        response = _handlers()[path](request=self._authenticated_request(is_admin))
        assert response.status_code == 303
        assert response.headers["location"] == "/today"

    async def test_logout_redirects_to_login(self) -> None:
        request = SimpleNamespace(session={}, client=None, headers={})
        response = await _handlers()["/logout"](request=request)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


class TestFormValidation:
    """Tests for form validation patterns."""

    def test_safe_form_string_extracts_value(self):
        """Test safe_form_string extracts form values safely."""
        from adapters.inbound.form_helpers import safe_form_string

        assert safe_form_string("value") == "value"
        assert safe_form_string("  trimmed  ") == "trimmed"
        assert safe_form_string(None) == ""
        assert safe_form_string("") == ""


class TestInviteCodeGate:
    """SIGNUP_INVITE_CODE gates /register/submit (public-facing hardening).

    The gate runs BEFORE ``sign_up`` so a bad code never creates an account;
    unset env = open signup (passthrough).
    """

    @staticmethod
    def _submit_request(invite_code: str | None = None):
        fields = dict(_REGISTRATION_FORM)
        if invite_code is not None:
            fields["invite_code"] = invite_code
        return _post("/register/submit", fields)

    async def test_unset_env_is_open_signup(self) -> None:
        graph_auth = _graph_auth()
        handlers = _handlers(graph_auth)

        response = await handlers["/register/submit"](request=self._submit_request())

        graph_auth.sign_up.assert_awaited_once()
        assert response.status_code == 303  # → /login?registered=true

    async def test_wrong_code_rejected_before_signup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIGNUP_INVITE_CODE", "sekrit")
        graph_auth = _graph_auth()
        handlers = _handlers(graph_auth)

        response = await handlers["/register/submit"](
            request=self._submit_request(invite_code="wrong")
        )

        graph_auth.sign_up.assert_not_awaited()
        assert "Invalid invite code" in to_xml(response)

    async def test_absent_code_rejected_before_signup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SIGNUP_INVITE_CODE", "sekrit")
        graph_auth = _graph_auth()
        handlers = _handlers(graph_auth)

        response = await handlers["/register/submit"](request=self._submit_request())

        graph_auth.sign_up.assert_not_awaited()
        assert "Invalid invite code" in to_xml(response)

    async def test_correct_code_registers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIGNUP_INVITE_CODE", "sekrit")
        graph_auth = _graph_auth()
        handlers = _handlers(graph_auth)

        response = await handlers["/register/submit"](
            request=self._submit_request(invite_code="sekrit")
        )

        graph_auth.sign_up.assert_awaited_once()
        assert response.status_code == 303

    def test_register_page_shows_invite_input_only_when_gated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        handlers = _handlers(_graph_auth())
        request = SimpleNamespace(method="GET", session={}, headers={}, cookies={})

        assert 'name="invite_code"' not in to_xml(handlers["/register"](request=request))

        monkeypatch.setenv("SIGNUP_INVITE_CODE", "sekrit")
        assert 'name="invite_code"' in to_xml(handlers["/register"](request=request))
