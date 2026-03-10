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

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import RedirectResponse

from adapters.inbound.auth import (
    clear_current_user,
    get_current_user,
    get_is_admin,
    is_authenticated,
    set_current_user,
)
from adapters.inbound.form_helpers import safe_form_string
from core.models.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegistrationRequest,
    ResetPasswordRequest,
)
from core.utils.logging import get_logger

# Import auth components
from ui.auth.components import AuthComponents

if TYPE_CHECKING:
    from core.ports import GraphAuthOperations

logger = get_logger("skuel.routes.auth_ui")


def _first_validation_error(e: ValidationError) -> str:
    """Extract a human-readable message from the first Pydantic validation error."""
    first = e.errors()[0]
    msg = first.get("msg", "Validation error")
    # Pydantic prefixes model_validator messages with "Value error, "
    if msg.startswith("Value error, "):
        return msg[len("Value error, ") :]
    # Field-level errors — include the field name
    field = first.get("loc", ("",))[-1]
    if field:
        label = str(field).replace("_", " ").title()
        if "at least 1 character" in msg or "required" in msg.lower():
            return f"{label} is required"
        return f"{label}: {msg}"
    return msg


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
        # If already logged in, redirect to appropriate hub
        if is_authenticated(request):
            return RedirectResponse(
                "/admin" if get_is_admin(request) else "/profile", status_code=303
            )

        return AuthComponents.render_registration_page()

    @rt("/register/submit")
    async def register_submit(request: Request) -> Any:
        """Process registration with graph-native auth"""
        logger.info("POST /register/submit - Registration form submitted")
        try:
            form_data = await request.form()

            # Validate form data via Pydantic
            try:
                reg = RegistrationRequest(
                    username=safe_form_string(form_data.get("username")),
                    email=safe_form_string(form_data.get("email")),
                    display_name=safe_form_string(form_data.get("display_name")),
                    password=safe_form_string(form_data.get("password")),
                    confirm_password=safe_form_string(form_data.get("confirm_password")),
                    accept_terms=bool(form_data.get("accept_terms")),
                )
            except ValidationError as e:
                error_msg = _first_validation_error(e)
                logger.warning(f"Validation failed: {error_msg}")
                return AuthComponents.render_registration_page(error_message=error_msg)

            logger.info("All validation checks passed")

            # Check if graph_auth service is available
            if not graph_auth:
                logger.error("Graph auth service not available")
                return AuthComponents.render_registration_page(
                    error_message="Authentication service unavailable - please try again later"
                )

            # Register with graph-native auth
            logger.info(f"Registering user: {reg.username} ({reg.email})")
            auth_result = await graph_auth.sign_up(
                email=reg.email,
                password=reg.password,
                username=reg.username,
                display_name=reg.display_name,
            )

            if auth_result.is_error:
                error_msg = (
                    auth_result.error.message if auth_result.error else "Registration failed"
                )
                logger.warning(f"Registration failed for {reg.email}: {error_msg}")
                return AuthComponents.render_registration_page(error_message=error_msg)

            user_data = auth_result.value
            logger.info(f"New user registered: {reg.username} ({user_data['user_uid']})")

            # Get client info for session
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Auto-login after registration
            login_result = await graph_auth.sign_in(
                email=reg.email,
                password=reg.password,
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

            is_admin = user.can_manage_users()
            logger.info(
                f"User registered and logged in: {reg.username} "
                f"(admin={is_admin}, teacher={user.can_create_curriculum()})"
            )
            return RedirectResponse("/admin" if is_admin else "/profile", status_code=303)

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
        # If already logged in, redirect to appropriate hub
        if is_authenticated(request):
            return RedirectResponse(
                "/admin" if get_is_admin(request) else "/profile", status_code=303
            )

        return AuthComponents.render_login_page()

    @rt("/login/submit")
    async def login_submit(request: Request) -> Any:
        """Process login with graph-native auth"""
        try:
            form_data = await request.form()

            # Validate form data via Pydantic
            try:
                login = LoginRequest(
                    username=safe_form_string(form_data.get("username")),
                    password=safe_form_string(form_data.get("password")),
                )
            except ValidationError as e:
                error_msg = _first_validation_error(e)
                return AuthComponents.render_login_page(error_message=error_msg)

            # Check if graph_auth service is available
            if not graph_auth:
                return AuthComponents.render_login_page(
                    error_message="Authentication service unavailable"
                )

            # Determine if input is email or username
            if "@" in login.username:
                email = login.username
            else:
                # Look up email by username from Neo4j
                user_result = await user_service.get_user_by_username(login.username)
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
                password=login.password,
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

            is_admin = user.can_manage_users()
            logger.info(
                f"User logged in: {email} ({session_data['user_uid']}) "
                f"(admin={is_admin}, teacher={user.can_create_curriculum()})"
            )
            return RedirectResponse("/admin" if is_admin else "/profile", status_code=303)

        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return AuthComponents.render_login_error(str(e))

    # ========================================================================
    # PASSWORD RESET
    # ========================================================================

    @rt("/forgot-password")
    async def forgot_password_page(_request: Request) -> Any:
        """Show forgot password email form"""
        return AuthComponents.render_forgot_password_form()

    @rt("/forgot-password")
    async def forgot_password_submit(request: Request) -> Any:
        """Process forgot password request — send reset email"""
        form_data = await request.form()
        email = safe_form_string(form_data.get("email"))

        try:
            forgot = ForgotPasswordRequest(email=email)
        except ValidationError as e:
            error_msg = _first_validation_error(e)
            return AuthComponents.render_forgot_password_form(error_message=error_msg)

        if "@" not in forgot.email:
            return AuthComponents.render_forgot_password_form(
                error_message="Please enter a valid email address"
            )

        await graph_auth.reset_password_email(forgot.email)
        return AuthComponents.render_password_reset_sent(forgot.email)

    # ========================================================================
    # PASSWORD RESET (Token-Based)
    # ========================================================================

    @rt("/reset-password")
    async def reset_password_page(request: Request, token: str = "") -> Any:
        """Show reset password form where users enter token and new password"""
        # If already logged in, redirect to appropriate hub
        if is_authenticated(request):
            return RedirectResponse(
                "/admin" if get_is_admin(request) else "/profile", status_code=303
            )

        return AuthComponents.render_reset_password_page(token=token)

    @rt("/reset-password/submit")
    async def reset_password_submit(request: Request) -> Any:
        """Process password reset with token"""
        try:
            form_data = await request.form()
            token_value = safe_form_string(form_data.get("token"))

            # Validate form data via Pydantic
            try:
                reset = ResetPasswordRequest(
                    token=token_value,
                    password=safe_form_string(form_data.get("password")),
                    confirm_password=safe_form_string(form_data.get("confirm_password")),
                )
            except ValidationError as e:
                error_msg = _first_validation_error(e)
                return AuthComponents.render_reset_password_page(
                    error_message=error_msg,
                    token=token_value,
                )

            # Check if graph_auth service is available
            if not graph_auth:
                return AuthComponents.render_reset_password_page(
                    error_message="Authentication service unavailable",
                    token=reset.token,
                )

            # Get client info for audit trail
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")

            # Reset password with token
            result = await graph_auth.reset_password_with_token(
                token_value=reset.token,
                new_password=reset.password,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            if result.is_error:
                error = result.expect_error()
                return AuthComponents.render_reset_password_page(
                    error_message=error.message,
                    token=reset.token,
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
