"""
Tests for Session Management.

Tests cover:
1. get_current_user() - Get user from session
2. get_current_user_or_default() - Get user or fallback
3. set_current_user() / clear_current_user() - Session mutation
4. is_authenticated() - Authentication check
5. require_authenticated_user() - Get user or raise HTTPException
6. require_auth() decorator - Route protection with redirect
7. optional_auth() decorator - Optional auth with injection
8. get_session_data() / set_session_data() - Arbitrary session data
9. get_session_middleware_config() - Middleware configuration
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse

from core.auth.session import (
    DEFAULT_DEV_USER,
    clear_current_user,
    get_current_user,
    get_current_user_or_default,
    get_session_data,
    get_session_middleware_config,
    is_authenticated,
    optional_auth,
    require_auth,
    require_authenticated_user,
    set_current_user,
    set_session_data,
)


class MockRequest:
    """Mock Starlette Request with session support."""

    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}
        self.url = MagicMock()
        self.url.path = "/test"


class TestGetCurrentUser:
    """Tests for get_current_user()."""

    def test_returns_user_uid_when_authenticated(self):
        """Test that user_uid is returned when present in session."""
        request = MockRequest(session={"user_uid": "user.test"})
        result = get_current_user(request)
        assert result == "user.test"

    def test_returns_none_when_not_authenticated(self):
        """Test that None is returned when session is empty."""
        request = MockRequest(session={})
        result = get_current_user(request)
        assert result is None

    def test_returns_none_when_session_missing(self):
        """Test that None is returned when request has no session attribute."""
        request = MagicMock(spec=[])  # No session attribute
        result = get_current_user(request)
        assert result is None

    def test_returns_none_on_exception(self):
        """Test that None is returned when session access raises exception."""
        request = MagicMock()
        request.session.get.side_effect = Exception("Session error")
        result = get_current_user(request)
        assert result is None


class TestGetCurrentUserOrDefault:
    """Tests for get_current_user_or_default()."""

    def test_returns_user_uid_when_authenticated(self):
        """Test that session user is returned when present."""
        request = MockRequest(session={"user_uid": "user.mike"})
        result = get_current_user_or_default(request)
        assert result == "user.mike"

    def test_returns_default_when_not_authenticated(self):
        """Test that default user is returned when no session."""
        request = MockRequest(session={})
        result = get_current_user_or_default(request)
        assert result == DEFAULT_DEV_USER

    def test_returns_custom_default(self):
        """Test that custom default user can be specified."""
        request = MockRequest(session={})
        result = get_current_user_or_default(request, default="custom.user")
        assert result == "custom.user"


class TestSetCurrentUser:
    """Tests for set_current_user()."""

    def test_sets_user_uid_in_session(self):
        """Test that user_uid is stored in session."""
        request = MockRequest()
        set_current_user(request, "user.test")
        assert request.session["user_uid"] == "user.test"

    def test_sets_logged_in_at_timestamp(self):
        """Test that logged_in_at timestamp is stored."""
        request = MockRequest()
        set_current_user(request, "user.test")
        assert "logged_in_at" in request.session
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(request.session["logged_in_at"])

    def test_handles_missing_session(self):
        """Test that missing session is handled gracefully."""
        request = MagicMock(spec=[])  # No session attribute
        # Should not raise
        set_current_user(request, "user.test")


class TestClearCurrentUser:
    """Tests for clear_current_user()."""

    def test_clears_session(self):
        """Test that session is cleared on logout."""
        request = MockRequest(session={"user_uid": "user.test", "other": "data"})
        clear_current_user(request)
        assert request.session == {}

    def test_handles_missing_session(self):
        """Test that missing session is handled gracefully."""
        request = MagicMock(spec=[])  # No session attribute
        # Should not raise
        clear_current_user(request)


class TestIsAuthenticated:
    """Tests for is_authenticated()."""

    def test_returns_true_when_authenticated(self):
        """Test that True is returned when user is in session."""
        request = MockRequest(session={"user_uid": "user.test"})
        assert is_authenticated(request) is True

    def test_returns_false_when_not_authenticated(self):
        """Test that False is returned when no user in session."""
        request = MockRequest(session={})
        assert is_authenticated(request) is False


class TestRequireAuthenticatedUser:
    """Tests for require_authenticated_user()."""

    def test_returns_user_uid_when_authenticated(self):
        """Test that user_uid is returned when authenticated."""
        request = MockRequest(session={"user_uid": "user.test"})
        result = require_authenticated_user(request)
        assert result == "user.test"

    def test_raises_401_when_not_authenticated(self):
        """Test that HTTPException 401 is raised when not authenticated."""
        request = MockRequest(session={})
        with pytest.raises(HTTPException) as exc_info:
            require_authenticated_user(request)
        assert exc_info.value.status_code == 401
        assert "Authentication required" in str(exc_info.value.detail)


class TestRequireAuthDecorator:
    """Tests for require_auth() decorator."""

    @pytest.mark.asyncio
    async def test_allows_authenticated_user(self):
        """Test that decorated function executes when authenticated."""

        @require_auth()
        async def protected_route(request):
            return "success"

        request = MockRequest(session={"user_uid": "user.test"})
        result = await protected_route(request)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_redirects_unauthenticated_user(self):
        """Test that unauthenticated user is redirected."""

        @require_auth()
        async def protected_route(request):
            return "success"

        request = MockRequest(session={})
        result = await protected_route(request)
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_redirects_to_login_by_default(self):
        """Test that default redirect is to /login."""

        @require_auth()
        async def protected_route(request):
            return "success"

        request = MockRequest(session={})
        result = await protected_route(request)
        assert isinstance(result, RedirectResponse)
        # Check redirect URL by examining headers
        assert result.headers.get("location") == "/login"

    @pytest.mark.asyncio
    async def test_custom_redirect_url(self):
        """Test that custom redirect URL can be specified."""

        @require_auth(redirect_to="/custom-login")
        async def protected_route(request):
            return "success"

        request = MockRequest(session={})
        result = await protected_route(request)
        assert isinstance(result, RedirectResponse)
        assert result.headers.get("location") == "/custom-login"


class TestOptionalAuthDecorator:
    """Tests for optional_auth() decorator."""

    @pytest.mark.asyncio
    async def test_injects_user_from_session(self):
        """Test that user_uid from session is injected."""

        @optional_auth()
        async def route(request, user_uid: str):
            return user_uid

        request = MockRequest(session={"user_uid": "user.from_session"})
        result = await route(request)
        assert result == "user.from_session"

    @pytest.mark.asyncio
    async def test_injects_default_when_no_session(self):
        """Test that default user is injected when no session."""

        @optional_auth()
        async def route(request, user_uid: str):
            return user_uid

        request = MockRequest(session={})
        result = await route(request)
        assert result == DEFAULT_DEV_USER

    @pytest.mark.asyncio
    async def test_custom_default_user(self):
        """Test that custom default user can be specified."""

        @optional_auth(default_user="custom.default")
        async def route(request, user_uid: str):
            return user_uid

        request = MockRequest(session={})
        result = await route(request)
        assert result == "custom.default"


class TestGetSessionData:
    """Tests for get_session_data()."""

    def test_returns_session_value(self):
        """Test that session value is returned."""
        request = MockRequest(session={"custom_key": "custom_value"})
        result = get_session_data(request, "custom_key")
        assert result == "custom_value"

    def test_returns_default_when_key_missing(self):
        """Test that default is returned when key not in session."""
        request = MockRequest(session={})
        result = get_session_data(request, "missing_key", default="default_value")
        assert result == "default_value"

    def test_returns_none_default(self):
        """Test that None is default default."""
        request = MockRequest(session={})
        result = get_session_data(request, "missing_key")
        assert result is None

    def test_handles_missing_session(self):
        """Test that missing session returns default."""
        request = MagicMock(spec=[])  # No session attribute
        result = get_session_data(request, "key", default="fallback")
        assert result == "fallback"


class TestSetSessionData:
    """Tests for set_session_data()."""

    def test_sets_session_value(self):
        """Test that value is stored in session."""
        request = MockRequest()
        set_session_data(request, "custom_key", "custom_value")
        assert request.session["custom_key"] == "custom_value"

    def test_handles_missing_session(self):
        """Test that missing session is handled gracefully."""
        request = MagicMock(spec=[])  # No session attribute
        # Should not raise
        set_session_data(request, "key", "value")


class TestGetSessionMiddlewareConfig:
    """Tests for get_session_middleware_config()."""

    def test_returns_config_dict(self):
        """Test that config dict is returned."""
        config = get_session_middleware_config()
        assert isinstance(config, dict)

    def test_contains_required_keys(self):
        """Test that config contains required middleware keys."""
        config = get_session_middleware_config()
        assert "secret_key" in config
        assert "session_cookie" in config
        assert "max_age" in config

    def test_session_cookie_name(self):
        """Test that session cookie name is correct."""
        config = get_session_middleware_config()
        assert config["session_cookie"] == "skuel_session"

    def test_max_age_is_30_days(self):
        """Test that max age is 30 days in seconds."""
        config = get_session_middleware_config()
        expected_max_age = 60 * 60 * 24 * 30  # 30 days in seconds
        assert config["max_age"] == expected_max_age

    def test_secret_key_from_environment(self):
        """Test that secret key is read from environment when set."""
        with patch.dict("os.environ", {"SESSION_SECRET_KEY": "test_secret_key"}):
            config = get_session_middleware_config()
            assert config["secret_key"] == "test_secret_key"

    def test_generates_secret_when_not_in_env(self):
        """Test that secret is generated when not in environment."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove SESSION_SECRET_KEY if present
            import os

            os.environ.pop("SESSION_SECRET_KEY", None)
            config = get_session_middleware_config()
            assert config["secret_key"] is not None
            assert len(config["secret_key"]) > 20  # Should be a secure random key

    def test_https_only_in_production(self):
        """Test that https_only is True in production."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            config = get_session_middleware_config()
            assert config["https_only"] is True

    def test_https_only_false_in_development(self):
        """Test that https_only is False in development."""
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            config = get_session_middleware_config()
            assert config["https_only"] is False

    def test_same_site_is_strict(self):
        """Test that same_site is strict for CSRF protection (January 2026 hardening)."""
        config = get_session_middleware_config()
        assert config["same_site"] == "strict"


class TestDefaultDevUser:
    """Tests for DEFAULT_DEV_USER constant."""

    def test_default_dev_user_is_user_mike(self):
        """Test that default dev user is user.mike."""
        assert DEFAULT_DEV_USER == "user_mike"
