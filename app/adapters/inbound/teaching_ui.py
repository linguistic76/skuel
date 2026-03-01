"""
Teaching UI Routes — Teacher Dashboard
========================================

Teacher-facing pages for the full teaching workflow:
- Overview dashboard with at-a-glance stats
- Review queue and approved submissions
- By-exercise and by-student views
- Classes (groups) management
- Submission review with content display

TEACHER role required for all endpoints.

Layout: Unified sidebar (Tailwind + Alpine) with teaching navigation.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    H4,
    A,
    Div,
    Form,
    Input,
    Label,
    P,
    Span,
    Textarea,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from core.utils.logging import get_logger
from ui.daisy_components import Button, ButtonT, Option, Select
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger("skuel.routes.teaching.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

TEACHING_SIDEBAR_ITEMS = [
    SidebarItem("Overview", "/teaching", "overview", icon="📊"),
    SidebarItem("Review Queue", "/teaching/queue", "queue", icon="📥"),
    SidebarItem("Approved", "/teaching/approved", "approved", icon="✅"),
    SidebarItem("By Exercise", "/teaching/exercises", "exercises", icon="📋"),
    SidebarItem("By Student", "/teaching/students", "students", icon="👥"),
    SidebarItem("Classes", "/teaching/classes", "classes", icon="🏫"),
]

_SIDEBAR_DEFAULTS = {
    "title": "Teaching",
    "subtitle": "Manage student work",
    "storage_key": "teaching-sidebar",
    "active_page": "teaching",
    "title_href": "/teaching",
}


# ============================================================================
# HELPERS — STATUS + TYPE BADGES
# ============================================================================


def _status_badge(status: str) -> Span:
    """Render a DaisyUI badge for entity status."""
    badge_classes = {
        "submitted": "badge-warning",
        "active": "badge-info",
        "completed": "badge-success",
        "revision_requested": "badge-error",
        "draft": "badge-ghost",
    }
    cls = badge_classes.get(status, "badge-ghost")
    label = status.replace("_", " ").title()
    return Span(label, cls=f"badge {cls}")


def _entity_type_badge(ku_type: str | None) -> Span:
    """Render a DaisyUI badge for entity type."""
    if not ku_type:
        return Span()
    label = ku_type.replace("_", " ").title()
    return Span(label, cls="badge badge-outline badge-sm")


# ============================================================================
# HELPERS — DASHBOARD OVERVIEW
# ============================================================================


def _render_stat_card(label: str, value: int, icon: str, href: str, badge_cls: str = "") -> Div:
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


def _render_dashboard(stats: dict[str, Any]) -> Div:
    """Render the overview dashboard with stat cards and quick links."""
    pending = stats.get("pending_count", 0)
    pending_badge = "text-warning" if pending > 0 else ""

    return Div(
        Div(
            _render_stat_card("Pending Reviews", pending, "📥", "/teaching/queue", pending_badge),
            _render_stat_card(
                "Students", stats.get("total_students", 0), "👥", "/teaching/students"
            ),
            _render_stat_card(
                "Exercises", stats.get("total_exercises", 0), "📋", "/teaching/exercises"
            ),
            _render_stat_card("Classes", stats.get("total_groups", 0), "🏫", "/teaching/classes"),
            cls="grid grid-cols-2 gap-4 mb-6",
        ),
        Div(
            A(
                "Go to Review Queue →",
                href="/teaching/queue",
                cls="btn btn-primary",
                **{"hx-boost": "false"},
            ),
            cls="mt-2",
        )
        if pending > 0
        else Div(
            P("No submissions pending review.", cls="text-base-content/60"),
        ),
    )


# ============================================================================
# HELPERS — REVIEW QUEUE ITEMS
# ============================================================================


def _render_queue_item(item: dict[str, Any]) -> Div:
    """Render a single review queue item as a card."""
    title = item.get("title") or "Untitled"
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
    status = item.get("status") or "unknown"
    ku_type = item.get("ku_type")
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
                    _entity_type_badge(ku_type),
                    _status_badge(status),
                    cls="flex gap-2 items-center",
                ),
                cls="flex items-center justify-between gap-4",
            ),
            Div(
                A(
                    "Review",
                    href=f"/teaching/review/{ku_uid}",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_queue_empty() -> Div:
    """Render empty state for review queue."""
    return Div(
        Div(
            H3("No submissions to review", cls="text-lg font-medium mb-2"),
            P(
                "When students submit work against your assignments, it will appear here.",
                cls="text-base-content/60",
            ),
            cls="text-center py-12",
        ),
    )


# ============================================================================
# HELPERS — FEEDBACK HISTORY
# ============================================================================


def _render_feedback_item(fb: dict[str, Any]) -> Div:
    """Render a single feedback history item."""
    teacher_name = fb.get("teacher_name") or fb.get("teacher_uid") or "Teacher"
    content = fb.get("content") or ""
    created_at = fb.get("created_at", "")
    title = fb.get("title", "")

    time_display = ""
    if created_at:
        if isinstance(created_at, datetime):
            time_display = created_at.strftime("%b %d, %H:%M")
        else:
            time_display = str(created_at)[:16]

    is_revision = "revision" in title.lower() if title else False
    border_cls = "border-l-warning" if is_revision else "border-l-info"
    type_label = "Revision Request" if is_revision else "SubmissionFeedback"

    return Div(
        Div(
            Div(
                Span(type_label, cls="font-medium text-sm"),
                Span(f" by {teacher_name}", cls="text-sm text-base-content/60"),
                Span(f" · {time_display}", cls="text-xs text-base-content/40")
                if time_display
                else "",
                cls="mb-1",
            ),
            P(content, cls="text-sm whitespace-pre-wrap"),
            cls="p-3",
        ),
        cls=f"border-l-4 {border_cls} bg-base-200/50 rounded-r mb-2",
    )


# ============================================================================
# HELPERS — SUBMISSION CONTENT DISPLAY
# ============================================================================


def _render_submission_content(detail: dict[str, Any]) -> Div:
    """
    Render the submission content card for teacher review.

    Shows processed_content if available, then content, then filename as fallback.
    Also surfaces exercise instructions for teacher reference.
    """
    title = detail.get("title") or "Untitled"
    ku_type = detail.get("ku_type")
    status = detail.get("status") or ""
    student_name = detail.get("student_name") or detail.get("student_uid") or "Unknown"
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
                    _entity_type_badge(ku_type),
                    _status_badge(status),
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


# ============================================================================
# HELPERS — EXERCISE CARDS + ROWS
# ============================================================================


def _render_exercise_summary_card(item: dict[str, Any]) -> Div:
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
                    **{"hx-boost": "false"},
                ),
                A(
                    "View Submissions",
                    href=f"/teaching/exercises/{uid}/submissions",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex gap-2 justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_exercise_form(groups: list[dict[str, Any]], exercise: Any = None) -> Div:
    """Render create/edit exercise form with Alpine.js scope toggle."""
    is_edit = exercise is not None
    uid = getattr(exercise, "uid", "") if exercise else ""
    post_url = f"/api/teaching/exercises/{uid}" if is_edit else "/api/teaching/exercises"

    name_val = getattr(exercise, "title", "") or ""
    instructions_val = getattr(exercise, "instructions", "") or ""
    model_val = getattr(exercise, "model", "claude-sonnet-4-6") or "claude-sonnet-4-6"

    scope_raw = getattr(exercise, "scope", None)
    _no_value = object()
    _scope_value = getattr(scope_raw, "value", _no_value) if scope_raw is not None else _no_value
    scope_str = str(_scope_value) if _scope_value is not _no_value else "personal"
    group_uid_val = getattr(exercise, "group_uid", "") or ""

    due_date_raw = getattr(exercise, "due_date", None)
    due_date_val = str(due_date_raw) if due_date_raw else ""

    context_notes_raw = getattr(exercise, "context_notes", ()) or ()
    context_notes_str = "\n".join(context_notes_raw)
    notes_open = "true" if context_notes_str else "false"

    group_options: list[Any] = [
        Option("-- Select group --", value="", disabled=True, selected=not group_uid_val)
    ]
    for group in groups:
        g_name = group.get("name") or group.get("uid", "Unknown")
        g_uid = group.get("uid", "")
        group_options.append(Option(g_name, value=g_uid, selected=(g_uid == group_uid_val)))

    model_choices = [
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 (Recommended)"),
        ("claude-opus-4-6", "Claude Opus 4.6 (Most Capable)"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (Fastest)"),
        ("gpt-4o", "GPT-4o"),
        ("gpt-4o-mini", "GPT-4o Mini (Cheaper)"),
    ]
    model_options: list[Any] = [
        Option(label, value=val, selected=(val == model_val)) for val, label in model_choices
    ]

    after_request_js = (
        "if(event.detail.successful){"
        "window.location='/teaching/exercises';"
        "}else{"
        "try{"
        "var d=JSON.parse(event.detail.xhr.responseText);"
        "document.getElementById('form-result').innerHTML="
        "'<div class=\"alert alert-error mt-2\">'+(d.message||'Error saving exercise')+'</div>';"
        "}catch(e){}"
        "}"
    )

    return Div(
        Form(
            Div(
                Label("Name", cls="label-text font-medium"),
                Input(
                    type="text",
                    name="name",
                    value=name_val,
                    placeholder="e.g., Daily Reflection, Principle Mining",
                    cls="input input-bordered w-full",
                    required=True,
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("Instructions (visible to students & LLM)", cls="label-text font-medium"),
                Textarea(
                    instructions_val,
                    name="instructions",
                    placeholder="Write the instructions for students and the LLM...",
                    cls="textarea textarea-bordered w-full h-40",
                    required=True,
                ),
                cls="form-control mb-4",
            ),
            Div(
                Label("LLM Model", cls="label-text font-medium"),
                Select(*model_options, name="model", cls="select select-bordered w-full"),
                cls="form-control mb-4",
            ),
            Div(
                Label("Scope", cls="label-text font-medium"),
                Div(
                    Label(
                        Input(
                            type="radio",
                            name="scope",
                            value="personal",
                            cls="radio radio-sm mr-2",
                            **{"x-model": "scope"},
                        ),
                        "Personal",
                        cls="label cursor-pointer gap-2 justify-start",
                    ),
                    Label(
                        Input(
                            type="radio",
                            name="scope",
                            value="assigned",
                            cls="radio radio-sm mr-2",
                            **{"x-model": "scope"},
                        ),
                        "Assigned to group",
                        cls="label cursor-pointer gap-2 justify-start",
                    ),
                    cls="flex gap-6",
                ),
                cls="form-control mb-4",
            ),
            Div(
                Div(
                    Label("Group", cls="label-text font-medium"),
                    Select(*group_options, name="group_uid", cls="select select-bordered w-full"),
                    cls="form-control mb-3",
                ),
                Div(
                    Label("Due Date", cls="label-text font-medium"),
                    Input(
                        type="date",
                        name="due_date",
                        value=due_date_val,
                        cls="input input-bordered w-full",
                    ),
                    cls="form-control mb-3",
                ),
                **{"x-show": "scope === 'assigned'"},
            ),
            Div(
                Div(
                    P(
                        "▶ Context Notes (optional)",
                        cls="font-medium text-sm mb-1 cursor-pointer",
                        **{
                            "x-on:click": "notesOpen = !notesOpen",
                            "x-text": "notesOpen ? '▼ Context Notes (optional)' : '▶ Context Notes (optional)'",
                        },
                    ),
                ),
                Div(
                    P(
                        "One note per line — reference materials the LLM should consider.",
                        cls="text-xs text-base-content/60 mb-1",
                    ),
                    Textarea(
                        context_notes_str,
                        name="context_notes",
                        placeholder="Focus on self-awareness\nBe gentle and curious",
                        cls="textarea textarea-bordered w-full h-24",
                    ),
                    **{"x-show": "notesOpen"},
                ),
                cls="form-control mb-4",
            ),
            Div(
                Button(
                    "Save Exercise" if is_edit else "Create Exercise",
                    variant=ButtonT.primary,
                    type="submit",
                ),
                cls="mt-2",
            ),
            Div(id="form-result", cls="mt-3"),
            **{
                "hx-post": post_url,
                "hx-target": "#form-result",
                "hx-swap": "innerHTML",
                "hx-on::after-request": after_request_js,
            },
        ),
        **{"x-data": f"{{ scope: '{scope_str}', notesOpen: {notes_open} }}"},
    )


def _render_exercise_submission_row(item: dict[str, Any]) -> Div:
    """Render a submission row in the exercise-detail view."""
    title = item.get("title") or item.get("original_filename") or "Untitled"
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
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
                    _status_badge(status),
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


# ============================================================================
# HELPERS — STUDENT CARDS + ROWS
# ============================================================================


def _render_student_summary_card(item: dict[str, Any]) -> Div:
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
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_student_submission_row(item: dict[str, Any]) -> Div:
    """Render a submission row in the student-detail view with feedback toggle."""
    title = item.get("title") or item.get("original_filename") or "Untitled"
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
                    _status_badge(status),
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


# ============================================================================
# HELPERS — CLASS (GROUP) CARDS + ROWS
# ============================================================================


def _render_class_card(item: dict[str, Any]) -> Div:
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
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_class_member_row(item: dict[str, Any]) -> Div:
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


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_teaching_ui_routes(
    _app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
    exercises_service: Any = None,
) -> list[Any]:
    """
    Create teaching UI routes for the full teacher dashboard.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
        exercises_service: ExerciseService for create/edit forms
    """

    def get_user_service() -> Any:
        return user_service

    # ------------------------------------------------------------------
    # OVERVIEW / DASHBOARD
    # ------------------------------------------------------------------

    @rt("/teaching")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_overview_page(request: Request, current_user: Any = None) -> Any:
        """Dashboard overview — at-a-glance stats for the teacher."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_dashboard_stats(teacher_uid=user_uid)
        stats = result.value if result.is_ok else {}

        content = Div(
            PageHeader("Teaching Overview", subtitle="Your teaching activity at a glance"),
            _render_dashboard(stats),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="overview",
            page_title="Teaching Overview",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # REVIEW QUEUE
    # ------------------------------------------------------------------

    @rt("/teaching/queue")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_queue_page(request: Request, current_user: Any = None) -> Any:
        """Review queue — pending student submissions."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_review_queue(teacher_uid=user_uid)

        if result.is_error:
            queue_content: Any = Div(
                P("Failed to load review queue", cls="text-center text-error"),
            )
        elif not result.value:
            queue_content = _render_queue_empty()
        else:
            queue_content = Div(*[_render_queue_item(item) for item in result.value])

        content = Div(
            PageHeader("Review Queue", subtitle="Student submissions awaiting your review"),
            queue_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="queue",
            page_title="Review Queue",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # APPROVED
    # ------------------------------------------------------------------

    @rt("/teaching/approved")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_approved_page(request: Request, current_user: Any = None) -> Any:
        """Approved submissions — completed reviews."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_review_queue(
            teacher_uid=user_uid, status_filter="completed"
        )

        if result.is_error:
            list_content: Any = Div(
                P("Failed to load approved submissions", cls="text-center text-error"),
            )
        elif not result.value:
            list_content = Div(
                P("No approved submissions yet.", cls="text-center text-base-content/60 py-8"),
            )
        else:
            list_content = Div(*[_render_queue_item(item) for item in result.value])

        content = Div(
            PageHeader("Approved", subtitle="Submissions you have reviewed and approved"),
            list_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="approved",
            page_title="Approved Submissions",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # REVIEW DETAIL
    # ------------------------------------------------------------------

    @rt("/teaching/review/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_review_detail(request: Request, uid: str, current_user: Any = None) -> Any:
        """Review detail — submission content + feedback history + action form."""
        user_uid = require_authenticated_user(request)

        # Fetch submission content
        detail_result = await teacher_review_service.get_submission_detail(
            submission_uid=uid, teacher_uid=user_uid
        )
        submission_section: Any = ""
        if detail_result.is_ok and detail_result.value:
            submission_section = _render_submission_content(detail_result.value)
        else:
            submission_section = Div(
                P("Submission content unavailable.", cls="text-sm text-base-content/50 italic"),
                cls="mb-4",
            )

        # Fetch feedback history
        feedback_history_section: Any = ""
        history_result = await teacher_review_service.get_feedback_history(uid)
        if not history_result.is_error and history_result.value:
            feedback_items = [_render_feedback_item(fb) for fb in history_result.value]
            feedback_history_section = Div(
                H3("Feedback History", cls="text-lg font-semibold mb-3"),
                Div(*feedback_items),
                cls="mb-6",
            )

        content = Div(
            PageHeader("Review Submission"),
            # Submission content
            submission_section,
            # Feedback history (if any)
            feedback_history_section,
            # Feedback form
            Div(
                Div(
                    Form(
                        Div(
                            Textarea(
                                name="feedback",
                                placeholder="Write your feedback here...",
                                cls="textarea textarea-bordered w-full h-32",
                                required=True,
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            Button(
                                "Submit Feedback",
                                variant=ButtonT.primary,
                                type="submit",
                            ),
                            cls="mb-2",
                        ),
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/feedback",
                            "hx-target": "#review-result",
                            "hx-swap": "innerHTML",
                        },
                        id="feedback-form",
                    ),
                    Div(
                        Div(
                            Button(
                                "Request Revision",
                                variant=ButtonT.warning,
                                type="button",
                                **{
                                    "hx-post": f"/api/teaching/review/{uid}/revision",
                                    "hx-target": "#review-result",
                                    "hx-swap": "innerHTML",
                                    "hx-include": "#feedback-form",
                                    "hx-vals": '{"notes": ""}',
                                },
                            ),
                            Button(
                                "Approve",
                                variant=ButtonT.success,
                                type="button",
                                **{
                                    "hx-post": f"/api/teaching/review/{uid}/approve",
                                    "hx-target": "#review-result",
                                    "hx-swap": "innerHTML",
                                    "hx-confirm": "Approve this submission?",
                                },
                            ),
                            cls="flex gap-3",
                        ),
                        cls="mt-4",
                    ),
                    Div(id="review-result", cls="mt-4"),
                    cls="card-body",
                ),
                cls="card bg-base-100 shadow-sm",
            ),
            Div(
                A(
                    "Back to Queue",
                    href="/teaching/queue",
                    cls="btn btn-ghost btn-sm mt-4",
                    **{"hx-boost": "false"},
                ),
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="queue",
            page_title="Review Submission",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # BY EXERCISE
    # ------------------------------------------------------------------

    @rt("/teaching/exercises")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_exercises_page(request: Request, current_user: Any = None) -> Any:
        """By Exercise page — teacher's exercises with submission counts."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=user_uid
        )

        if result.is_error:
            page_content: Any = Div(
                P("Failed to load exercises", cls="text-center text-error"),
            )
        elif not result.value:
            page_content = Div(
                Div(
                    H3("No exercises yet", cls="text-lg font-medium mb-2"),
                    P(
                        "Exercises you create will appear here with submission counts.",
                        cls="text-base-content/60",
                    ),
                    cls="text-center py-12",
                ),
            )
        else:
            page_content = Div(*[_render_exercise_summary_card(item) for item in result.value])

        content = Div(
            PageHeader("By Exercise", subtitle="Submissions grouped by exercise"),
            Div(
                A(
                    "+ New Exercise",
                    href="/teaching/exercises/new",
                    cls="btn btn-primary btn-sm mb-4",
                    **{"hx-boost": "false"},
                ),
            ),
            page_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="exercises",
            page_title="By Exercise",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/exercises/new")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_new_exercise_page(request: Request, current_user: Any = None) -> Any:
        """New exercise form — create a teaching exercise."""
        user_uid = require_authenticated_user(request)

        groups_result = await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=user_uid
        )
        groups = groups_result.value if groups_result.is_ok else []

        content = Div(
            PageHeader("New Exercise", subtitle="Create an exercise for your students"),
            _render_exercise_form(groups),
            A(
                "← Back to Exercises",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
                **{"hx-boost": "false"},
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="exercises",
            page_title="New Exercise",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/exercises/{uid}/edit")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_edit_exercise_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Edit exercise form — update an existing exercise."""
        user_uid = require_authenticated_user(request)

        exercise: Any = None
        if exercises_service:
            exercise_result = await exercises_service.get_exercise(uid)
            exercise = exercise_result.value if exercise_result.is_ok else None

        groups_result = await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=user_uid
        )
        groups = groups_result.value if groups_result.is_ok else []

        title = getattr(exercise, "title", uid) if exercise else uid
        content = Div(
            PageHeader(f"Edit: {title}", subtitle="Update exercise details"),
            _render_exercise_form(groups, exercise=exercise),
            A(
                "← Back to Exercises",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
                **{"hx-boost": "false"},
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="exercises",
            page_title="Edit Exercise",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/exercises/{uid}/submissions")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_exercise_submissions_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Exercise submissions page — all submissions against a specific exercise."""
        result = await teacher_review_service.get_submissions_for_exercise(exercise_uid=uid)

        if result.is_error:
            rows: Any = Div(P("Failed to load submissions", cls="text-center text-error"))
        elif not result.value:
            rows = Div(
                P(
                    "No submissions yet for this exercise.",
                    cls="text-center text-base-content/60 py-8",
                )
            )
        else:
            rows = Div(*[_render_exercise_submission_row(item) for item in result.value])

        back_link = Div(
            A(
                "← By Exercise",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
                **{"hx-boost": "false"},
            ),
        )

        content = Div(
            PageHeader("Exercise Submissions", subtitle=f"Exercise: {uid}"),
            rows,
            back_link,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="exercises",
            page_title="Exercise Submissions",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # BY STUDENT
    # ------------------------------------------------------------------

    @rt("/teaching/students")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_students_page(request: Request, current_user: Any = None) -> Any:
        """By Student page — students who shared work with the teacher."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_students_summary(teacher_uid=user_uid)

        if result.is_error:
            students_content: Any = Div(
                P("Failed to load students", cls="text-center text-error"),
            )
        elif not result.value:
            students_content = Div(
                Div(
                    H3("No students yet", cls="text-lg font-medium mb-2"),
                    P(
                        "Students who share work with you will appear here.",
                        cls="text-base-content/60",
                    ),
                    cls="text-center py-12",
                ),
            )
        else:
            students_content = Div(*[_render_student_summary_card(item) for item in result.value])

        content = Div(
            PageHeader("By Student", subtitle="Students who have shared work with you"),
            students_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="students",
            page_title="By Student",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/students/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_student_detail_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Student detail page — all submissions from a specific student."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_student_submissions(
            teacher_uid=user_uid, student_uid=uid
        )

        if result.is_error:
            submission_rows: Any = Div(
                P("Failed to load submissions", cls="text-center text-error")
            )
        elif not result.value:
            submission_rows = Div(
                P(
                    "No submissions from this student.",
                    cls="text-center text-base-content/60 py-8",
                )
            )
        else:
            submission_rows = Div(*[_render_student_submission_row(item) for item in result.value])

        back_link = Div(
            A(
                "← By Student",
                href="/teaching/students",
                cls="btn btn-ghost btn-sm mt-4",
                **{"hx-boost": "false"},
            ),
        )

        content = Div(
            PageHeader(f"Student: {uid}", subtitle="All submissions shared with you"),
            submission_rows,
            back_link,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="students",
            page_title="Student Detail",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # CLASSES (GROUPS)
    # ------------------------------------------------------------------

    @rt("/teaching/classes")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_classes_page(request: Request, current_user: Any = None) -> Any:
        """Classes page — teacher's groups with student and exercise counts."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_teacher_groups_with_stats(teacher_uid=user_uid)

        if result.is_error:
            classes_content: Any = Div(
                P("Failed to load classes", cls="text-center text-error"),
            )
        elif not result.value:
            classes_content = Div(
                Div(
                    H3("No classes yet", cls="text-lg font-medium mb-2"),
                    P(
                        "Create your first class from the Groups section to get started.",
                        cls="text-base-content/60",
                    ),
                    A(
                        "Go to Groups →",
                        href="/groups",
                        cls="btn btn-primary btn-sm mt-4",
                        **{"hx-boost": "false"},
                    ),
                    cls="text-center py-12",
                ),
            )
        else:
            classes_content = Div(*[_render_class_card(item) for item in result.value])

        content = Div(
            PageHeader("Classes", subtitle="Your groups and their activity"),
            classes_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="classes",
            page_title="Classes",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/classes/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_class_detail_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Class detail page — members with submission progress stats."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_group_detail(group_uid=uid, teacher_uid=user_uid)

        if result.is_error:
            members_content: Any = Div(
                P("Failed to load class members", cls="text-center text-error")
            )
        elif not result.value:
            members_content = Div(
                P("No members in this class yet.", cls="text-center text-base-content/60 py-8")
            )
        else:
            members_content = Div(*[_render_class_member_row(item) for item in result.value])

        back_link = Div(
            A(
                "← Classes",
                href="/teaching/classes",
                cls="btn btn-ghost btn-sm mt-4",
                **{"hx-boost": "false"},
            ),
        )

        content = Div(
            PageHeader(f"Class: {uid}", subtitle="Members and their submission progress"),
            members_content,
            back_link,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="classes",
            page_title="Class Detail",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    logger.info("Teaching UI routes registered")
    return []
