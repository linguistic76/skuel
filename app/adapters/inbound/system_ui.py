"""
System UI Routes
================

System UI routes for home page and error pages.

Version: 2.0 - Simplified root page with login form
"""

__version__ = "2.0"


from typing import Any

from fasthtml.common import H1, A, Div, Nav, NotStr, P
from starlette.requests import Request
from starlette.responses import RedirectResponse

from adapters.inbound.auth import is_authenticated
from core.utils.logging import get_logger
from ui.layout import Container

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
        """Home page - login form when logged out, redirect when logged in."""
        # If authenticated, redirect to Profile
        if is_authenticated(request):
            logger.info("Authenticated user at root, redirecting to Profile")
            return RedirectResponse("/profile", status_code=303)

        # Not authenticated - show login landing page
        logger.info("Unauthenticated user at root, showing login page")
        return _render_login_landing_page()

    # ========================================================================
    # ERROR HANDLING ROUTES
    # ========================================================================

    @rt("/404")
    async def not_found() -> Any:
        """404 Not Found page using DaisyUI/Tailwind with module-level imports"""
        # Create navigation using module-level imported components
        navbar = Nav(
            [
                Container(
                    [
                        Div(
                            [
                                Div(
                                    [
                                        A("SKUEL", href="/", cls="btn btn-ghost text-xl"),
                                        A("Home", href="/", cls="btn btn-ghost btn-sm"),
                                        A("Search", href="/search", cls="btn btn-ghost btn-sm"),
                                        A("Askesis", href="/askesis", cls="btn btn-ghost btn-sm"),
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

        # Return DaisyUI/Tailwind components with module-level imports
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
                                A("Go Home", href="/", cls="btn btn-primary mr-2"),
                                A("Search", href="/search", cls="btn btn-secondary"),
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


def _render_login_landing_page() -> NotStr:
    """
    Render the landing page with login form for unauthenticated users.

    Uses dark theme matching the login page style.
    Simple, focused design like Facebook's logged-out homepage.
    """
    return NotStr("""<!DOCTYPE html>
<html class="h-full dark" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SKUEL - Personal Knowledge & Productivity</title>
    <link rel="stylesheet" href="/static/css/output.css?v=4">
</head>
<body class="h-full bg-secondary">
    <div class="flex min-h-full">
        <!-- Left side: Branding -->
        <div class="hidden lg:flex lg:w-1/2 flex-col justify-center px-12">
            <h1 class="text-5xl font-bold text-primary mb-4">SKUEL</h1>
            <p class="text-2xl text-foreground mb-6">Your integrated personal knowledge and productivity system</p>
            <ul class="space-y-3 text-muted-foreground">
                <li class="flex items-center gap-3">
                    <span class="text-primary/80">✓</span>
                    Track tasks, goals, and habits in one place
                </li>
                <li class="flex items-center gap-3">
                    <span class="text-primary/80">✓</span>
                    Build your personal knowledge graph
                </li>
                <li class="flex items-center gap-3">
                    <span class="text-primary/80">✓</span>
                    AI-powered insights and recommendations
                </li>
                <li class="flex items-center gap-3">
                    <span class="text-primary/80">✓</span>
                    Connect learning to life path alignment
                </li>
            </ul>
        </div>

        <!-- Right side: Login form -->
        <div class="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-8 lg:w-1/2">
            <!-- Mobile branding -->
            <h1 class="text-center text-3xl font-bold text-primary lg:hidden mb-8">SKUEL</h1>

            <!-- Login card -->
            <div class="card bg-background w-full max-w-sm shadow-2xl">
                <div class="card-body">
                    <h2 class="card-title text-2xl font-bold mb-4">Sign in</h2>

                    <form action="/login/submit" method="POST">
                        <!-- Email/Username field -->
                        <div class="form-control w-full mb-4">
                            <label class="label" for="username">
                                <span class="label-text">Email or Username</span>
                            </label>
                            <input
                                id="username"
                                type="text"
                                name="username"
                                required
                                autocomplete="email"
                                autofocus
                                placeholder="Enter your email or username"
                                class="input input-bordered w-full"
                            />
                        </div>

                        <!-- Password field -->
                        <div class="form-control w-full mb-4">
                            <label class="label" for="password">
                                <span class="label-text">Password</span>
                                <a href="/forgot-password" class="label-text-alt link link-hover">Forgot password?</a>
                            </label>
                            <input
                                id="password"
                                type="password"
                                name="password"
                                required
                                autocomplete="current-password"
                                placeholder="Enter your password"
                                class="input input-bordered w-full"
                            />
                        </div>

                        <!-- Submit button -->
                        <div class="form-control mt-6">
                            <button type="submit" class="btn btn-primary w-full">Sign in</button>
                        </div>
                    </form>

                    <!-- Sign up link -->
                    <div class="mt-4 text-center">
                        <span class="text-sm">Don't have an account? </span>
                        <a href="/register" class="link link-hover text-sm">Sign up</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>""")
