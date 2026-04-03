"""Shelved teaching card components — removed 2026-04-03.

Dashboard overview, stat cards, and exercise summary cards.
These were removed when the Teaching UI was redesigned to use
Review Queue as the root page and exercises became ingestion-only.
"""

from typing import Any

from fasthtml.common import Div, P

from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.teaching.types import (
    ExerciseSummary,
    TeachingDashboardStats,
)


def render_stat_card(label: str, value: int, icon: str, href: str, badge_cls: str = "") -> Div:
    """Render a single stat card linking to the relevant section."""
    value_cls = f"text-2xl font-bold {badge_cls}" if badge_cls else "text-2xl font-bold"
    return Card(
        Div(
            Div(icon, cls="text-2xl"),
            Div(label, cls="text-sm text-muted-foreground"),
            Div(str(value), cls=value_cls),
            cls="p-4 text-center",
        ),
        cls="bg-background shadow-sm cursor-pointer hover:shadow-md transition-shadow",
        **{"onclick": f"window.location='{href}'"},
    )


def render_dashboard(stats: TeachingDashboardStats) -> Div:
    """Render the overview dashboard with stat cards and quick links."""
    pending_badge = "text-warning" if stats.pending_count > 0 else ""

    return Div(
        Div(
            render_stat_card(
                "Pending Reviews", stats.pending_count, "📥", "/teaching/queue", pending_badge
            ),
            render_stat_card("Students", stats.total_students, "👥", "/teaching/students"),
            render_stat_card("Exercises", stats.total_exercises, "📋", "/teaching/exercises"),
            render_stat_card("Groups", stats.total_groups, "👥", "/teaching/groups"),
            cls="grid grid-cols-2 gap-4 mb-6",
        ),
        Div(
            ButtonLink(
                "Go to Review Queue →",
                href="/teaching/queue",
                variant=ButtonT.primary,
            ),
            cls="mt-2",
        )
        if stats.pending_count > 0
        else Div(
            P("No submissions pending review.", cls="text-muted-foreground"),
        ),
    )


def render_exercise_summary_card(item: ExerciseSummary) -> Div:
    """Render an exercise card with submission counts and a link."""
    scope_badge = Badge(item.scope, variant=BadgeT.outline, size=Size.sm) if item.scope else None
    pending_variant = BadgeT.warning if item.pending_count > 0 else BadgeT.ghost

    return CardGenerator.from_dataclass(
        {"title": item.title},
        display_fields=[],
        subtitle=scope_badge,
        header_badges=[
            Badge(f"{item.pending_count} pending", variant=pending_variant),
            Badge(f"{item.reviewed_count}/{item.total_count} reviewed", variant=BadgeT.ghost),
        ],
        show_labels=False,
        actions=Div(
            ButtonLink(
                "Edit",
                href=f"/teaching/exercises/{item.uid}/edit",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            ButtonLink(
                "View Submissions",
                href=f"/teaching/exercises/{item.uid}/submissions",
                variant=ButtonT.primary,
                size=Size.sm,
            ),
            cls="flex gap-2",
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )
