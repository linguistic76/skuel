"""Error page UI components (404, etc.)."""

from typing import Any

from fasthtml.common import H1, Div, Nav, P

from ui.components import ButtonT
from ui.layout import Container
from ui.primitives import ButtonLink


def render_404_page() -> Any:
    """Render 404 Not Found page."""
    navbar = Nav(
        Container(
            Div(
                Div(
                    ButtonLink("SKUEL", href="/", cls=(ButtonT.ghost, "text-xl")),
                    ButtonLink("Home", href="/", cls=ButtonT.ghost, size="sm"),
                    ButtonLink("Search", href="/search", cls=ButtonT.ghost, size="sm"),
                    ButtonLink("Askesis", href="/askesis", cls=ButtonT.ghost, size="sm"),
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
                ButtonLink("Go Home", href="/", cls=(ButtonT.primary, "mr-2")),
                ButtonLink("Search", href="/search", cls=ButtonT.secondary),
                cls="text-center",
            ),
            cls="dashboard-header",
        ),
        cls="tasks-dashboard p-8 bg-muted min-h-screen",
    )
