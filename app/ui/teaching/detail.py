"""
Teaching UI Detail Components
=============================

Submission content display and row components for detail views.
"""

from typing import Any

from fasthtml.common import H4, A, Div, P, Span

from ui.teaching.badges import entity_type_badge, status_badge
from ui.teaching.cards import get_display_title


def get_student_name(item: dict[str, Any]) -> str:
    """Get student display name from an item dict, with fallbacks."""
    return item.get("student_name") or item.get("student_uid") or "Unknown"


def render_submission_content(detail: dict[str, Any]) -> Div:
    """
    Render the submission content card for teacher review.

    Shows processed_content if available, then content, then filename as fallback.
    Also surfaces exercise instructions for teacher reference.
    """
    title = detail.get("title") or "Untitled"
    entity_type = detail.get("entity_type")
    status = detail.get("status") or ""
    student_name = get_student_name(detail)
    exercise_title = detail.get("exercise_title")
    exercise_instructions = detail.get("exercise_instructions")

    # Display content — prefer processed, fall back to raw, then filename
    display_content = (
        detail.get("processed_content")
        or detail.get("content")
        or detail.get("original_filename")
        or "(No content available)"
    )

    meta_parts = [f"by {student_name}"]
    if exercise_title:
        meta_parts.append(f"Exercise: {exercise_title}")

    exercise_section: Any = ""
    if exercise_instructions:
        exercise_section = Div(
            Div(
                Span(
                    "Exercise instructions",
                    cls="text-xs font-semibold text-base-content/50 uppercase tracking-wide",
                ),
                P(
                    exercise_instructions,
                    cls="text-sm text-base-content/70 whitespace-pre-wrap mt-1",
                ),
                cls="p-3 bg-base-200/50 rounded",
            ),
            cls="mb-3",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="font-semibold mb-1"),
                    P(" · ".join(meta_parts), cls="text-sm text-base-content/60 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    entity_type_badge(entity_type),
                    status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-start justify-between gap-4 mb-4",
            ),
            exercise_section,
            Div(
                Span(
                    "Submission content",
                    cls="text-xs font-semibold text-base-content/50 uppercase tracking-wide",
                ),
                P(display_content, cls="text-sm whitespace-pre-wrap mt-1"),
                cls="p-3 bg-base-200/30 rounded border border-base-300",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-4",
    )


def render_feedback_item(fb: dict[str, Any]) -> Div:
    """Render a single feedback history item. Delegates to shared component."""
    from ui.patterns.feedback_item import render_feedback_item as _shared_render

    return _shared_render(fb)


def render_exercise_submission_row(item: dict[str, Any]) -> Div:
    """Render a submission row in the exercise-detail view."""
    title = get_display_title(item)
    student_name = get_student_name(item)
    status = item.get("status") or "unknown"
    uid = item.get("uid", "")
    feedback_count = item.get("feedback_count", 0)

    feedback_indicator: Any = ""
    if feedback_count > 0:
        feedback_indicator = Span(
            f"{feedback_count} feedback",
            cls="badge badge-sm badge-info",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    P(f"by {student_name}", cls="text-sm text-base-content/60 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    feedback_indicator,
                    status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Review",
                    href=f"/teaching/review/{uid}",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_student_submission_row(item: dict[str, Any]) -> Div:
    """Render a submission row in the student-detail view with feedback toggle."""
    title = get_display_title(item)
    status = item.get("status") or "unknown"
    uid = item.get("uid", "")
    feedback_count = item.get("feedback_count", 0)
    exercise_title = item.get("exercise_title")

    exercise_label: Any = ""
    if exercise_title:
        exercise_label = Span(f"Exercise: {exercise_title}", cls="text-xs text-base-content/50")

    feedback_indicator: Any = ""
    if feedback_count > 0:
        feedback_indicator = Span(
            f"{feedback_count} feedback",
            cls="badge badge-sm badge-info",
        )

    feedback_toggle: Any = ""
    if feedback_count > 0:
        feedback_toggle = Div(
            A(
                "View Feedback",
                cls="btn btn-xs btn-ghost",
                **{
                    "hx-get": f"/api/submissions/{uid}/feedback",
                    "hx-target": f"#feedback-{uid}",
                    "hx-swap": "innerHTML",
                },
            ),
            Div(id=f"feedback-{uid}"),
            cls="mt-2",
        )

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    exercise_label,
                    cls="flex-1",
                ),
                Div(
                    feedback_indicator,
                    status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Review",
                    href=f"/teaching/review/{uid}",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            feedback_toggle,
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_class_member_row(item: dict[str, Any]) -> Div:
    """Render a member row in the class detail view."""
    user_name = item.get("user_name") or item.get("user_uid") or "Unknown"
    user_uid = item.get("user_uid", "")
    role = item.get("role") or "student"
    submission_count = item.get("submission_count", 0)
    reviewed_count = item.get("reviewed_count", 0)
    pending_count = item.get("pending_count", 0)

    pending_badge_cls = "badge-warning" if pending_count > 0 else "badge-ghost"

    return Div(
        Div(
            Div(
                Div(
                    H4(user_name, cls="mb-0 font-semibold"),
                    P(f"{role} · {user_uid}", cls="text-xs text-base-content/40 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    Span(f"{pending_count} pending", cls=f"badge {pending_badge_cls}"),
                    Span(f"{reviewed_count}/{submission_count} reviewed", cls="badge badge-ghost"),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "View Submissions",
                    href=f"/teaching/students/{user_uid}",
                    cls="btn btn-sm btn-ghost",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )
