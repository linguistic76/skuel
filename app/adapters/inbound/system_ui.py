"""
System UI Routes
================

System UI routes for home page and error pages.

Version: 2.0 - Simplified root page with login form
"""

__version__ = "2.0"


from typing import Any

from fasthtml.common import H1, A, Div, Form, Li, Nav, P, Span, Ul
from starlette.responses import RedirectResponse

from adapters.inbound.auth import get_is_admin, is_authenticated
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody, CardTitle
from ui.forms.components import LabelInput
from ui.layout import Container, Size
from ui.layouts.base_page import AuthPage

logger = get_logger("skuel.routes.system.ui")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_system_ui_routes(
    app: Any,
    rt: Any,
    system_service: Any,
    services: Any = None,
) -> list[Any]:
    """
    Create system UI routes for the application.

    Args:
        app: The FastHTML app instance
        rt: The router instance
        system_service: System service instance (unused but kept for consistency)
        services: Optional services container (unused)

    Returns:
        List of registered routes
    """
    routes: list[Any] = []

    # ========================================================================
    # HOME PAGE ROUTE
    # ========================================================================

    @rt("/")
    async def home(request: Request) -> Any:
        """Home page - admin hub, profile redirect, or login landing."""
        if is_authenticated(request):
            if get_is_admin(request):
                return await _render_admin_hub(request)
            return RedirectResponse("/profile", status_code=303)

        # Not authenticated - show login landing page
        logger.info("Unauthenticated user at root, showing login page")
        return _render_login_landing_page()

    # ========================================================================
    # ERROR HANDLING ROUTES
    # ========================================================================

    @rt("/404")
    async def not_found() -> Any:
        """404 Not Found page using MonsterUI/Tailwind with module-level imports"""
        # Create navigation using module-level imported components
        navbar = Nav(
            [
                Container(
                    [
                        Div(
                            [
                                Div(
                                    [
                                        ButtonLink(
                                            "SKUEL", href="/", variant=ButtonT.ghost, cls="text-xl"
                                        ),
                                        ButtonLink(
                                            "Home", href="/", variant=ButtonT.ghost, size=Size.sm
                                        ),
                                        ButtonLink(
                                            "Search",
                                            href="/search",
                                            variant=ButtonT.ghost,
                                            size=Size.sm,
                                        ),
                                        ButtonLink(
                                            "Askesis",
                                            href="/askesis",
                                            variant=ButtonT.ghost,
                                            size=Size.sm,
                                        ),
                                    ],
                                    cls="flex items-center gap-2",
                                ),
                            ],
                            cls="navbar flex items-center justify-between",
                        )
                    ]
                )
            ],
            cls="navbar bg-background",
        )

        # Return MonsterUI/Tailwind components with module-level imports
        return Container(
            [
                navbar,
                Div(
                    [
                        H1(
                            "Page Not Found",
                            cls="text-4xl font-bold text-center mb-2 text-foreground",
                        ),
                        P(
                            "Sorry, the page you're looking for doesn't exist.",
                            cls="text-muted-foreground text-center mb-8 text-lg",
                        ),
                        Div(
                            [
                                ButtonLink(
                                    "Go Home", href="/", variant=ButtonT.primary, cls="mr-2"
                                ),
                                ButtonLink("Search", href="/search", variant=ButtonT.secondary),
                            ],
                            cls="text-center",
                        ),
                    ],
                    cls="dashboard-header",
                ),
            ],
            cls="tasks-dashboard p-8 bg-muted min-h-screen",
        )

    logger.info("✅ System UI routes registered")

    # Return list of registered routes
    # Collect all routes
    routes.extend([home, not_found])

    logger.info(f"System UI routes registered: {len(routes)} endpoints")
    return routes


__all__ = ["create_system_ui_routes"]


async def _render_admin_hub(request: Request) -> Any:
    """Render admin home hub with Admin + Teaching cards."""
    from ui.layouts.base_page import BasePage
    from ui.patterns.hub import HubCardData, HubSection
    from ui.patterns.page_header import PageHeader

    cards = [
        HubCardData(
            icon="🛡️",
            name="Admin",
            href="/admin",
            description="User management, analytics, and system health",
        ),
        HubCardData(
            icon="🎓",
            name="Teaching",
            href="/teaching/students",
            description="Review queue, student management, and class groups",
        ),
    ]

    content = Div(
        PageHeader("Home", subtitle="Welcome back"),
        HubSection(title=None, cards=cards, cols=2),
    )

    return await BasePage(
        content=content,
        title="Home",
        request=request,
        active_page="home",
    )


def _render_login_landing_page() -> Any:
    """Render the landing page with login form for unauthenticated users.

    Split layout: branding on left (desktop), login card on right.
    Uses AuthPage for consistent MonsterUI CSS loading.
    """
    content = Div(
        # Left side: Branding (desktop only)
        Div(
            H1("SKUEL", cls="text-5xl font-bold text-primary mb-4"),
            P(
                "Your integrated personal knowledge and productivity system",
                cls="text-2xl text-foreground mb-6",
            ),
            Ul(
                Li(
                    Span("✓", cls="text-primary/80"),
                    " Track tasks, goals, and habits in one place",
                    cls="flex items-center gap-3",
                ),
                Li(
                    Span("✓", cls="text-primary/80"),
                    " Build your personal knowledge graph",
                    cls="flex items-center gap-3",
                ),
                Li(
                    Span("✓", cls="text-primary/80"),
                    " AI-powered insights and recommendations",
                    cls="flex items-center gap-3",
                ),
                Li(
                    Span("✓", cls="text-primary/80"),
                    " Connect learning to life path alignment",
                    cls="flex items-center gap-3",
                ),
                cls="space-y-3 text-muted-foreground",
            ),
            cls="hidden lg:flex lg:w-1/2 flex-col justify-center px-12",
        ),
        # Right side: Login form
        Div(
            # Mobile branding
            H1("SKUEL", cls="text-center text-3xl font-bold text-primary lg:hidden mb-8"),
            # Login card
            Card(
                CardBody(
                    CardTitle("Sign in", cls="text-2xl font-bold mb-4"),
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
                            Button("Sign in", cls="w-full", variant=ButtonT.primary),
                            cls="mt-2",
                        ),
                        action="/login/submit",
                        method="POST",
                        cls="space-y-4",
                    ),
                    Div(
                        Span("Don't have an account? ", cls="text-sm"),
                        A("Sign up", href="/register", cls="hover:underline text-sm"),
                        cls="mt-4 text-center",
                    ),
                ),
                cls="bg-background w-full max-w-sm shadow-2xl",
            ),
            cls="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-8 lg:w-1/2",
        ),
        cls="flex min-h-full",
    )

    return AuthPage(content, title="SKUEL - Personal Knowledge & Productivity")
