"""
Authentication UI Routes
=========================

Graph-native authentication UI with registration, login, and password reset.

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
- User switching removed entirely for security
- Password reset with secure tokens

Version: 2.1.0
Date: 2026-01-21
"""

from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import RedirectResponse

from adapters.inbound.form_helpers import safe_form_string

# Import auth components
from components.auth_components import AuthComponents
from core.auth import (
    clear_current_user,
    get_current_user,
    is_authenticated,
    set_current_user,
)
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.protocols import GraphAuthOperations

logger = get_logger("skuel.routes.auth_ui")


def create_auth_ui_routes(
    app: Any,
    rt: Any,
    graph_auth: "GraphAuthOperations",
    user_service: Any = None,
) -> list[Any]:
    """
    Create authentication UI routes.

    Routes:
    - GET /register - Show registration page
    - POST /register/submit - Process registration
    - GET /login - Show login page
    - POST /login/submit - Process login
    - GET /logout - Process logout
    - GET /forgot-password - Show password reset page
    - POST /forgot-password - Process password reset request
    - GET /reset-password - Show password reset form
    - POST /reset-password/submit - Process password reset

    Args:
        app: FastHTML app instance
        rt: Route decorator
        graph_auth: Graph authentication service
        user_service: Optional user service

    Returns:
        List of created routes
    """
    routes: list[Any] = []

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
            if not graph_auth:
                logger.error("Graph auth service not available")
                return AuthComponents.render_registration_page(
                    error_message="Authentication service unavailable - please try again later"
                )

            # Register with graph-native auth
            logger.info(f"Registering user: {username} ({email})")
            auth_result = await graph_auth.sign_up(
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
            login_result = await graph_auth.sign_in(
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
                is_teacher=user.can_create_curriculum(),
            )

            logger.info(
                f"User registered and logged in: {username} "
                f"(admin={user.can_manage_users()}, teacher={user.can_create_curriculum()})"
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
            if not graph_auth:
                return AuthComponents.render_login_page(
                    error_message="Authentication service unavailable"
                )

            # Determine if input is email or username
            if "@" in email_or_username:
                email = email_or_username
            else:
                # Look up email by username from Neo4j
                user_result = await user_service.get_user_by_username(email_or_username)
                if user_result.is_error or not user_result.value:
                    return AuthComponents.render_login_page(
                        error_message="Invalid username or password"
                    )
                email = user_result.value.email

            # Get client info for audit trail
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Authenticate with graph-native auth
            auth_result = await graph_auth.sign_in(
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
                is_teacher=user.can_create_curriculum(),
            )

            logger.info(
                f"User logged in: {email} ({session_data['user_uid']}) "
                f"(admin={user.can_manage_users()}, teacher={user.can_create_curriculum()})"
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
            if not graph_auth:
                return AuthComponents.render_reset_password_page(
                    error_message="Authentication service unavailable",
                    token=token,
                )

            # Get client info for audit trail
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Reset password with token
            result = await graph_auth.reset_password_with_token(
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
        if graph_auth and session_token:
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            await graph_auth.sign_out(
                session_token=session_token,
                ip_address=ip_address,
                user_agent=user_agent,
            )

        # Clear cookie session
        clear_current_user(request)

        logger.info(f"User logged out: {user_uid}")

        return RedirectResponse("/login", status_code=303)

    # Collect all routes
    routes.extend(
        [
            register_page,
            register_submit,
            login_page,
            login_submit,
            forgot_password_page,
            forgot_password_submit,
            reset_password_page,
            reset_password_submit,
            logout,
        ]
    )

    logger.info(f"Auth UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_auth_ui_routes"]
