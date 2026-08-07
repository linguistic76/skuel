"""Login landing page UI components.

Split layout: branded hero on left (desktop), login card on right.
"""

from typing import Any

from fasthtml.common import H1, H2, A, Div, Form, P, Span

from ui.components import Button, ButtonT, Icon
from ui.forms.components import LabelInput
from ui.layouts.base_page import AuthPage
from ui.primitives import ButtonLink


def _landing_feature_item(text: str) -> Any:
    """Single feature bullet for the landing hero panel."""
    return Div(
        Div(
            Span(
                Icon("check", cls="text-white"),
                cls="flex items-center justify-center w-6 h-6 rounded-full bg-white/20",
            ),
            P(text, cls="text-blue-50 text-sm"),
            cls="flex items-center gap-3",
        ),
    )


def render_login_landing_page() -> Any:
    """Render the landing page with login form for unauthenticated users.

    Split layout: branded hero on left (desktop), login card on right.
    Uses AuthPage for consistent CSS loading.
    """
    content = Div(
        # Left side: Branded hero panel (desktop only)
        Div(
            Div(
                H1("SKUEL", cls="text-5xl font-extrabold tracking-tight text-white mb-3"),
                P(
                    "Personal knowledge & productivity",
                    cls="text-xl font-medium text-blue-100 mb-10",
                ),
                Div(
                    _landing_feature_item(
                        "Track tasks, goals, and habits in one place",
                    ),
                    _landing_feature_item(
                        "Build your personal knowledge graph",
                    ),
                    _landing_feature_item(
                        "AI-powered insights and recommendations",
                    ),
                    _landing_feature_item(
                        "Connect learning to life path alignment",
                    ),
                    cls="space-y-4",
                ),
                cls="max-w-md",
            ),
            cls="hidden lg:flex lg:w-1/2 flex-col justify-center px-16 bg-linear-to-br from-blue-600 via-blue-700 to-indigo-800",
        ),
        # Right side: Login form
        Div(
            Div(
                # Mobile branding
                Div(
                    H1("SKUEL", cls="text-3xl font-extrabold tracking-tight text-primary"),
                    P(
                        "Personal knowledge & productivity",
                        cls="text-sm text-muted-foreground mt-1",
                    ),
                    cls="text-center lg:hidden mb-10",
                ),
                # Desktop subtitle
                H2("Welcome back", cls="hidden lg:block text-2xl font-bold text-foreground mb-1"),
                P(
                    "Sign in to your account",
                    cls="hidden lg:block text-sm text-muted-foreground mb-8",
                ),
                # Login form
                Form(
                    LabelInput(
                        "Email or Username",
                        id="username",
                        name="username",
                        placeholder="Enter your email or username",
                        required=True,
                        autocomplete="email",
                        autofocus=True,
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
                        Div(
                            A(
                                "Forgot password?",
                                href="/forgot-password",
                                cls="text-sm text-primary/80 hover:text-primary font-medium",
                            ),
                            cls="text-right mb-4",
                        ),
                        Button(
                            "Sign in",
                            cls=(
                                "w-full bg-primary text-primary-foreground hover:bg-primary/90",
                                ButtonT.primary,
                            ),
                        ),
                    ),
                    action="/login/submit",
                    method="POST",
                    cls="space-y-5",
                ),
                # Divider
                Div(
                    Div(cls="flex-1 border-t border-border"),
                    Span("or", cls="px-3 text-xs text-muted-foreground"),
                    Div(cls="flex-1 border-t border-border"),
                    cls="flex items-center my-6",
                ),
                # Sign up link
                P(
                    "Don't have an account?",
                    cls="text-center text-sm text-muted-foreground mb-3",
                ),
                ButtonLink(
                    "Create one",
                    href="/register",
                    cls=(ButtonT.secondary, "w-full"),
                ),
                cls="w-full max-w-sm",
            ),
            cls="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-12 lg:w-1/2 bg-background",
        ),
        cls="flex min-h-screen",
    )

    return AuthPage(content, title="SKUEL - Personal Knowledge & Productivity")
