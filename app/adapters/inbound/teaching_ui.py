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

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Div,
    Form,
    P,
    Textarea,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage
from ui.teaching.cards import (
    render_class_card,
    render_dashboard,
    render_empty_state,
    render_exercise_summary_card,
    render_queue_item,
    render_student_summary_card,
)
from ui.teaching.detail import (
    render_class_member_row,
    render_exercise_submission_row,
    render_report_item,
    render_student_submission_row,
    render_submission_content,
)
from ui.teaching.forms import render_exercise_form

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
            render_dashboard(stats),
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
            queue_content = render_empty_state(
                "No submissions to review",
                "When students submit work against your assignments, it will appear here.",
            )
        else:
            queue_content = Div(*[render_queue_item(item) for item in result.value])

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
            list_content = Div(*[render_queue_item(item) for item in result.value])

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
            submission_section = render_submission_content(detail_result.value)
        else:
            submission_section = Div(
                P("Submission content unavailable.", cls="text-sm text-base-content/50 italic"),
                cls="mb-4",
            )

        # Fetch feedback history
        feedback_history_section: Any = ""
        history_result = await teacher_review_service.get_report_history(uid)
        if not history_result.is_error and history_result.value:
            feedback_items = [render_report_item(fb) for fb in history_result.value]
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
                            "hx-post": f"/api/teaching/review/{uid}/report",
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
            page_content = render_empty_state(
                "No exercises yet",
                "Exercises you create will appear here with submission counts.",
            )
        else:
            page_content = Div(*[render_exercise_summary_card(item) for item in result.value])

        content = Div(
            PageHeader("By Exercise", subtitle="Submissions grouped by exercise"),
            Div(
                A(
                    "+ New Exercise",
                    href="/teaching/exercises/new",
                    cls="btn btn-primary btn-sm mb-4",
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
            render_exercise_form(groups),
            A(
                "← Back to Exercises",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
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
            render_exercise_form(groups, exercise=exercise),
            A(
                "← Back to Exercises",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
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
            rows = Div(*[render_exercise_submission_row(item) for item in result.value])

        back_link = Div(
            A(
                "← By Exercise",
                href="/teaching/exercises",
                cls="btn btn-ghost btn-sm mt-4",
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
            students_content = render_empty_state(
                "No students yet",
                "Students who share work with you will appear here.",
            )
        else:
            students_content = Div(*[render_student_summary_card(item) for item in result.value])

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
            submission_rows = Div(*[render_student_submission_row(item) for item in result.value])

        back_link = Div(
            A(
                "← By Student",
                href="/teaching/students",
                cls="btn btn-ghost btn-sm mt-4",
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
                    ),
                    cls="text-center py-12",
                ),
            )
        else:
            classes_content = Div(*[render_class_card(item) for item in result.value])

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
            members_content = Div(*[render_class_member_row(item) for item in result.value])

        back_link = Div(
            A(
                "← Classes",
                href="/teaching/classes",
                cls="btn btn-ghost btn-sm mt-4",
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
