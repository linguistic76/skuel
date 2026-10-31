"""LifePath dashboard page content."""

from fasthtml.common import FT, H3, Div, P, Span

from core.models.enums import AlignmentLevel
from core.ports.query_types import DailyFocusResult, LifePathStatus
from ui.components import ButtonT, Card
from ui.feedback import Badge, BadgeT, Progress
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink


def render_dashboard_content(status: LifePathStatus) -> FT:
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
                cls=ButtonT.primary,
                size="lg",
            ),
            cls="container mx-auto text-center",
        )

    # Has vision - show summary. Alignment is measured against a designated path,
    # so a learner who has not chosen one yet has none (``alignment`` is None).
    vision = status.get("vision") or {}
    alignment = status.get("alignment") or {}
    alignment_score = alignment.get("alignment_score", 0)
    alignment_level = AlignmentLevel.from_value(alignment.get("alignment_level"))
    alignment_body = (
        (
            Div(
                Span(f"{round(alignment_score * 100)}%", cls="text-4xl font-bold"),
                Span(
                    f" ({alignment_level.get_label()})",
                    cls="text-xl text-muted-foreground ml-2",
                ),
                cls="mb-4",
            ),
            Progress(value=round(alignment_score * 100), max=100, cls="w-full h-4"),
            P("Are you LIVING what you SAID?", cls="text-sm text-muted-foreground mt-2"),
        )
        if status.get("has_designation")
        else (
            P(
                "Choose a Learning Path for your vision, and alignment is measured against it.",
                cls="text-muted-foreground",
            ),
        )
    )

    return Div(
        PageHeader("Your Life Path"),
        # Vision summary
        Card(
            Div(
                H3("Your Vision", cls="font-semibold text-lg mb-2"),
                P(
                    vision.get("statement", "No vision"),
                    cls="text-muted-foreground italic",
                ),
                Div(
                    *[
                        Badge(theme, variant=BadgeT.outline, cls="mr-2")
                        for theme in vision.get("themes", [])[:5]
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
                *alignment_body,
                cls="p-4",
            ),
            cls="mb-6",
        ),
        # Quick actions
        Div(
            ButtonLink("View Alignment Details", href="/lifepath/alignment", cls=ButtonT.secondary),
            ButtonLink("Update Vision", href="/lifepath/vision", cls=ButtonT.secondary),
            cls="flex flex-wrap gap-4",
        ),
        # Daily focus
        render_daily_focus(status.get("daily_focus")),
        cls="container mx-auto",
    )


def render_daily_focus(daily_focus: DailyFocusResult | None) -> FT:
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
