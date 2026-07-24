"""
Authentication UI Components
============================

Reusable components for user registration and login.
Uses SKUEL component wrappers for consistent styling.

All methods return FT component trees (not NotStr). Full-page auth views
(login, registration) are wrapped with AuthPage() by the route handler.
Fragment views (forgot-password, success pages) are rendered within the
app's normal layout.
"""

from typing import Any

from fasthtml.common import H1, H3, A, Div, Form, Li, P, Span, Strong, Ul

from ui.components import Button, ButtonT, Card, CardBody
from ui.forms.components import Checkbox, Input, LabelInput
from ui.patterns.csrf import csrf_hidden_input
from ui.primitives import ButtonLink


def _error_banner(error_message: str | None) -> Any:
    """Render an error banner if error_message is provided, else empty tuple."""
    if not error_message:
        return ()
    return Div(
        P(error_message, cls="text-sm text-destructive"),
        cls="mb-4 rounded-md bg-destructive/10 border border-destructive/20 p-3",
        role="alert",
    )


def _auth_card(*children: Any, max_width: str = "max-w-md") -> Any:
    """Card container for fragment auth pages (forgot-password, success, etc.)."""
    return Div(
        Card(
            CardBody(*children),
            cls=f"bg-background shadow-xl {max_width} w-full",
        ),
        cls="min-h-screen bg-muted flex items-center justify-center p-6",
    )


class AuthComponents:
    """Component library for authentication interface.

    Full-page methods (render_login_page, render_registration_page) return
    content to be wrapped by AuthPage() in the route handler.

    Fragment methods (render_forgot_password_form, etc.) return content
    rendered within the app's normal layout (which already loads SKUEL CSS).
    """

    @staticmethod
    def render_login_page(error_message: str | None = None) -> Any:
        """Render login page content (wrap with AuthPage in route handler)."""
        return Div(
            Div(
                # Header
                H1("SKUEL", cls="text-center text-3xl font-extrabold tracking-tight text-primary"),
                P(
                    "Sign in to your account",
                    cls="mt-2 text-center text-sm text-muted-foreground",
                ),
                cls="mb-8",
            ),
            _error_banner(error_message),
            Form(
                csrf_hidden_input(),
                LabelInput(
                    "Email or Username",
                    id="username",
                    name="username",
                    type="text",
                    placeholder="Enter your email or username",
                    required=True,
                    autofocus=True,
                    autocomplete="email",
                ),
                LabelInput(
                    "Password",
                    id="password",
                    name="password",
                    type="password",
                    placeholder="Enter your password",
                    required=True,
                    autocomplete="current-password",
                ),
                Div(
                    A(
                        "Forgot password?",
                        href="/forgot-password",
                        cls="text-sm text-primary/80 hover:text-primary font-medium",
                    ),
                    cls="text-right",
                ),
                Button(
                    "Sign in",
                    cls=(
                        "w-full bg-primary text-primary-foreground hover:bg-primary/90",
                        ButtonT.primary,
                    ),
                ),
                action="/login/submit",
                method="POST",
                cls="space-y-5",
                id="login-form",
            ),
            # Divider
            Div(
                Div(cls="flex-1 border-t border-border"),
                Span("or", cls="px-3 text-xs text-muted-foreground"),
                Div(cls="flex-1 border-t border-border"),
                cls="flex items-center my-6",
            ),
            P(
                "Don't have an account?",
                cls="text-center text-sm text-muted-foreground mb-3",
            ),
            ButtonLink(
                "Create one",
                href="/register",
                cls=(ButtonT.secondary, "w-full"),
            ),
            cls="flex flex-col justify-center px-6 py-12 sm:px-8 mx-auto w-full max-w-sm min-h-screen",
        )

    @staticmethod
    def render_registration_page(
        error_message: str | None = None,
        require_invite_code: bool = False,
    ) -> Any:
        """Render registration page content (wrap with AuthPage in route handler).

        ``require_invite_code`` renders the invite-code input — set by the route
        when the deployment gates signup behind ``SIGNUP_INVITE_CODE``.
        """
        return Div(
            Div(
                # Header
                H1("SKUEL", cls="text-center text-3xl font-extrabold tracking-tight text-primary"),
                P(
                    "Create your account",
                    cls="mt-2 text-center text-sm text-muted-foreground",
                ),
                cls="mb-8",
            ),
            _error_banner(error_message),
            Form(
                csrf_hidden_input(),
                LabelInput(
                    "Username",
                    id="username",
                    name="username",
                    placeholder="Choose a username",
                    required=True,
                    autofocus=True,
                    minlength="3",
                    maxlength="30",
                    pattern="[a-zA-Z0-9_]+",
                    help_text="3-30 characters, letters, numbers, and underscores only",
                ),
                LabelInput(
                    "Email address",
                    id="email",
                    name="email",
                    type="email",
                    placeholder="your.email@example.com",
                    required=True,
                    autocomplete="email",
                ),
                LabelInput(
                    "Display name",
                    id="display_name",
                    name="display_name",
                    placeholder="How should we call you?",
                    required=True,
                    maxlength="100",
                ),
                LabelInput(
                    "Password",
                    id="password",
                    name="password",
                    type="password",
                    placeholder="Create a strong password",
                    required=True,
                    minlength="6",
                    autocomplete="new-password",
                    help_text="At least 6 characters",
                ),
                LabelInput(
                    "Confirm password",
                    id="confirm_password",
                    name="confirm_password",
                    type="password",
                    placeholder="Re-enter your password",
                    required=True,
                    minlength="6",
                    autocomplete="new-password",
                ),
                (
                    LabelInput(
                        "Invite code",
                        id="invite_code",
                        name="invite_code",
                        placeholder="Enter your invite code",
                        required=True,
                        maxlength="200",
                        autocomplete="off",
                        help_text="Signup currently requires an invite code",
                    )
                    if require_invite_code
                    else None
                ),
                # Terms acceptance
                Div(
                    Input(type="hidden", name="accept_terms", value="0", full_width=False),
                    Div(
                        Checkbox(
                            id="accept_terms",
                            name="accept_terms",
                            value="1",
                            required=True,
                        ),
                        Span(
                            "I agree to the ",
                            A(
                                "Terms of Service",
                                href="/terms",
                                cls="font-semibold text-primary/80 hover:text-primary",
                            ),
                            " and ",
                            A(
                                "Privacy Policy",
                                href="/privacy",
                                cls="font-semibold text-primary/80 hover:text-primary",
                            ),
                            cls="text-sm text-muted-foreground",
                        ),
                        cls="flex items-center gap-2",
                    ),
                    cls="pt-1",
                ),
                Button("Create account", cls=("w-full mt-2", ButtonT.primary)),
                action="/register/submit",
                method="POST",
                cls="space-y-4",
            ),
            # Divider
            Div(
                Div(cls="flex-1 border-t border-border"),
                Span("or", cls="px-3 text-xs text-muted-foreground"),
                Div(cls="flex-1 border-t border-border"),
                cls="flex items-center my-6",
            ),
            P(
                "Already have an account? ",
                A(
                    "Sign in",
                    href="/login",
                    cls="font-semibold text-primary/80 hover:text-primary",
                ),
                cls="text-center text-sm text-muted-foreground",
            ),
            cls="flex flex-col justify-center px-6 py-12 sm:px-8 mx-auto w-full max-w-sm min-h-screen",
        )

    @staticmethod
    def render_registration_success(username: str) -> Any:
        """Render registration success page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1(
                    "Welcome to SKUEL!",
                    cls="text-3xl font-bold mb-2",
                ),
                P(
                    f"Your account '{username}' has been created successfully!",
                    cls="text-lg text-muted-foreground mb-6",
                ),
                Div(
                    H3("What's Next?", cls="text-xl font-semibold mb-4"),
                    Ul(
                        Li("Explore learning paths", cls="flex items-center gap-2"),
                        Li("Create your first task", cls="flex items-center gap-2"),
                        Li("Set your goals", cls="flex items-center gap-2"),
                        Li("Customize your preferences", cls="flex items-center gap-2"),
                        cls="space-y-2 text-foreground/80",
                    ),
                    cls="text-left mb-6",
                ),
                ButtonLink("Get Started", href="/", cls=(ButtonT.primary, "w-full")),
                cls="text-center",
            ),
            max_width="max-w-lg",
        )

    @staticmethod
    def render_login_error(error_message: str) -> Any:
        """Render login error page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1(
                    "Login Failed",
                    cls="text-3xl font-bold text-destructive mb-2",
                ),
                P(error_message, cls="text-lg text-foreground/80 mb-6"),
                Div(
                    ButtonLink("Try Again", href="/login", cls=ButtonT.primary),
                    ButtonLink("Forgot Password?", href="/forgot-password", cls=ButtonT.secondary),
                    cls="flex justify-center gap-3",
                ),
                cls="text-center",
            ),
            max_width="max-w-lg",
        )

    @staticmethod
    def render_forgot_password_form(error_message: str | None = None) -> Any:
        """Render forgot password email form (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Reset Password", cls="text-3xl font-bold mb-2"),
                P(
                    "Enter your email and we'll send you a link to reset your password.",
                    cls="text-muted-foreground mb-6",
                ),
                _error_banner(error_message),
                Form(
                    csrf_hidden_input(),
                    Input(
                        type="email",
                        name="email",
                        placeholder="your.email@example.com",
                        required=True,
                        autofocus=True,
                    ),
                    Button("Send Reset Link", cls=("w-full", ButtonT.primary)),
                    action="/forgot-password",
                    method="POST",
                    cls="space-y-4",
                ),
                Div(cls="border-t border-border my-4"),
                Div(
                    ButtonLink(
                        "I Have a Reset Token",
                        href="/reset-password",
                        cls=(ButtonT.secondary, "w-full"),
                    ),
                    A(
                        "Back to Login",
                        href="/login",
                        cls="hover:underline text-muted-foreground text-sm",
                    ),
                    cls="space-y-2 text-center",
                ),
                cls="text-center",
            ),
        )

    @staticmethod
    def render_reset_password_page(
        error_message: str | None = None,
        token: str = "",
    ) -> Any:
        """Render password reset form (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Reset Your Password", cls="text-2xl font-bold"),
                P("Enter your reset token", cls="text-muted-foreground text-sm mt-1"),
                cls="text-center mb-4",
            ),
            _error_banner(error_message),
            Form(
                csrf_hidden_input(),
                LabelInput(
                    "Reset Token",
                    name="token",
                    placeholder="Paste your reset token here",
                    input_cls="font-mono text-sm",
                    value=token,
                    required=True,
                    help_text="The token from your password reset email",
                ),
                LabelInput(
                    "New Password",
                    name="password",
                    type="password",
                    placeholder="Enter new password",
                    required=True,
                    minlength="8",
                    help_text="At least 8 characters",
                ),
                LabelInput(
                    "Confirm Password",
                    name="confirm_password",
                    type="password",
                    placeholder="Confirm new password",
                    required=True,
                    minlength="8",
                ),
                Button("Reset Password", cls=("w-full", ButtonT.primary)),
                action="/reset-password/submit",
                method="POST",
                cls="space-y-4",
            ),
            Div(cls="border-t border-border my-4"),
            Div(
                A("Back to Login", href="/login", cls="hover:underline text-muted-foreground"),
                cls="text-center",
            ),
        )

    @staticmethod
    def render_reset_password_success() -> Any:
        """Render password reset success page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Password Reset!", cls="text-3xl font-bold mb-2"),
                P(
                    "Your password has been reset successfully. "
                    "You can now log in with your new password.",
                    cls="text-muted-foreground mb-6",
                ),
                ButtonLink("Go to Login", href="/login", cls=(ButtonT.primary, "w-full")),
                cls="text-center",
            ),
        )

    @staticmethod
    def render_email_verification_sent(email: str) -> Any:
        """Render email verification sent page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Check Your Email", cls="text-3xl font-bold mb-2"),
                P(
                    "We've sent a verification email to ",
                    Strong(email),
                    ".",
                    cls="text-lg text-muted-foreground mb-4",
                ),
                P(
                    "Please click the link in the email to verify your account before logging in.",
                    cls="text-foreground/80 mb-6",
                ),
                ButtonLink("Go to Login", href="/login", cls=(ButtonT.primary, "w-full")),
                cls="text-center",
            ),
            max_width="max-w-lg",
        )

    @staticmethod
    def render_password_reset_sent(email: str) -> Any:
        """Render password reset email sent page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Check Your Email", cls="text-3xl font-bold mb-4"),
                P(
                    "If an account exists for ",
                    Strong(email),
                    ", you'll receive password reset instructions shortly.",
                    cls="text-muted-foreground mb-6",
                ),
                ButtonLink("Back to Login", href="/login", cls=(ButtonT.primary, "w-full")),
                cls="text-center",
            ),
        )

    @staticmethod
    def render_email_verified() -> Any:
        """Render email verified callback page (fragment within app layout)."""
        return _auth_card(
            Div(
                H1("Email Verified!", cls="text-3xl font-bold mb-2"),
                P(
                    "Your email has been verified successfully.",
                    cls="text-lg text-muted-foreground mb-4",
                ),
                P("Redirecting you to login...", cls="text-foreground/80 mb-6"),
                cls="text-center",
            ),
            max_width="max-w-lg",
        )


__all__ = ["AuthComponents"]
