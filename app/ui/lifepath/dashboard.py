"""LifePath dashboard page content."""

from typing import Any

from fasthtml.common import H3, Div, P, Span

from core.models.type_hints import UserUID
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT, Progress
from ui.layout import Size
from ui.patterns.page_header import PageHeader


def render_dashboard_content(status: dict, user_uid: UserUID) -> Any:
    """Build the main dashboard content."""
    if not status.get("has_vision"):
        return Div(
            PageHeader(
                "Welcome to Your Life Path",
                subtitle="You haven't expressed your vision yet. Start by telling us what you want to become.",
            ),
            ButtonLink(
                "Express Your Vision",
                href="/lifepath/vision",
                variant=ButtonT.primary,
                size=Size.lg,
            ),
            cls="container mx-auto px-4 py-8 text-center",
        )

    # Has vision - show summary
    alignment = status.get("alignment", {})
    alignment_score = alignment.get("alignment_score", 0)
    alignment_level = alignment.get("alignment_level", "unknown")

    return Div(
        PageHeader("Your Life Path"),
        # Vision summary
        Card(
            Div(
                H3("Your Vision", cls="font-semibold text-lg mb-2"),
                P(
                    status.get("vision", {}).get("statement", "No vision"),
                    cls="text-muted-foreground italic",
                ),
                Div(
                    *[
                        Badge(theme, variant=BadgeT.outline, cls="mr-2")
                        for theme in status.get("vision", {}).get("themes", [])[:5]
                    ],
                    cls="mt-4",
                ),
                cls="p-4",
            ),
            cls="mb-6",
        ),
        # Alignment score
        Card(
            Div(
                H3("Alignment Score", cls="font-semibold text-lg mb-2"),
                Div(
                    Span(f"{int(alignment_score * 100)}%", cls="text-4xl font-bold"),
                    Span(f" ({alignment_level})", cls="text-xl text-muted-foreground ml-2"),
                    cls="mb-4",
                ),
                Progress(
                    value=int(alignment_score * 100),
                    max=100,
                    cls="w-full h-4",
                ),
                P(
                    "Are you LIVING what you SAID?",
                    cls="text-sm text-muted-foreground mt-2",
                ),
                cls="p-4",
            ),
            cls="mb-6",
        ),
        # Quick actions
        Div(
            ButtonLink(
                "View Alignment Details",
                href="/lifepath/alignment",
                variant=ButtonT.outline,
                cls="mr-4",
            ),
            ButtonLink("Update Vision", href="/lifepath/vision", variant=ButtonT.outline),
            cls="flex gap-4",
        ),
        # Daily focus
        render_daily_focus(status.get("daily_focus")),
        cls="container mx-auto px-4 py-8",
    )


def render_daily_focus(daily_focus: dict | None) -> Any:
    """Build daily focus card."""
    if not daily_focus:
        return Div()

    return Card(
        Div(
            H3("Today's Focus", cls="font-semibold text-lg mb-2"),
            P(daily_focus.get("focus", ""), cls="text-xl font-medium mb-2"),
            P(daily_focus.get("reason", ""), cls="text-sm text-muted-foreground"),
            P(
                f"Action: {daily_focus.get('action', '')}",
                cls="text-sm text-muted-foreground mt-2 italic",
            ),
            cls="p-4",
        ),
        cls="mt-6",
    )
