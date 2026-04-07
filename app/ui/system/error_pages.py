"""Error page UI components (404, etc.)."""

from typing import Any

from fasthtml.common import H1, Div, Nav, P

from ui.buttons import ButtonLink, ButtonT
from ui.layout import Container, Size


def render_404_page() -> Any:
    """Render 404 Not Found page."""
    navbar = Nav(
        Container(
            Div(
                Div(
                    ButtonLink("SKUEL", href="/", variant=ButtonT.ghost, cls="text-xl"),
                    ButtonLink("Home", href="/", variant=ButtonT.ghost, size=Size.sm),
                    ButtonLink("Search", href="/search", variant=ButtonT.ghost, size=Size.sm),
                    ButtonLink("Askesis", href="/askesis", variant=ButtonT.ghost, size=Size.sm),
                    cls="flex items-center gap-2",
                ),
                cls="navbar flex items-center justify-between",
            ),
        ),
        cls="navbar bg-background",
    )

    return Container(
        navbar,
        Div(
            H1(
                "Page Not Found",
                cls="text-4xl font-bold text-center mb-2 text-foreground",
            ),
            P(
                "Sorry, the page you're looking for doesn't exist.",
                cls="text-muted-foreground text-center mb-8 text-lg",
            ),
            Div(
                ButtonLink("Go Home", href="/", variant=ButtonT.primary, cls="mr-2"),
                ButtonLink("Search", href="/search", variant=ButtonT.secondary),
                cls="text-center",
            ),
            cls="dashboard-header",
        ),
        cls="tasks-dashboard p-8 bg-muted min-h-screen",
    )
