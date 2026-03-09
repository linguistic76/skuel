"""
Teaching UI Cards
=================

Dashboard, stat, and summary card components for teaching views.
"""

from typing import Any

from fasthtml.common import H3, H4, A, Div, P, Span

from ui.teaching.badges import entity_type_badge, status_badge


def render_empty_state(title: str, description: str) -> Div:
    """Render a centered empty state with title and description."""
    return Div(
        Div(
            H3(title, cls="text-lg font-medium mb-2"),
            P(description, cls="text-base-content/60"),
            cls="text-center py-12",
        ),
    )


def get_display_title(item: dict[str, Any]) -> str:
    """Get display title from an item dict, with fallbacks."""
    return item.get("title") or item.get("original_filename") or "Untitled"


def render_stat_card(label: str, value: int, icon: str, href: str, badge_cls: str = "") -> Div:
    """Render a single stat card linking to the relevant section."""
    value_cls = f"stat-value {badge_cls}" if badge_cls else "stat-value"
    return Div(
        Div(
            Div(icon, cls="stat-figure text-2xl"),
            Div(label, cls="stat-title"),
            Div(str(value), cls=value_cls),
            cls="stat",
        ),
        cls="card bg-base-100 shadow-sm cursor-pointer hover:shadow-md transition-shadow",
        **{"onclick": f"window.location='{href}'"},
    )


def render_dashboard(stats: dict[str, Any]) -> Div:
    """Render the overview dashboard with stat cards and quick links."""
    pending = stats.get("pending_count", 0)
    pending_badge = "text-warning" if pending > 0 else ""

    return Div(
        Div(
            render_stat_card("Pending Reviews", pending, "📥", "/teaching/queue", pending_badge),
            render_stat_card(
                "Students", stats.get("total_students", 0), "👥", "/teaching/students"
            ),
            render_stat_card(
                "Exercises", stats.get("total_exercises", 0), "📋", "/teaching/exercises"
            ),
            render_stat_card("Classes", stats.get("total_groups", 0), "🏫", "/teaching/classes"),
            cls="grid grid-cols-2 gap-4 mb-6",
        ),
        Div(
            A(
                "Go to Review Queue →",
                href="/teaching/queue",
                cls="btn btn-primary",
            ),
            cls="mt-2",
        )
        if pending > 0
        else Div(
            P("No submissions pending review.", cls="text-base-content/60"),
        ),
    )


def render_queue_item(item: dict[str, Any]) -> Div:
    """Render a single review queue item as a card."""
    title = get_display_title(item)
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
    status = item.get("status") or "unknown"
    entity_type = item.get("entity_type")
    project_name = item.get("project_name")
    ku_uid = item.get("ku_uid", "")
    feedback_count = item.get("feedback_count", 0)

    subtitle_parts = [f"by {student_name}"]
    if project_name:
        subtitle_parts.append(f"for {project_name}")

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
                    P(" · ".join(subtitle_parts), cls="text-sm text-base-content/60 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    feedback_indicator,
                    entity_type_badge(entity_type),
                    status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Review",
                    href=f"/teaching/review/{ku_uid}",
                    cls="btn btn-sm btn-primary",
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_exercise_summary_card(item: dict[str, Any]) -> Div:
    """Render an exercise card with submission counts and a link."""
    title = item.get("title") or "Untitled Exercise"
    uid = item.get("uid", "")
    scope = item.get("scope")
    total_count = item.get("total_count", 0)
    reviewed_count = item.get("reviewed_count", 0)
    pending_count = item.get("pending_count", 0)

    scope_badge = Span(scope, cls="badge badge-outline badge-sm") if scope else ""
    pending_badge_cls = "badge-warning" if pending_count > 0 else "badge-ghost"

    return Div(
        Div(
            Div(
                Div(
                    H4(title, cls="mb-0 font-semibold"),
                    Div(scope_badge, cls="mt-1") if scope else "",
                    cls="flex-1",
                ),
                Div(
                    Span(f"{pending_count} pending", cls=f"badge {pending_badge_cls}"),
                    Span(f"{reviewed_count}/{total_count} reviewed", cls="badge badge-ghost"),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Edit",
                    href=f"/teaching/exercises/{uid}/edit",
                    cls="btn btn-sm btn-ghost",
                ),
                A(
                    "View Submissions",
                    href=f"/teaching/exercises/{uid}/submissions",
                    cls="btn btn-sm btn-primary",
                ),
                cls="flex gap-2 justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_student_summary_card(item: dict[str, Any]) -> Div:
    """Render a student card with submission counts and a link."""
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
    student_uid = item.get("student_uid", "")
    submission_count = item.get("submission_count", 0)
    reviewed_count = item.get("reviewed_count", 0)
    pending_count = item.get("pending_count", 0)

    pending_badge_cls = "badge-warning" if pending_count > 0 else "badge-ghost"

    return Div(
        Div(
            Div(
                Div(
                    H4(student_name, cls="mb-0 font-semibold"),
                    P(student_uid, cls="text-xs text-base-content/40 mb-0"),
                    cls="flex-1",
                ),
                Div(
                    Span(f"{pending_count} pending", cls=f"badge {pending_badge_cls}"),
                    Span(
                        f"{reviewed_count}/{submission_count} reviewed",
                        cls="badge badge-ghost",
                    ),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "View Student",
                    href=f"/teaching/students/{student_uid}",
                    cls="btn btn-sm btn-primary",
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def render_class_card(item: dict[str, Any]) -> Div:
    """Render a class (group) card with member/exercise/pending counts."""
    name = item.get("name") or "Unnamed Class"
    uid = item.get("uid", "")
    description = item.get("description")
    member_count = item.get("member_count", 0)
    exercise_count = item.get("exercise_count", 0)
    pending_count = item.get("pending_count", 0)
    is_active = item.get("is_active", True)

    pending_badge_cls = "badge-warning" if pending_count > 0 else "badge-ghost"
    active_badge: Any = "" if is_active else Span("Inactive", cls="badge badge-ghost badge-sm")

    return Div(
        Div(
            Div(
                Div(
                    Div(
                        H4(name, cls="mb-0 font-semibold"),
                        active_badge,
                        cls="flex items-center gap-2",
                    ),
                    P(description, cls="text-sm text-base-content/60 mb-0 mt-1")
                    if description
                    else "",
                    cls="flex-1",
                ),
                Div(
                    Span(f"{pending_count} pending", cls=f"badge {pending_badge_cls}"),
                    Span(f"{member_count} students", cls="badge badge-ghost"),
                    Span(f"{exercise_count} exercises", cls="badge badge-ghost"),
                    cls="flex gap-2 items-center flex-wrap",
                ),
                cls="flex items-start justify-between gap-4",
            ),
            Div(
                A(
                    "View Class",
                    href=f"/teaching/classes/{uid}",
                    cls="btn btn-sm btn-primary",
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )
