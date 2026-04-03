"""
Teaching UI Cards
=================

Dashboard, stat, and summary card components for teaching views.
"""

from typing import Any

from fasthtml.common import H3, Div, P

from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.teaching.badges import entity_type_badge, status_badge
from ui.teaching.types import (
    ClassSummary,
    ExerciseSummary,
    QueueItem,
    StudentSummary,
    TeachingDashboardStats,
)


def render_empty_state(title: str, description: str) -> Div:
    """Render a centered empty state with title and description."""
    return Div(
        Div(
            H3(title, cls="text-lg font-medium mb-2"),
            P(description, cls="text-muted-foreground"),
            cls="text-center py-12",
        ),
    )


def _display_title(item: QueueItem) -> str:
    """Get display title from a QueueItem, with fallbacks."""
    return item.title or item.original_filename or "Untitled"


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


def render_queue_item(item: QueueItem) -> Div:
    """Render a single review queue item as a card."""
    title = _display_title(item)
    student_name = item.student_name or item.student_uid or "Unknown"

    subtitle_parts = [f"by {student_name}"]
    if item.exercise_name:
        subtitle_parts.append(f"for {item.exercise_name}")

    feedback_badge: Any = None
    if item.feedback_count > 0:
        feedback_badge = Badge(
            f"{item.feedback_count} feedback",
            variant=BadgeT.info,
            size=Size.sm,
        )

    return CardGenerator.from_dataclass(
        {"title": title},
        display_fields=[],
        subtitle=" · ".join(subtitle_parts),
        header_badges=[
            feedback_badge,
            entity_type_badge(item.entity_type),
            status_badge(item.status),
        ],
        show_labels=False,
        actions=ButtonLink(
            "Review",
            href=f"/teaching/review/{item.ku_uid}",
            variant=ButtonT.primary,
            size=Size.sm,
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
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


def render_student_summary_card(item: StudentSummary) -> Div:
    """Render a student card with submission counts and a link."""
    pending_variant = BadgeT.warning if item.pending_count > 0 else BadgeT.ghost

    return CardGenerator.from_dataclass(
        {"title": item.student_name},
        display_fields=[],
        subtitle=P(item.student_uid, cls="text-xs text-foreground/40 mb-0"),
        header_badges=[
            Badge(f"{item.pending_count} pending", variant=pending_variant),
            Badge(f"{item.reviewed_count}/{item.submission_count} reviewed", variant=BadgeT.ghost),
        ],
        show_labels=False,
        actions=Div(
            ButtonLink(
                "Submissions",
                href=f"/teaching/students/{item.student_uid}",
                variant=ButtonT.primary,
                size=Size.sm,
            ),
            ButtonLink(
                "KU Progress",
                href=f"/teaching/learning/user/{item.student_uid}",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            ButtonLink(
                "Reports",
                href=f"/teaching/reports/user/{item.student_uid}",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex gap-2 w-full justify-end",
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )


def render_class_card(item: ClassSummary) -> Div:
    """Render a class (group) card with member/exercise/pending counts."""
    pending_variant = BadgeT.warning if item.pending_count > 0 else BadgeT.ghost
    active_badge: Any = (
        None if item.is_active else Badge("Inactive", variant=BadgeT.ghost, size=Size.sm)
    )

    subtitle_text = item.description if item.description else None

    return CardGenerator.from_dataclass(
        {"title": item.name},
        display_fields=[],
        title_field="title",
        subtitle=subtitle_text,
        header_badges=[
            active_badge,
            Badge(f"{item.pending_count} pending", variant=pending_variant),
            Badge(f"{item.member_count} students", variant=BadgeT.ghost),
            Badge(f"{item.exercise_count} exercises", variant=BadgeT.ghost),
        ],
        show_labels=False,
        actions=ButtonLink(
            "View Group",
            href=f"/teaching/groups/{item.uid}",
            variant=ButtonT.primary,
            size=Size.sm,
        ),
        card_attrs={"cls": "bg-background shadow-sm mb-2"},
    )
