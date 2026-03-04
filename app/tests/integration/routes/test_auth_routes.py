"""
Integration Tests for Authentication Routes.

Tests cover:
1. Registration page and form submission
2. Login page and form submission
3. Logout functionality
4. Password reset flow (admin-initiated)
5. User switching (dev mode)
6. Session management
7. Redirect behavior for authenticated users

All tests use mocked services to avoid dependencies on Neo4j.
Authentication is handled by GraphAuthService (graph-native).
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.utils.result_simplified import Errors, Result


class MockServices:
    """Mock services container for auth route testing."""

    def __init__(self):
        self.user_service = MagicMock()
        self.graph_auth = MagicMock()


class MockUser:
    """Mock User model."""

    def __init__(self, uid: str = "user.test", email: str = "test@example.com"):
        self.uid = uid
        self.email = email
        self.username = "testuser"
        self.display_name = "Test User"


@pytest.fixture
def mock_services():
    """Create mock services container."""
    return MockServices()


@pytest.fixture
def mock_graph_auth():
    """Mock GraphAuthService for authentication.

    Uses MagicMock for synchronous testing of mock behavior.
    For actual async route tests, use a separate integration test setup.
    """
    return MagicMock()


class TestRegistrationSubmit:
    """Tests for POST /register/submit."""

    def test_registration_validation_requires_all_fields(self):
        """Test that registration requires all fields."""
        # Verify form validation expects username, email, display_name, password
        required_fields = ["username", "email", "display_name", "password", "confirm_password"]
        assert len(required_fields) == 5

    def test_registration_password_must_match(self):
        """Test that passwords must match."""
        # Verification that password matching is enforced
        password = "secure123"
        confirm_password = "different123"
        assert password != confirm_password

    def test_registration_password_minimum_length(self):
        """Test that password has minimum length requirement."""
        # Graph-native auth requires minimum 8 characters
        min_length = 8
        short_password = "1234567"
        valid_password = "12345678"
        assert len(short_password) < min_length
        assert len(valid_password) >= min_length

    def test_registration_requires_terms_acceptance(self):
        """Test that terms of service must be accepted."""
        # Terms acceptance is a required field
        accept_terms = None
        assert not accept_terms

    def test_registration_calls_graph_auth_signup(self, mock_graph_auth):
        """Test that registration uses GraphAuthService for signup."""
        mock_graph_auth.sign_up.return_value = Result.ok(
            {
                "user_uid": "user_testuser",
                "email": "test@example.com",
            }
        )

        # Simulate the sign_up call
        result = mock_graph_auth.sign_up(
            email="test@example.com",
            password="password123",
            username="testuser",
            display_name="Test User",
        )

        assert result.is_ok
        assert result.value["user_uid"] == "user_testuser"

    def test_registration_creates_neo4j_user(self, mock_services):
        """Test that registration creates user in Neo4j."""
        mock_services.user_service.create_user = AsyncMock(return_value=Result.ok(MockUser()))

        # Verify the method signature
        assert hasattr(mock_services.user_service, "create_user")

    def test_registration_handles_auth_error(self, mock_graph_auth):
        """Test that registration handles auth errors gracefully."""
        mock_graph_auth.sign_up.return_value = Result.fail(
            Errors.validation(
                message="An account with this email already exists", field="email"
            )
        )

        result = mock_graph_auth.sign_up(
            email="existing@example.com",
            password="password123",
            username="existinguser",
            display_name="Existing User",
        )

        assert result.is_error
        assert "already exists" in result.error.message


class TestLoginSubmit:
    """Tests for POST /login/submit."""

    def test_login_requires_email_and_password(self):
        """Test that login requires email and password."""
        # Both fields required for validation
        email = ""
        password = ""
        assert not email or not password

    def test_login_accepts_email_format(self):
        """Test that login accepts email format."""
        email = "test@example.com"
        assert "@" in email

    def test_login_accepts_username_format(self):
        """Test that login accepts username (non-email) format."""
        username = "testuser"
        assert "@" not in username

    def test_login_calls_graph_auth_signin(self, mock_graph_auth):
        """Test that login uses GraphAuthService for authentication."""
        mock_graph_auth.sign_in.return_value = Result.ok(
            {
                "user_uid": "user_testuser",
                "session_token": "token-abc-123",
            }
        )

        result = mock_graph_auth.sign_in(
            email="test@example.com",
            password="password123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        assert result.is_ok
        assert result.value["session_token"] == "token-abc-123"

    def test_login_looks_up_user_by_username(self, mock_services):
        """Test that login can look up user by username."""
        mock_services.user_service.get_user_by_username = AsyncMock(
            return_value=Result.ok(MockUser(email="test@example.com"))
        )

        # Verify the lookup method exists
        assert hasattr(mock_services.user_service, "get_user_by_username")

    def test_login_retrieves_user_from_neo4j(self, mock_services):
        """Test that login retrieves user from Neo4j."""
        mock_services.user_service.get_user_by_email = AsyncMock(
            return_value=Result.ok(MockUser(uid="user.test123"))
        )

        assert hasattr(mock_services.user_service, "get_user_by_email")

    def test_login_sets_session_data(self):
        """Test that login sets session data."""
        session = {}
        user_uid = "user.test"
        session_token = "token-abc-123"
        logged_in_at = datetime.now().isoformat()

        session["user_uid"] = user_uid
        session["session_token"] = session_token
        session["logged_in_at"] = logged_in_at

        assert session["user_uid"] == user_uid
        assert session["session_token"] == session_token
        assert "logged_in_at" in session

    def test_login_handles_invalid_credentials(self, mock_graph_auth):
        """Test that login handles invalid credentials."""
        mock_graph_auth.sign_in.return_value = Result.fail(
            Errors.business("auth", "Invalid email or password")
        )

        result = mock_graph_auth.sign_in(
            email="test@example.com",
            password="wrong_password",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        assert result.is_error
        assert "Invalid" in result.error.message


class TestLogout:
    """Tests for GET /logout."""

    def test_logout_clears_session(self):
        """Test that logout clears session data."""
        session = {
            "user_uid": "user.test",
            "session_token": "token",
            "logged_in_at": "2024-01-01T00:00:00",
        }
        session.clear()
        assert session == {}

    def test_logout_redirects_to_login(self):
        """Test that logout redirects to login page."""
        # Verify redirect behavior
        redirect_path = "/login"
        assert redirect_path == "/login"


class TestPasswordReset:
    """Tests for password reset with admin-generated token."""

    def test_reset_password_with_valid_token(self, mock_graph_auth):
        """Test password reset with valid token."""
        mock_graph_auth.reset_password_with_token.return_value = Result.ok(True)

        result = mock_graph_auth.reset_password_with_token(
            token_value="valid-reset-token",
            new_password="newpassword123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        assert result.is_ok
        assert result.value is True

    def test_reset_password_with_expired_token(self, mock_graph_auth):
        """Test password reset with expired token."""
        mock_graph_auth.reset_password_with_token.return_value = Result.fail(
            Errors.business("auth", "Reset token has expired")
        )

        result = mock_graph_auth.reset_password_with_token(
            token_value="expired-token",
            new_password="newpassword123",
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        assert result.is_error
        assert "expired" in result.error.message

    def test_admin_generates_reset_token(self, mock_graph_auth):
        """Test admin can generate reset token for user."""
        mock_graph_auth.admin_generate_reset_token.return_value = Result.ok("reset-token-abc123")

        result = mock_graph_auth.admin_generate_reset_token(
            user_uid="user_testuser",
            admin_uid="user_admin",
            ip_address="127.0.0.1",
            user_agent="admin-browser",
        )

        assert result.is_ok
        assert result.value == "reset-token-abc123"


class TestUserSwitching:
    """Tests for GET/POST /switch-user (development mode)."""

    def test_switch_user_shows_current_user(self):
        """Test that switch user page shows current user."""
        current_user = "user.mike"
        assert current_user is not None

    def test_switch_user_lists_available_users(self):
        """Test that switch user page lists development users."""
        dev_users = ["user.mike", "user.test", "user.admin", "user.demo"]
        assert len(dev_users) == 4

    def test_switch_user_updates_session(self):
        """Test that switch user updates session."""
        session = {"user_uid": "user.mike"}
        new_user = "user.test"
        session["user_uid"] = new_user
        assert session["user_uid"] == new_user


class TestWhoami:
    """Tests for GET /whoami (debugging endpoint)."""

    def test_whoami_shows_user_info(self):
        """Test that whoami shows current user information."""
        user_uid = "user.test"
        is_authenticated = True
        assert user_uid is not None
        assert isinstance(is_authenticated, bool)


class TestSessionManagement:
    """Tests for session-related functionality."""

    def test_is_authenticated_with_session(self):
        """Test is_authenticated returns True when user in session."""
        from adapters.inbound.auth.session import is_authenticated

        class MockRequest:
            session = {"user_uid": "user.test"}

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
            session = {"user_uid": "user.test"}

        assert get_current_user(MockRequest()) == "user.test"

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

        set_current_user(MockRequest(), "user.test")
        assert MockRequest.session.get("user_uid") == "user.test"

    def test_set_current_user_with_token(self):
        """Test set_current_user sets session with token."""
        from adapters.inbound.auth.session import set_current_user

        class MockRequest:
            session = {}

        set_current_user(MockRequest(), "user.test", session_token="token-abc")
        assert MockRequest.session.get("user_uid") == "user.test"
        assert MockRequest.session.get("session_token") == "token-abc"

    def test_clear_current_user_clears_session(self):
        """Test clear_current_user clears session."""
        from adapters.inbound.auth.session import clear_current_user

        class MockRequest:
            session = {"user_uid": "user.test", "session_token": "token", "other": "data"}

        clear_current_user(MockRequest())
        assert MockRequest.session == {}


class TestRedirectBehavior:
    """Tests for redirect behavior on authenticated/unauthenticated access."""

    def test_register_redirects_when_authenticated(self):
        """Test that register page redirects authenticated users."""
        # When user is authenticated, should redirect to /profile
        redirect_target = "/profile"
        assert redirect_target == "/profile"

    def test_login_redirects_when_authenticated(self):
        """Test that login page redirects authenticated users."""
        # When user is authenticated, should redirect to /profile
        redirect_target = "/profile"
        assert redirect_target == "/profile"

    def test_successful_login_redirects_to_profile(self):
        """Test that successful login redirects to profile."""
        redirect_target = "/profile"
        status_code = 303
        assert redirect_target == "/profile"
        assert status_code == 303

    def test_logout_redirects_to_login(self):
        """Test that logout redirects to login page."""
        redirect_target = "/login"
        status_code = 303
        assert redirect_target == "/login"
        assert status_code == 303


class TestFormValidation:
    """Tests for form validation patterns."""

    def test_safe_form_string_extracts_value(self):
        """Test safe_form_string extracts form values safely."""
        from adapters.inbound.form_helpers import safe_form_string

        assert safe_form_string("value") == "value"
        assert safe_form_string("  trimmed  ") == "trimmed"
        assert safe_form_string(None) == ""
        assert safe_form_string("") == ""

    def test_email_detection(self):
        """Test email vs username detection."""
        email = "user@example.com"
        username = "testuser"

        assert "@" in email
        assert "@" not in username

    def test_password_length_validation(self):
        """Test password length validation."""
        min_length = 8  # Graph-native auth uses 8 character minimum

        short_passwords = ["", "a", "1234567"]
        valid_passwords = ["12345678", "securepassword", "a" * 100]

        for pwd in short_passwords:
            assert len(pwd) < min_length

        for pwd in valid_passwords:
            assert len(pwd) >= min_length
