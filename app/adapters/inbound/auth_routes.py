"""
Authentication Routes for SKUEL
================================

Graph-native authentication system with registration and login.

Features:
- User registration with bcrypt password hashing
- Login with username/email via Neo4j
- Graph-native session management
- Admin-initiated password reset

Design:
- All authentication state lives in Neo4j
- Sessions stored as Neo4j nodes with audit trail
- No external authentication dependencies

Security:
- Debug endpoints (/debug-session, /whoami) are admin-only in production
- User switching removed entirely for security

Version: 2.1.0
Date: 2026-01-21
"""

from typing import Any

from fasthtml.common import H1, H2, A, P
from starlette.requests import Request
from starlette.responses import RedirectResponse

# Import auth components
from components.auth_components import AuthComponents
from core.auth import (
    clear_current_user,
    get_current_user,
    is_authenticated,
    require_admin,
    set_current_user,
)
from core.ui.daisy_components import Card, CardBody, Div
from core.utils.form_helpers import safe_form_string
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.auth")


def create_auth_routes(_app, rt, services):
    """
    Create authentication routes.

    Routes:
    - GET /register - Show registration page
    - POST /register - Process registration
    - GET /login - Show login page
    - POST /login - Process login
    - GET /logout - Process logout
    - GET /forgot-password - Show password reset page
    - POST /forgot-password - Process password reset
    - GET /debug-session - Debug session state (admin-only)
    - GET /whoami - Show current user info (admin-only)

    Security:
    - /switch-user REMOVED (January 2026) - security vulnerability
    - Debug endpoints require admin role
    """

    # ========================================================================
    # REGISTRATION
    # ========================================================================

    @rt("/register")
    async def register_page(request: Request) -> Any:
        """Show registration page"""
        # If already logged in, redirect to profile hub
        if is_authenticated(request):
            return RedirectResponse("/profile", status_code=303)

        return AuthComponents.render_registration_page()

    @rt("/register/submit")
    async def register_submit(request: Request) -> Any:
        """Process registration with graph-native auth"""
        logger.info("POST /register/submit - Registration form submitted")
        try:
            form_data = await request.form()

            # Extract form data
            username = safe_form_string(form_data.get("username"))
            email = safe_form_string(form_data.get("email"))
            display_name = safe_form_string(form_data.get("display_name"))
            password = safe_form_string(form_data.get("password"))
            confirm_password = safe_form_string(form_data.get("confirm_password"))
            accept_terms = form_data.get("accept_terms")

            # Validation
            if not all([username, email, display_name, password, confirm_password]):
                logger.warning("Validation failed: Missing required fields")
                return AuthComponents.render_registration_page(
                    error_message="All fields are required"
                )

            if password != confirm_password:
                logger.warning("Validation failed: Passwords don't match")
                return AuthComponents.render_registration_page(
                    error_message="Passwords do not match"
                )

            if len(password) < 8:  # Graph-native uses 8 character minimum
                logger.warning("Validation failed: Password too short")
                return AuthComponents.render_registration_page(
                    error_message="Password must be at least 8 characters"
                )

            if not accept_terms:
                logger.warning("Validation failed: Terms not accepted")
                return AuthComponents.render_registration_page(
                    error_message="You must accept the Terms of Service"
                )

            logger.info("All validation checks passed")

            # Check if graph_auth service is available
            if not services.graph_auth:
                logger.error("Graph auth service not available")
                return AuthComponents.render_registration_page(
                    error_message="Authentication service unavailable - please try again later"
                )

            # Register with graph-native auth
            logger.info(f"Registering user: {username} ({email})")
            auth_result = await services.graph_auth.sign_up(
                email=email,
                password=password,
                username=username,
                display_name=display_name,
            )

            if auth_result.is_error:
                error_msg = (
                    auth_result.error.message if auth_result.error else "Registration failed"
                )
                logger.warning(f"Registration failed for {email}: {error_msg}")
                return AuthComponents.render_registration_page(error_message=error_msg)

            user_data = auth_result.value
            logger.info(f"New user registered: {username} ({user_data['user_uid']})")

            # Get client info for session
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Auto-login after registration
            login_result = await services.graph_auth.sign_in(
                email=email,
                password=password,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if login_result.is_error:
                # Registration succeeded but auto-login failed - redirect to login
                logger.warning("Auto-login after registration failed")
                return RedirectResponse("/login?registered=true", status_code=303)

            session_data = login_result.value

            # Set session with token
            request.session.clear()
            user = session_data["user"]
            set_current_user(
                request,
                user_uid=session_data["user_uid"],
                session_token=session_data["session_token"],
                is_admin=user.can_manage_users(),
            )

            logger.info(
                f"User registered and logged in: {username} (admin={user.can_manage_users()})"
            )
            return RedirectResponse("/profile", status_code=303)

        except Exception as e:
            logger.error(f"Registration error: {e}")
            return AuthComponents.render_registration_page(
                error_message=f"An error occurred: {e!s}"
            )

    # ========================================================================
    # LOGIN
    # ========================================================================

    @rt("/login")
    async def login_page(request: Request) -> Any:
        """Show login page"""
        # If already logged in, redirect to profile hub
        if is_authenticated(request):
            return RedirectResponse("/profile", status_code=303)

        return AuthComponents.render_login_page()

    @rt("/login/submit")
    async def login_submit(request: Request) -> Any:
        """Process login with graph-native auth"""
        try:
            form_data = await request.form()

            # Field is named 'username' but can be email
            email_or_username = safe_form_string(form_data.get("username"))
            password = safe_form_string(form_data.get("password"))

            # Validation
            if not email_or_username or not password:
                return AuthComponents.render_login_page(
                    error_message="Email and password are required"
                )

            # Check if graph_auth service is available
            if not services.graph_auth:
                return AuthComponents.render_login_page(
                    error_message="Authentication service unavailable"
                )

            # Determine if input is email or username
            if "@" in email_or_username:
                email = email_or_username
            else:
                # Look up email by username from Neo4j
                user_result = await services.user_service.get_user_by_username(email_or_username)
                if user_result.is_error or not user_result.value:
                    return AuthComponents.render_login_page(
                        error_message="Invalid username or password"
                    )
                email = user_result.value.email

            # Get client info for audit trail
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Authenticate with graph-native auth
            auth_result = await services.graph_auth.sign_in(
                email=email,
                password=password,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if auth_result.is_error:
                error = auth_result.expect_error()
                logger.warning(f"Login failed for {email}: {error.message}")
                return AuthComponents.render_login_page(error_message=error.message)

            session_data = auth_result.value
            user = session_data["user"]

            # Clear old session first
            request.session.clear()

            # Set new session with token
            set_current_user(
                request,
                user_uid=session_data["user_uid"],
                session_token=session_data["session_token"],
                is_admin=user.can_manage_users(),
            )

            logger.info(
                f"User logged in: {email} ({session_data['user_uid']}) (admin={user.can_manage_users()})"
            )
            return RedirectResponse("/profile", status_code=303)

        except Exception as e:
            logger.error(f"Login error: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return AuthComponents.render_login_error(str(e))

    # ========================================================================
    # PASSWORD RESET
    # ========================================================================

    @rt("/forgot-password")
    async def forgot_password_page(_request: Request) -> Any:
        """Show forgot password page with admin contact info"""
        return AuthComponents.render_admin_password_reset_info()

    @rt("/forgot-password")
    async def forgot_password_submit(request: Request) -> Any:
        """Process forgot password request - inform user to contact admin"""
        # In graph-native auth, password reset is admin-initiated
        # Show message to contact administrator
        return AuthComponents.render_admin_password_reset_info()

    # ========================================================================
    # PASSWORD RESET (Token-Based)
    # ========================================================================

    @rt("/reset-password")
    async def reset_password_page(request: Request, token: str = "") -> Any:
        """Show reset password form where users enter token and new password"""
        # If already logged in, redirect to profile hub
        if is_authenticated(request):
            return RedirectResponse("/profile", status_code=303)

        return AuthComponents.render_reset_password_page(token=token)

    @rt("/reset-password/submit")
    async def reset_password_submit(request: Request) -> Any:
        """Process password reset with token"""
        try:
            form_data = await request.form()

            token = safe_form_string(form_data.get("token"))
            password = safe_form_string(form_data.get("password"))
            confirm_password = safe_form_string(form_data.get("confirm_password"))

            # Validation
            if not token:
                return AuthComponents.render_reset_password_page(
                    error_message="Reset token is required"
                )

            if not password or not confirm_password:
                return AuthComponents.render_reset_password_page(
                    error_message="Password fields are required",
                    token=token,
                )

            if password != confirm_password:
                return AuthComponents.render_reset_password_page(
                    error_message="Passwords do not match",
                    token=token,
                )

            if len(password) < 8:
                return AuthComponents.render_reset_password_page(
                    error_message="Password must be at least 8 characters",
                    token=token,
                )

            # Check if graph_auth service is available
            if not services.graph_auth:
                return AuthComponents.render_reset_password_page(
                    error_message="Authentication service unavailable",
                    token=token,
                )

            # Get client info for audit trail
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Reset password with token
            result = await services.graph_auth.reset_password_with_token(
                token_value=token,
                new_password=password,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if result.is_error:
                error = result.expect_error()
                return AuthComponents.render_reset_password_page(
                    error_message=error.message,
                    token=token,
                )

            logger.info("Password reset successfully via token")
            return AuthComponents.render_reset_password_success()

        except Exception as e:
            logger.error(f"Password reset error: {e}")
            return AuthComponents.render_reset_password_page(
                error_message=f"An error occurred: {e!s}"
            )

    # ========================================================================
    # LOGOUT
    # ========================================================================

    @rt("/logout")
    async def logout(request: Request) -> Any:
        """Process logout - invalidate session in Neo4j and clear cookie"""
        user_uid = get_current_user(request)
        session_token = request.session.get("session_token")

        # Invalidate session in Neo4j if we have graph_auth and session_token
        if services.graph_auth and session_token:
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            await services.graph_auth.sign_out(
                session_token=session_token,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Clear cookie session
        clear_current_user(request)

        logger.info(f"User logged out: {user_uid}")

        return RedirectResponse("/login", status_code=303)

    # ========================================================================
    # DEBUG ENDPOINTS (Admin-only)
    # ========================================================================
    # Security: These endpoints expose session internals and are restricted
    # to admin users only as of January 2026.

    def get_user_service():
        """Get user service for admin role checks."""
        return services.user_service

    @rt("/debug-session")
    @require_admin(get_user_service)
    async def debug_session(request, current_user) -> Any:
        """
        Debug route to check session state.

        Security: Admin-only - exposes session internals.
        """
        from fasthtml.common import Pre

        try:
            session_data = dict(request.session)
        except AttributeError:
            session_data = {}
        user_uid = get_current_user(request)

        return Div(
            H1("Session Debug (Admin)"),
            P(f"User UID from helper: {user_uid}"),
            P(f"Session has user_uid: {'user_uid' in session_data}"),
            Pre(str(session_data)),
        )

    @rt("/whoami")
    @require_admin(get_user_service)
    async def whoami(request, current_user) -> Any:
        """
        Show current user info.

        Security: Admin-only - exposes user identity details.
        """
        user_uid = get_current_user(request)
        is_auth = is_authenticated(request)

        return Div(
            H1("Current User (Admin)", cls="text-3xl font-bold mb-6"),
            Card(
                CardBody(
                    H2("Session Information", cls="text-xl font-semibold mb-4"),
                    Div(
                        P("User UID:", cls="font-medium"),
                        P(user_uid or "None", cls="text-gray-600 font-mono"),
                        cls="mb-3",
                    ),
                    Div(
                        P("Authenticated:", cls="font-medium"),
                        P("Yes" if is_auth else "No", cls="text-gray-600"),
                        cls="mb-3",
                    ),
                    Div(
                        P("Session Status:", cls="font-medium"),
                        P(
                            "Active session" if is_auth else "No session",
                            cls="text-gray-600",
                        ),
                        cls="mb-6",
                    ),
                    Div(
                        A(
                            "Logout" if is_auth else "Login",
                            href="/logout" if is_auth else "/login",
                            cls="btn btn-secondary",
                        ),
                        A("Home", href="/", cls="btn btn-outline"),
                        cls="flex gap-3",
                    ),
                ),
                cls="max-w-2xl",
            ),
            cls="container mx-auto p-6",
        )

    logger.info("✅ Authentication routes registered")


__all__ = ["create_auth_routes"]
