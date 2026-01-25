"""
Test Fixtures for SKUEL GraphQL Tests
======================================

Provides authenticated test client for GraphQL API tests.

Setup:
- Loads .env for credentials (OpenAI, Deepgram, Neo4j)
- Uses ASGITransport (in-process) to avoid HTTP/cookie issues
- Creates test user via registration
- Authenticates via /login endpoint
- Provides AsyncClient with valid session cookie
"""

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

# Load .env before any other imports (required for integration tests)
from dotenv import load_dotenv

if TYPE_CHECKING:
    from collections.abc import Generator

    from httpx import TestClient

load_dotenv()


@pytest.fixture(scope="session")
def event_loop():
    """
    Create session-scoped event loop for async tests.

    Required for session-scoped async fixtures.
    """
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def skuel_app():
    """
    Bootstrap SKUEL app once per test session.

    This creates a single app instance with all services initialized.
    Using session scope ensures session middleware works correctly.
    """
    from scripts.dev.bootstrap import bootstrap_skuel

    container = await bootstrap_skuel()
    yield container.app

    # Cleanup
    await container.services.cleanup()


@pytest.fixture
def authenticated_client(skuel_app) -> "Generator[TestClient, None, None]":
    """
    Create authenticated TestClient for API testing.

    Uses Starlette's TestClient which properly handles sessions and cookies.

    This fixture:
    1. Creates a test user (registers if needed)
    2. Logs in to get session cookie
    3. Returns TestClient with authenticated session

    Usage:
        def test_graphql_query(authenticated_client):
            response = authenticated_client.post(
                "/graphql",
                json={"query": "..."}
            )
            assert response.status_code == 200
    """
    from starlette.testclient import TestClient

    # Use the session-scoped app fixture
    app = skuel_app

    # Test user credentials
    test_username = "test_graphql_user"
    test_email = "test_graphql@example.com"
    test_password = "test_password_123"

    # Use TestClient (synchronous but handles cookies correctly)
    with TestClient(app, follow_redirects=True) as client:
        # Step 1: Try to register test user (idempotent - fails if exists)
        register_response = client.post(
            "/register",
            data={
                "username": test_username,
                "email": test_email,
                "display_name": "Test GraphQL User",
                "password": test_password,
                "confirm_password": test_password,
                "accept_terms": "on",
            },
        )

        print("\n🔍 Registration Response Debug:")
        print(f"   Status: {register_response.status_code}")
        print(f"   URL: {register_response.url}")
        print(f"   Cookies after registration: {dict(client.cookies)}")

        # Check if registration showed an error message
        if "error" in register_response.text.lower() or "failed" in register_response.text.lower():
            # Extract error message from HTML
            import re

            error_match = re.search(r"error[^<>]{0,200}", register_response.text, re.IGNORECASE)
            if error_match:
                print(f"   Registration error: {error_match.group()[:100]}")

        # If registration succeeded, we should be logged in and redirected to home
        if register_response.status_code == 200 and register_response.url.path == "/":
            print("   ✅ Registration succeeded - already logged in!")
            # Skip login step - already authenticated
            if "skuel_session" in client.cookies:
                print("   ✅ Session cookie present from registration")
                yield client
                return
            else:
                print("   ⚠️ Registration succeeded but no cookie - will try login")

        # If registration failed (user exists), that's okay - proceed to login
        print("   Registration response (user may already exist) - will try login")

        # Step 2: Log in to get session cookie
        login_response = client.post(
            "/login", data={"username": test_username, "password": test_password}
        )

        # Debug: Print login response details
        print("\n🔍 Login Response Debug:")
        print(f"   Status: {login_response.status_code}")
        print(f"   URL: {login_response.url}")
        print(f"   Headers: {dict(login_response.headers)}")
        print(f"   Client cookies: {dict(client.cookies)}")

        if hasattr(login_response, "history") and login_response.history:
            print(f"   Redirect history: {len(login_response.history)} redirects")
            for i, resp in enumerate(login_response.history):
                print(f"     {i + 1}. {resp.status_code} -> {resp.headers.get('location', 'N/A')}")
                if "set-cookie" in resp.headers:
                    cookie_val = resp.headers["set-cookie"]
                    print(f"        Set-Cookie: {cookie_val[:80]}...")

        # Check login succeeded (should redirect to home with status 200)
        if login_response.status_code != 200:
            raise RuntimeError(
                f"Login failed with status {login_response.status_code}. "
                f"Response: {login_response.text[:500]}"
            )

        # Step 3: Verify session cookie was set
        # With ASGITransport, cookies are automatically handled
        if "skuel_session" not in client.cookies:
            raise RuntimeError(
                f"Session cookie not found after login. "
                f"This should not happen with ASGITransport. "
                f"Cookies: {dict(client.cookies)}"
            )

        # Step 4: Return the authenticated client
        # The client already has the session cookie set from the login flow
        yield client


@pytest.fixture
def authenticated_client_simple(skuel_app) -> "Generator[TestClient, None, None]":
    """
    Simplified authenticated client that bypasses login.

    Tests use the default development user (user.mike) that's already
    configured in the application. No async database operations needed.

    Usage:
        def test_graphql_query(authenticated_client_simple):
            response = authenticated_client_simple.post(
                "/graphql",
                json={"query": "..."}
            )
            assert response.status_code == 200
    """
    from starlette.testclient import TestClient

    # Create TestClient - uses default dev user
    # No async database operations needed - avoids event loop issues
    with TestClient(skuel_app) as client:
        yield client


@pytest.fixture
def test_user_uid() -> str:
    """
    Test user UID for use in GraphQL queries.

    This matches the user created by authenticated_client fixture.
    """
    return "test_graphql_user"
