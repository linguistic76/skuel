"""
Teaching UI Cards
=================

Summary card components for teaching views.
"""

from typing import Any

from fasthtml.common import A, Div, P

from ui.components import ButtonT
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.primitives import ButtonLink
from ui.teaching.badges import entity_type_badge
from ui.teaching.types import (
    ClassSummary,
    QueueItem,
    StudentSummary,
)


def _display_title(item: QueueItem) -> str:
    """Get display title from a QueueItem, with fallbacks."""
    return item.title or item.original_filename or "Untitled"


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
            StatusBadge(item.status),
        ],
        show_labels=False,
        actions=ButtonLink(
            "Review",
            href=f"/teaching/review/{item.submission_uid}",
            cls=ButtonT.primary,
            size="sm",
        ),
        card_attrs={"cls": "bg-background shadow-xs mb-2"},
    )


def render_student_summary_card(item: StudentSummary) -> Div:
    """Render a student card with submission counts and action buttons."""
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
                "Exercises Submitted",
                href=f"/teaching/students/{item.student_uid}?tab=pending",
                cls=ButtonT.ghost,
                size="sm",
            ),
            ButtonLink(
                "KU Progress",
                href=f"/teaching/students/{item.student_uid}?tab=ku",
                cls=ButtonT.ghost,
                size="sm",
            ),
            cls="flex gap-2",
        ),
        card_attrs={"cls": "bg-background shadow-xs mb-2"},
    )


def render_student_name_row(student_name: str, student_uid: str) -> Div:
    """Render a simple clickable student name row linking to the student hub."""
    return Div(
        A(
            student_name,
            href=f"/teaching/students/{student_uid}",
            cls="text-base font-medium text-foreground hover:text-primary transition-colors no-underline",
        ),
        cls="px-4 py-3 bg-background border border-border rounded-sm mb-2 hover:bg-muted/50 transition-colors",
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
            href=f"/teaching/groups/{item.uid}?name={item.name}",
            cls=ButtonT.primary,
            size="sm",
        ),
        card_attrs={"cls": "bg-background shadow-xs mb-2"},
    )
