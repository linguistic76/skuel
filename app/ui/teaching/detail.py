"""
Teaching UI Detail Components
=============================

Submission content display and row components for detail views.
"""

from typing import Any

from fasthtml.common import H4, Div, P, Span

from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.teaching.badges import entity_type_badge, status_badge
from ui.teaching.types import ClassMember, SubmissionDetail, SubmissionRow


def render_submission_content(detail: SubmissionDetail) -> Div:
    """
    Render the submission content card for teacher review.

    Shows processed_content if available, then content, then filename as fallback.
    Also surfaces exercise instructions for teacher reference.
    """
    student_name = detail.student_name or detail.student_uid or "Unknown"

    # Display content — prefer processed, fall back to raw, then filename
    display_content = (
        detail.processed_content
        or detail.content
        or detail.original_filename
        or "(No content available)"
    )

    meta_parts = [f"by {student_name}"]
    if detail.exercise_title:
        meta_parts.append(f"Exercise: {detail.exercise_title}")

    exercise_section: Any = ""
    if detail.exercise_instructions:
        exercise_section = Div(
            Div(
                Span(
                    "Exercise instructions",
                    cls="text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                ),
                P(
                    detail.exercise_instructions,
                    cls="text-sm text-muted-foreground whitespace-pre-wrap mt-1",
                ),
                cls="p-3 bg-muted/50 rounded",
            ),
            cls="mb-3",
        )

    return Card(
        CardBody(
            Div(
                Div(
                    H4(detail.title or "Untitled", cls="font-semibold mb-1"),
                    P(" · ".join(meta_parts), cls="text-sm text-muted-foreground mb-0"),
                    cls="flex-1",
                ),
                Div(
                    entity_type_badge(detail.entity_type),
                    status_badge(detail.status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-start justify-between gap-4 mb-4",
            ),
            exercise_section,
            Div(
                Span(
                    "Submission content",
                    cls="text-xs font-semibold text-muted-foreground uppercase tracking-wide",
                ),
                P(display_content, cls="text-sm whitespace-pre-wrap mt-1"),
                cls="p-3 bg-muted/30 rounded border border-border",
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-4",
    )


def render_report_item(fb: dict[str, Any]) -> Div:
    """Render a single report history item. Delegates to shared component."""
    from ui.patterns.report_item import render_report_item as _shared_render

    return _shared_render(fb)


def render_exercise_submission_row(item: SubmissionRow) -> Div:
    """Render a submission row in the exercise-detail view."""
    title = item.title or item.original_filename or "Untitled"
    student_name = item.student_name or item.student_uid or "Unknown"

    feedback_indicator: Any = ""
    if item.feedback_count > 0:
        feedback_indicator = Badge(
            f"{item.feedback_count} feedback",
            variant=BadgeT.info,
            size=Size.sm,
        )

    return Card(
        CardBody(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    P(f"by {student_name}", cls="text-sm text-muted-foreground mb-0"),
                    cls="flex-1",
                ),
                Div(
                    feedback_indicator,
                    status_badge(item.status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                ButtonLink(
                    "Review",
                    href=f"/teaching/review/{item.uid}",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                cls="flex justify-end mt-3",
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-2",
    )


def render_student_submission_row(item: SubmissionRow) -> Div:
    """Render a submission row in the student-detail view with feedback toggle."""
    title = item.title or item.original_filename or "Untitled"

    exercise_label: Any = ""
    if item.exercise_title:
        exercise_label = Span(
            f"Exercise: {item.exercise_title}", cls="text-xs text-muted-foreground"
        )

    feedback_indicator: Any = ""
    if item.feedback_count > 0:
        feedback_indicator = Badge(
            f"{item.feedback_count} feedback",
            variant=BadgeT.info,
            size=Size.sm,
        )

    feedback_toggle: Any = ""
    if item.feedback_count > 0:
        feedback_toggle = Div(
            Button(
                "View Feedback",
                variant=ButtonT.ghost,
                size=Size.xs,
                **{
                    "hx-get": f"/api/submissions/{item.uid}/feedback",
                    "hx-target": f"#feedback-{item.uid}",
                    "hx-swap": "innerHTML",
                },
            ),
            Div(id=f"feedback-{item.uid}"),
            cls="mt-2",
        )

    return Card(
        CardBody(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    exercise_label,
                    cls="flex-1",
                ),
                Div(
                    feedback_indicator,
                    status_badge(item.status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                ButtonLink(
                    "Review",
                    href=f"/teaching/review/{item.uid}",
                    variant=ButtonT.primary,
                    size=Size.sm,
                ),
                cls="flex justify-end mt-3",
            ),
            feedback_toggle,
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-2",
    )


def render_class_member_row(item: ClassMember) -> Div:
    """Render a member row in the class detail view."""
    pending_variant = BadgeT.warning if item.pending_count > 0 else BadgeT.ghost

    return Card(
        CardBody(
            Div(
                Div(
                    H4(item.user_name, cls="mb-0 font-semibold"),
                    P(f"{item.role} · {item.user_uid}", cls="text-xs text-foreground/40 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    Badge(f"{item.pending_count} pending", variant=pending_variant),
                    Badge(
                        f"{item.reviewed_count}/{item.submission_count} reviewed",
                        variant=BadgeT.ghost,
                    ),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                ButtonLink(
                    "View Submissions",
                    href=f"/teaching/students/{item.user_uid}",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="flex justify-end mt-3",
            ),
            cls="p-4",
        ),
        cls="bg-background shadow-sm mb-2",
    )
