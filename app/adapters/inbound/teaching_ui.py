"""
Teaching UI Routes — Teacher Review Queue
==========================================

Teacher-facing pages for reviewing student submissions.
Provides a review queue and detail view with feedback/revision/approve actions.

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
    P,
    Span,
    Textarea,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from core.utils.logging import get_logger
from ui.daisy_components import Button, ButtonT
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger("skuel.routes.teaching.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

TEACHING_SIDEBAR_ITEMS = [
    SidebarItem("Review Queue", "/teaching", "queue", icon="📥"),
    SidebarItem("Approved", "/teaching/approved", "approved", icon="✅"),
    SidebarItem("By Exercise", "/teaching/exercises", "exercises", icon="📋"),
    SidebarItem("By Student", "/teaching/students", "students", icon="👥"),
]


# ============================================================================
# HELPERS
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

    feedback_indicator = ""
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
    type_label = "Revision Request" if is_revision else "Feedback"

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
                    "View Submissions",
                    href=f"/teaching/exercises/{uid}/submissions",
                    cls="btn btn-sm btn-primary",
                    **{"hx-boost": "false"},
                ),
                cls="flex justify-end mt-3",
            ),
            cls="card-body p-4",
        ),
        cls="card bg-base-100 shadow-sm mb-2",
    )


def _render_exercise_submission_row(item: dict[str, Any]) -> Div:
    """Render a submission row in the exercise-detail view."""
    title = item.get("title") or item.get("original_filename") or "Untitled"
    student_name = item.get("student_name") or item.get("student_uid") or "Unknown"
    status = item.get("status") or "unknown"
    uid = item.get("uid", "")
    feedback_count = item.get("feedback_count", 0)

    feedback_indicator = ""
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

    exercise_label = ""
    if exercise_title:
        exercise_label = Span(f"Exercise: {exercise_title}", cls="text-xs text-base-content/50")

    feedback_indicator = ""
    if feedback_count > 0:
        feedback_indicator = Span(
            f"{feedback_count} feedback",
            cls="badge badge-sm badge-info",
        )

    feedback_toggle = ""
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
# ROUTE CREATION
# ============================================================================


def create_teaching_ui_routes(
    _app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
) -> list[Any]:
    """
    Create teaching UI routes for teacher review workflow.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
    """

    def get_user_service() -> Any:
        return user_service

    @rt("/teaching")
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
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Review Queue",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

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
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Approved Submissions",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

    @rt("/teaching/review/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_review_detail(request: Request, uid: str, current_user: Any = None) -> Any:
        """Review detail page — feedback form + action buttons + feedback history."""
        # Fetch feedback history for this submission
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
                    href="/teaching",
                    cls="btn btn-ghost btn-sm mt-4",
                    **{"hx-boost": "false"},
                ),
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="queue",
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Review Submission",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

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
            page_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="exercises",
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="By Exercise",
            request=request,
            active_page="teaching",
            title_href="/teaching",
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
                P("No submissions yet for this exercise.", cls="text-center text-base-content/60 py-8")
            )
        else:
            rows = Div(*[_render_exercise_submission_row(item) for item in result.value])

        back_link = Div(
            A("← By Exercise", href="/teaching/exercises", cls="btn btn-ghost btn-sm mt-4",
              **{"hx-boost": "false"}),
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
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Exercise Submissions",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

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
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="By Student",
            request=request,
            active_page="teaching",
            title_href="/teaching",
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
            submission_rows = Div(
                *[_render_student_submission_row(item) for item in result.value]
            )

        back_link = Div(
            A("← By Student", href="/teaching/students", cls="btn btn-ghost btn-sm mt-4",
              **{"hx-boost": "false"}),
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
            title="Teaching",
            subtitle="Review student work",
            storage_key="teaching-sidebar",
            page_title="Student Detail",
            request=request,
            active_page="teaching",
            title_href="/teaching",
        )

    logger.info("Teaching UI routes registered")
    return []
