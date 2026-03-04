"""
Tests for Authentication and Session Management
================================================

Tests the session-based authentication system including:
- Session middleware configuration
- get_current_user() functionality
- Login/logout flows
- Session data storage
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from adapters.inbound.auth import (
    DEFAULT_DEV_USER,
    clear_current_user,
    get_current_user,
    get_current_user_or_default,
    get_session_data,
    get_session_middleware_config,
    is_authenticated,
    set_current_user,
    set_session_data,
)


@pytest.fixture
def mock_request_with_session() -> MagicMock:
    """Create mock request with session support."""
    request = MagicMock()
    request.session = {}
    return request


@pytest.fixture
def mock_request_no_session() -> MagicMock:
    """Create mock request without session (middleware not installed)."""
    request = MagicMock()
    # Remove session attribute
    delattr(request, "session")
    return request


@pytest.fixture
def authenticated_request() -> MagicMock:
    """Create mock request with authenticated session."""
    request = MagicMock()
    request.session = {"user_uid": "user.test", "logged_in_at": datetime.now().isoformat()}
    return request


class TestGetCurrentUser:
    """Tests for get_current_user() function."""

    def test_get_user_from_session(self, authenticated_request):
        """Test getting user from active session."""
        user_uid = get_current_user(authenticated_request)
        assert user_uid == "user.test"

    def test_no_session_returns_none(self, mock_request_with_session):
        """Test that empty session returns None."""
        user_uid = get_current_user(mock_request_with_session)
        assert user_uid is None

    def test_no_session_attribute_returns_none(self, mock_request_no_session):
        """Test that request without session attribute returns None."""
        user_uid = get_current_user(mock_request_no_session)
        assert user_uid is None


class TestGetCurrentUserOrDefault:
    """Tests for get_current_user_or_default() function."""

    def test_returns_user_from_session(self, authenticated_request):
        """Test returns user from session when authenticated."""
        user_uid = get_current_user_or_default(authenticated_request)
        assert user_uid == "user.test"

    def test_returns_default_when_no_session(self, mock_request_with_session):
        """Test returns default user when no session."""
        user_uid = get_current_user_or_default(mock_request_with_session)
        assert user_uid == DEFAULT_DEV_USER

    def test_returns_custom_default(self, mock_request_with_session):
        """Test returns custom default when specified."""
        user_uid = get_current_user_or_default(mock_request_with_session, default="user.custom")
        assert user_uid == "user.custom"


class TestSetCurrentUser:
    """Tests for set_current_user() function."""

    def test_sets_user_in_session(self, mock_request_with_session):
        """Test setting user creates session data."""
        set_current_user(mock_request_with_session, "user.newuser")

        assert mock_request_with_session.session["user_uid"] == "user.newuser"
        assert "logged_in_at" in mock_request_with_session.session

    def test_overwrites_existing_session(self, authenticated_request):
        """Test setting user overwrites existing session."""
        set_current_user(authenticated_request, "user.different")

        assert authenticated_request.session["user_uid"] == "user.different"

    def test_no_session_attribute_does_nothing(self, mock_request_no_session):
        """Test gracefully handles request without session."""
        # Should not raise exception
        set_current_user(mock_request_no_session, "user.test")


class TestClearCurrentUser:
    """Tests for clear_current_user() function."""

    def test_clears_session_data(self, authenticated_request):
        """Test clearing session removes all data."""
        clear_current_user(authenticated_request)

        assert len(authenticated_request.session) == 0
        assert "user_uid" not in authenticated_request.session

    def test_clears_empty_session(self, mock_request_with_session):
        """Test clearing empty session doesn't raise error."""
        clear_current_user(mock_request_with_session)
        assert len(mock_request_with_session.session) == 0

    def test_no_session_attribute_does_nothing(self, mock_request_no_session):
        """Test gracefully handles request without session."""
        # Should not raise exception
        clear_current_user(mock_request_no_session)


class TestIsAuthenticated:
    """Tests for is_authenticated() function."""

    def test_authenticated_when_session_exists(self, authenticated_request):
        """Test returns True when user session exists."""
        assert is_authenticated(authenticated_request) is True

    def test_not_authenticated_when_no_session(self, mock_request_with_session):
        """Test returns False when no session."""
        assert is_authenticated(mock_request_with_session) is False

    def test_not_authenticated_without_session_attribute(self, mock_request_no_session):
        """Test returns False when no session attribute."""
        assert is_authenticated(mock_request_no_session) is False


class TestSessionData:
    """Tests for session data helpers."""

    def test_get_session_data(self, authenticated_request):
        """Test getting arbitrary session data."""
        authenticated_request.session["custom_key"] = "custom_value"

        value = get_session_data(authenticated_request, "custom_key")
        assert value == "custom_value"

    def test_get_session_data_default(self, mock_request_with_session):
        """Test getting session data with default."""
        value = get_session_data(mock_request_with_session, "missing_key", default="default_val")
        assert value == "default_val"

    def test_get_session_data_no_session_attribute(self, mock_request_no_session):
        """Test getting session data when no session attribute."""
        value = get_session_data(mock_request_no_session, "key", default="default")
        assert value == "default"

    def test_set_session_data(self, mock_request_with_session):
        """Test setting arbitrary session data."""
        set_session_data(mock_request_with_session, "test_key", "test_value")

        assert mock_request_with_session.session["test_key"] == "test_value"

    def test_set_session_data_no_session_attribute(self, mock_request_no_session):
        """Test setting session data when no session attribute."""
        # Should not raise exception
        set_session_data(mock_request_no_session, "key", "value")


class TestSessionMiddlewareConfig:
    """Tests for session middleware configuration."""

    def test_config_contains_required_keys(self):
        """Test configuration has all required keys."""
        config = get_session_middleware_config()

        assert "secret_key" in config
        assert "session_cookie" in config
        assert "max_age" in config
        assert "https_only" in config
        assert "same_site" in config

    def test_secret_key_is_generated_when_not_set(self, monkeypatch):
        """Test secret key is generated when not in environment."""
        monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)

        config = get_session_middleware_config()

        assert config["secret_key"] is not None
        assert len(config["secret_key"]) > 20  # Should be a decent length

    def test_secret_key_from_environment(self, monkeypatch):
        """Test secret key is read from environment."""
        monkeypatch.setenv("SESSION_SECRET_KEY", "test_secret_key_12345")

        config = get_session_middleware_config()

        assert config["secret_key"] == "test_secret_key_12345"

    def test_https_only_in_production(self, monkeypatch):
        """Test HTTPS-only enabled in production."""
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "production")
        monkeypatch.setenv("SESSION_SECRET_KEY", "test-key-for-prod")

        config = get_session_middleware_config()

        assert config["https_only"] is True

    def test_https_not_required_in_development(self, monkeypatch):
        """Test HTTPS not required in development."""
        monkeypatch.setenv("SKUEL_ENVIRONMENT", "development")

        config = get_session_middleware_config()

        assert config["https_only"] is False


class TestAuthenticationFlow:
    """Integration tests for complete authentication flow."""

    def test_complete_login_flow(self, mock_request_with_session):
        """Test complete login flow."""
        # Start unauthenticated
        assert is_authenticated(mock_request_with_session) is False
        assert get_current_user(mock_request_with_session) is None

        # Log in
        set_current_user(mock_request_with_session, "user.test")

        # Now authenticated
        assert is_authenticated(mock_request_with_session) is True
        assert get_current_user(mock_request_with_session) == "user.test"

    def test_complete_logout_flow(self, authenticated_request):
        """Test complete logout flow."""
        # Start authenticated
        assert is_authenticated(authenticated_request) is True
        assert get_current_user(authenticated_request) == "user.test"

        # Log out
        clear_current_user(authenticated_request)

        # Now unauthenticated
        assert is_authenticated(authenticated_request) is False
        assert get_current_user(authenticated_request) is None

    def test_user_switch_flow(self, authenticated_request):
        """Test switching users."""
        # Start as user.test
        assert get_current_user(authenticated_request) == "user.test"

        # Switch to different user
        set_current_user(authenticated_request, "user.different")

        # Now logged in as different user
        assert get_current_user(authenticated_request) == "user.different"
        assert is_authenticated(authenticated_request) is True


class TestDevelopmentHelpers:
    """Tests for development-friendly helpers."""

    def test_default_user_fallback(self, mock_request_with_session):
        """Test development mode fallback to default user."""
        # No session
        user_uid = get_current_user_or_default(mock_request_with_session)

        # Should return default dev user
        assert user_uid == DEFAULT_DEV_USER

    def test_development_mode_always_has_user(self, mock_request_with_session):
        """Test development mode never returns None for user."""
        # Multiple calls should always return a user
        for _ in range(5):
            user_uid = get_current_user_or_default(mock_request_with_session)
            assert user_uid is not None
            assert isinstance(user_uid, str)
            assert len(user_uid) > 0
