"""
Revised Exercise UI Components
================================

Renderer for the RevisedExercise detail view (/revised-exercises/detail).
List surfaces live on the GradeBook exchange lines and /exchange threads
(feedback-loop UX arc 2 C1).

Pattern: ui/submissions/report.py
"""

from datetime import datetime
from typing import Any

from fasthtml.common import (
    H3,
    Div,
    P,
    Span,
)

from core.models.enums.learning_enums import FeedbackCategory
from ui.components import ButtonT
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.error_banner import render_error_banner
from ui.primitives import ButtonLink

# ============================================================================
# HELPERS
# ============================================================================


def _format_date(dt_value: Any) -> str:
    """Format a datetime-like value to a display string."""
    if not dt_value:
        return ""
    try:
        dt = datetime.fromisoformat(str(dt_value))
        return dt.strftime("%d %b %Y")
    except ValueError:
        return str(dt_value)[:10]


# ============================================================================
# DETAIL VIEW
# ============================================================================


def render_revised_exercise_detail(entity: Any) -> Any:
    """Render the full detail view for a single RevisedExercise.

    Shows revision instructions, feedback points with category badges,
    revision rationale, and links to original exercise and submission.

    Args:
        entity: RevisedExercise domain model.
    """
    title = getattr(entity, "title", "") or "Revision Instructions"
    uid = getattr(entity, "uid", "") or ""
    instructions = getattr(entity, "instructions", None) or ""
    revision_number = getattr(entity, "revision_number", 1) or 1
    revision_rationale = getattr(entity, "revision_rationale", None) or ""
    original_exercise_uid = getattr(entity, "original_exercise_uid", None) or ""
    report_uid = getattr(entity, "report_uid", None) or ""
    created_at = getattr(entity, "created_at", None)
    feedback_points = getattr(entity, "feedback_points", ()) or ()
    date_str = _format_date(created_at)

    # Header badges
    badges: list[Any] = [
        Badge(
            f"Revision #{revision_number}",
            variant=BadgeT.warning,
            size=Size.sm,
        ),
    ]

    # Metadata
    meta_parts = []
    if date_str:
        meta_parts.append(date_str)
    if original_exercise_uid:
        meta_parts.append(f"Exercise: {original_exercise_uid}")

    # Instructions section
    instructions_section = Div(
        H3("Revision Instructions", cls="font-semibold mb-3"),
        P(instructions, cls="text-sm whitespace-pre-wrap leading-relaxed")
        if instructions
        else render_error_banner(
            "Revision instructions are missing — this revision may have incomplete data.",
            severity="warning",
        ),
        cls="mb-6",
    )

    # Feedback points section
    feedback_section: Any = None
    if feedback_points:
        point_items = []
        for fp in feedback_points:
            category = getattr(fp, "category", None)
            detail = getattr(fp, "detail", "") or ""
            if isinstance(category, FeedbackCategory):
                category_label = category.get_label()
                category_color = category.get_color()
            else:
                category_label = str(category or "")
                category_color = "#6B7280"
            point_items.append(
                Div(
                    Span(
                        category_label,
                        cls="text-xs font-medium px-2 py-0.5 rounded-sm",
                        style=f"background-color: {category_color}20; color: {category_color}",
                    ),
                    P(detail, cls="text-sm mt-1"),
                    cls="mb-3",
                )
            )
        feedback_section = Div(
            H3("Feedback Points", cls="font-semibold mb-3"),
            *point_items,
            cls="mb-6",
        )

    # Revision rationale section
    rationale_section: Any = None
    if revision_rationale:
        rationale_section = Div(
            H3("Revision Rationale", cls="font-semibold mb-3"),
            P(revision_rationale, cls="text-sm whitespace-pre-wrap leading-relaxed"),
            cls="mb-6",
        )

    # Links section
    links: list[Any] = []
    if original_exercise_uid:
        links.append(
            ButtonLink(
                "View Original Exercise",
                href=f"/exercises/get?uid={original_exercise_uid}",
                cls=ButtonT.ghost,
                size="sm",
            )
        )
        links.append(
            ButtonLink(
                "Submit Revision",
                href=f"/submit?exercise_uid={uid}",
                cls=ButtonT.primary,
                size="sm",
            )
        )
    if report_uid:
        links.append(
            ButtonLink(
                "View Report",
                href=f"/entry-reports/detail?uid={report_uid}",
                cls=ButtonT.ghost,
                size="sm",
            )
        )

    links_section = Div(*links, cls="flex flex-wrap gap-2 mb-6") if links else None

    # Back link
    back = Div(
        ButtonLink(
            "\u2190 Back to GradeBook",
            href="/gradebook",
            cls=ButtonT.ghost,
        ),
        cls="mt-6",
    )

    return Div(
        # Header
        Div(
            P(title, cls="text-xl font-bold mb-1"),
            P(" \u00b7 ".join(meta_parts), cls="text-sm text-muted-foreground")
            if meta_parts
            else None,
            Div(*badges, cls="flex flex-wrap gap-2 mt-2"),
            cls="mb-6",
        ),
        instructions_section,
        feedback_section,
        rationale_section,
        links_section,
        back,
    )
