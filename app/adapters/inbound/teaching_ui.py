"""
Teaching UI Routes — Teacher Dashboard
========================================

Teacher-facing pages for the full teaching workflow:
- Overview dashboard with at-a-glance stats
- Review queue and approved submissions
- By-exercise and by-student views
- Groups management
- Learning dashboard (KU progression tracking)
- Submission review with content display

TEACHER role required for all endpoints.

Layout: Unified sidebar (Tailwind + Alpine) with teaching navigation.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H2,
    H3,
    Div,
    Form,
    Input,
    Label,
    P,
)

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.admin.views import AdminLearningComponents
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Textarea
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
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
    render_student_detail_tabs,
    render_student_submission_row,
    render_submission_content,
)
from ui.teaching.forms import render_exercise_form
from ui.teaching.types import (
    ClassMember,
    ClassSummary,
    ExerciseSummary,
    QueueItem,
    StudentSummary,
    SubmissionDetail,
    SubmissionRow,
    TeachingDashboardStats,
)

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger("skuel.routes.teaching.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

TEACHING_SIDEBAR_ITEMS = [
    SidebarItem("Overview", "/teaching", "overview", icon="📊"),
    SidebarItem("Review Queue", "/teaching/queue", "queue", icon="📥"),
    SidebarItem("By Student", "/teaching/students", "students", icon="👥"),
    SidebarItem("Groups", "/teaching/groups", "groups", icon="👥"),
    SidebarItem("Learning", "/teaching/learning", "learning", icon="📚"),
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
    exercises_service: Any,
    admin_stats: Any = None,
) -> list[Any]:
    """
    Create teaching UI routes for the full teacher dashboard.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
        exercises_service: ExerciseService for create/edit forms
        admin_stats: AdminStatsService for KU progression data (learning dashboard)
    """

    get_user_service = make_service_getter(user_service)

    def _to_queue_item(d: dict[str, Any]) -> QueueItem:
        return QueueItem(
            title=d.get("title", ""),
            student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
            student_uid=d.get("student_uid", ""),
            status=d.get("status") or "unknown",
            entity_type=d.get("entity_type"),
            exercise_name=d.get("exercise_name"),
            ku_uid=d.get("ku_uid", ""),
            feedback_count=d.get("feedback_count", 0),
            original_filename=d.get("original_filename"),
        )

    def _to_submission_row(d: dict[str, Any]) -> SubmissionRow:
        return SubmissionRow(
            uid=d.get("uid", ""),
            title=d.get("title", ""),
            student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
            student_uid=d.get("student_uid", ""),
            status=d.get("status") or "unknown",
            feedback_count=d.get("feedback_count", 0),
            exercise_title=d.get("exercise_title"),
            original_filename=d.get("original_filename"),
        )

    # ------------------------------------------------------------------
    # OVERVIEW / DASHBOARD
    # ------------------------------------------------------------------

    @rt("/teaching")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_overview_page(request: Request, current_user: Any = None) -> Any:
        """Dashboard overview — at-a-glance stats for the teacher."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_dashboard_stats(teacher_uid=user_uid)
        stats_error = result.is_error
        if stats_error:
            logger.error(f"Failed to load dashboard stats: {result.error}")
        raw_stats = result.value if not stats_error else {}
        stats = TeachingDashboardStats(
            pending_count=raw_stats.get("pending_count", 0),
            total_students=raw_stats.get("total_students", 0),
            total_exercises=raw_stats.get("total_exercises", 0),
            total_groups=raw_stats.get("total_groups", 0),
        )

        content = Div(
            PageHeader("Teaching Overview", subtitle="Your teaching activity at a glance"),
            render_error_banner("Dashboard statistics may be incomplete", severity="warning")
            if stats_error
            else None,
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
            queue_content: Any = render_error_banner(
                "Failed to load review queue", str(result.error)
            )
        elif not result.value:
            queue_content = render_empty_state(
                "No submissions to review",
                "When students submit work against your assignments, it will appear here.",
            )
        else:
            queue_content = Div(*[render_queue_item(_to_queue_item(item)) for item in result.value])

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
    # APPROVED — redirects to review queue (completed view is per-student now)
    # ------------------------------------------------------------------

    @rt("/teaching/approved")
    async def teaching_approved_redirect(request: Request) -> Any:
        """301 redirect: /teaching/approved → /teaching/queue.

        Completed submissions are now visible per-student in the Completed tab
        at /teaching/students/{uid}. This route is kept for backward compatibility.
        """
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

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
        if not detail_result.is_error and detail_result.value:
            d = detail_result.value
            detail = SubmissionDetail(
                title=d.get("title", "Untitled"),
                entity_type=d.get("entity_type"),
                status=d.get("status") or "",
                student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
                student_uid=d.get("student_uid", ""),
                exercise_title=d.get("exercise_title"),
                exercise_instructions=d.get("exercise_instructions"),
                processed_content=d.get("processed_content"),
                content=d.get("content"),
                original_filename=d.get("original_filename"),
            )
            submission_section = render_submission_content(detail)
        else:
            submission_section = Div(
                P("Submission content unavailable.", cls="text-sm text-muted-foreground italic"),
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
            # Submit feedback — file upload
            Card(
                CardBody(
                    P("Upload your feedback as a Markdown file (.md).", cls="text-sm text-muted-foreground mb-3"),
                    Form(
                        Div(
                            Label("Feedback file", fr="feedback_file", cls="text-sm font-medium mb-1 block"),
                            Input(
                                type="file",
                                name="feedback_file",
                                id="feedback_file",
                                accept=".md",
                                required=True,
                                cls="block w-full text-sm file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer",
                            ),
                            cls="mb-4",
                        ),
                        Button(
                            "Submit Feedback",
                            variant=ButtonT.primary,
                            type="submit",
                        ),
                        enctype="multipart/form-data",
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/report",
                            "hx-target": "#review-result",
                            "hx-swap": "innerHTML",
                            "hx-encoding": "multipart/form-data",
                        },
                    ),
                    Div(id="review-result", cls="mt-4"),
                ),
                cls="bg-background shadow-sm mb-3",
            ),
            # Request revision — text notes
            Card(
                CardBody(
                    P("Request the student revise their work.", cls="text-sm text-muted-foreground mb-3"),
                    Form(
                        Div(
                            Label("Revision notes", fr="revision_notes", cls="text-sm font-medium mb-1 block"),
                            Textarea(
                                name="notes",
                                id="revision_notes",
                                placeholder="Describe what needs to be revised...",
                                cls="h-24",
                                required=True,
                            ),
                            cls="mb-4",
                        ),
                        Div(
                            Button(
                                "Request Revision",
                                variant=ButtonT.warning,
                                type="submit",
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
                        **{
                            "hx-post": f"/api/teaching/review/{uid}/revision",
                            "hx-target": "#review-result",
                            "hx-swap": "innerHTML",
                        },
                    ),
                ),
                cls="bg-background shadow-sm",
            ),
            Div(
                ButtonLink(
                    "Back to Queue",
                    href="/teaching/queue",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    cls="mt-4",
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
            page_content: Any = render_error_banner("Failed to load exercises", str(result.error))
        elif not result.value:
            page_content = render_empty_state(
                "No exercises yet",
                "Exercises you create will appear here with submission counts.",
            )
        else:
            page_content = Div(
                *[
                    render_exercise_summary_card(
                        ExerciseSummary(
                            uid=item.get("uid", ""),
                            title=item.get("title") or "Untitled Exercise",
                            scope=item.get("scope"),
                            total_count=item.get("total_count", 0),
                            reviewed_count=item.get("reviewed_count", 0),
                            pending_count=item.get("pending_count", 0),
                        )
                    )
                    for item in result.value
                ]
            )

        content = Div(
            PageHeader("By Exercise", subtitle="Submissions grouped by exercise"),
            Div(
                ButtonLink(
                    "+ New Exercise",
                    href="/teaching/exercises/new",
                    variant=ButtonT.primary,
                    size=Size.sm,
                    cls="mb-4",
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
        groups = groups_result.value if not groups_result.is_error else []

        content = Div(
            PageHeader("New Exercise", subtitle="Create an exercise for your students"),
            render_exercise_form(groups),
            ButtonLink(
                "← Back to Exercises",
                href="/teaching/exercises",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-4",
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

        exercise_result = await exercises_service.get_exercise(uid)
        exercise: Any = exercise_result.value if not exercise_result.is_error else None

        groups_result = await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=user_uid
        )
        groups = groups_result.value if not groups_result.is_error else []

        title = getattr(exercise, "title", uid) if exercise else uid
        content = Div(
            PageHeader(f"Edit: {title}", subtitle="Update exercise details"),
            render_exercise_form(groups, exercise=exercise),
            ButtonLink(
                "← Back to Exercises",
                href="/teaching/exercises",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-4",
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
            rows: Any = render_error_banner("Failed to load submissions", str(result.error))
        elif not result.value:
            rows = Div(
                P(
                    "No submissions yet for this exercise.",
                    cls="text-center text-muted-foreground py-8",
                )
            )
        else:
            rows = Div(
                *[render_exercise_submission_row(_to_submission_row(item)) for item in result.value]
            )

        back_link = Div(
            ButtonLink(
                "← By Exercise",
                href="/teaching/exercises",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-4",
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
            students_content: Any = render_error_banner(
                "Failed to load students", str(result.error)
            )
        elif not result.value:
            students_content = render_empty_state(
                "No students yet",
                "Students who share work with you will appear here.",
            )
        else:
            students_content = Div(
                *[
                    render_student_summary_card(
                        StudentSummary(
                            student_uid=item.get("student_uid", ""),
                            student_name=item.get("student_name")
                            or item.get("student_uid")
                            or "Unknown",
                            submission_count=item.get("submission_count", 0),
                            reviewed_count=item.get("reviewed_count", 0),
                            pending_count=item.get("pending_count", 0),
                        )
                    )
                    for item in result.value
                ]
            )

        content = Div(
            PageHeader("By Student", subtitle="Students who have submitted work"),
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
        """Student detail page — tabbed view of all submissions grouped by workflow status.

        Tabs: Needs Review | Revision Requested | Completed
        Pending submissions include inline HTMX-loadable review panels with action forms.
        """
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_student_submissions(
            teacher_uid=user_uid, student_uid=uid
        )

        if result.is_error:
            tabbed_content: Any = render_error_banner(
                "Failed to load submissions", str(result.error)
            )
            student_name = uid
        elif not result.value:
            tabbed_content = Div(
                P(
                    "No submissions from this student.",
                    cls="text-center text-muted-foreground py-8",
                )
            )
            student_name = uid
        else:
            # Derive display name from first submission that has one
            student_name = next(
                (
                    item.get("student_name") or item.get("student_uid") or uid
                    for item in result.value
                    if item.get("student_name")
                ),
                uid,
            )

            _needs_review = {"submitted", "active", "queued", "processing"}
            _revision = {"revision_requested"}
            _completed = {"completed", "failed"}

            pending: list[Any] = []
            revision_requested: list[Any] = []
            completed: list[Any] = []

            for item in result.value:
                row = _to_submission_row(item)
                status_str = (row.status or "").lower()
                if status_str in _needs_review:
                    pending.append(row)
                elif status_str in _revision:
                    revision_requested.append(row)
                elif status_str in _completed:
                    completed.append(row)
                else:
                    pending.append(row)  # unknown status → treat as pending

            tabbed_content = render_student_detail_tabs(
                pending=pending,
                revision_requested=revision_requested,
                completed=completed,
                student_name=student_name,
            )

        content = Div(
            PageHeader(
                f"Student: {student_name}",
                subtitle="Submissions grouped by review status",
            ),
            tabbed_content,
            Div(
                ButtonLink(
                    "← By Student",
                    href="/teaching/students",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    cls="mt-4",
                ),
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="students",
            page_title=f"Student: {student_name}",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # GROUPS
    # ------------------------------------------------------------------

    @rt("/teaching/classes")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_classes_redirect(request: Request, current_user: Any = None) -> Any:
        """301 redirect: /teaching/classes → /teaching/groups."""
        from fasthtml.common import RedirectResponse

        return RedirectResponse("/teaching/groups", status_code=301)

    @rt("/teaching/classes/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_class_detail_redirect(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """301 redirect: /teaching/classes/{uid} → /teaching/groups/{uid}."""
        from fasthtml.common import RedirectResponse

        return RedirectResponse(f"/teaching/groups/{uid}", status_code=301)

    @rt("/teaching/groups")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_groups_page(request: Request, current_user: Any = None) -> Any:
        """Groups page — teacher's groups with student and exercise counts."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_teacher_groups_with_stats(teacher_uid=user_uid)

        if result.is_error:
            groups_content: Any = render_error_banner("Failed to load groups", str(result.error))
        elif not result.value:
            groups_content = Div(
                Div(
                    H3("No groups yet", cls="text-lg font-medium mb-2"),
                    P(
                        "Create your first group from the Groups section to get started.",
                        cls="text-muted-foreground",
                    ),
                    ButtonLink(
                        "Go to Groups →",
                        href="/groups",
                        variant=ButtonT.primary,
                        size=Size.sm,
                        cls="mt-4",
                    ),
                    cls="text-center py-12",
                ),
            )
        else:
            groups_content = Div(
                *[
                    render_class_card(
                        ClassSummary(
                            uid=item.get("uid", ""),
                            name=item.get("name") or "Unnamed Group",
                            description=item.get("description"),
                            member_count=item.get("member_count", 0),
                            exercise_count=item.get("exercise_count", 0),
                            pending_count=item.get("pending_count", 0),
                            is_active=item.get("is_active", True),
                        )
                    )
                    for item in result.value
                ]
            )

        content = Div(
            PageHeader("Groups", subtitle="Your groups and their activity"),
            groups_content,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="groups",
            page_title="Groups",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/groups/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_group_detail_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Group detail page — members with submission progress stats."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_group_detail(group_uid=uid, teacher_uid=user_uid)

        if result.is_error:
            members_content: Any = render_error_banner(
                "Failed to load group members", str(result.error)
            )
        elif not result.value:
            members_content = EmptyState(title="No members in this group yet")
        else:
            members_content = Div(
                *[
                    render_class_member_row(
                        ClassMember(
                            user_uid=item.get("user_uid", ""),
                            user_name=item.get("user_name") or item.get("user_uid") or "Unknown",
                            role=item.get("role") or "student",
                            submission_count=item.get("submission_count", 0),
                            reviewed_count=item.get("reviewed_count", 0),
                            pending_count=item.get("pending_count", 0),
                        )
                    )
                    for item in result.value
                ]
            )

        back_link = Div(
            ButtonLink(
                "← Groups",
                href="/teaching/groups",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-4",
            ),
        )

        content = Div(
            PageHeader(f"Group: {uid}", subtitle="Members and their submission progress"),
            members_content,
            back_link,
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="groups",
            page_title="Group Detail",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    # ------------------------------------------------------------------
    # LEARNING DASHBOARD
    # ------------------------------------------------------------------

    @rt("/admin/learning")
    @require_role(UserRole.TEACHER, get_user_service)
    async def admin_learning_redirect(request: Request, current_user: Any = None) -> Any:
        """301 redirect: /admin/learning → /teaching/learning."""
        from fasthtml.common import RedirectResponse

        return RedirectResponse("/teaching/learning", status_code=301)

    @rt("/admin/learning/user/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def admin_learning_user_redirect(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """301 redirect: /admin/learning/user/{uid} → /teaching/learning/user/{uid}."""
        from fasthtml.common import RedirectResponse

        return RedirectResponse(f"/teaching/learning/user/{uid}", status_code=301)

    @rt("/teaching/learning")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_learning_page(request: Request, current_user: Any = None) -> Any:
        """Learning dashboard — KU progression tracking across all users."""
        if not admin_stats:
            content = Div(
                PageHeader("Learning Dashboard"),
                render_error_banner("Learning stats service unavailable", severity="warning"),
            )
            return await SidebarPage(
                content=content,
                items=TEACHING_SIDEBAR_ITEMS,
                active="learning",
                page_title="Learning Dashboard",
                request=request,
                **_SIDEBAR_DEFAULTS,
            )

        ku_metrics_result = await admin_stats.get_entity_system_metrics()
        ku_metrics_error = ku_metrics_result.is_error
        if ku_metrics_error:
            logger.error(f"Failed to load KU metrics: {ku_metrics_result.error}")
        ku_metrics = ku_metrics_result.value if not ku_metrics_error else {}

        user_progress_result = await admin_stats.get_all_users_progress()
        user_progress_error = user_progress_result.is_error
        if user_progress_error:
            logger.error(f"Failed to load user progress: {user_progress_result.error}")
        user_progress = user_progress_result.value if not user_progress_error else []

        content = Div(
            PageHeader(
                "Learning Dashboard", subtitle="Track knowledge unit progression across all users"
            ),
            Card(
                H2("Knowledge Unit Overview", cls="text-xl font-semibold mb-4"),
                render_error_banner("Knowledge unit metrics unavailable", severity="warning")
                if ku_metrics_error
                else AdminLearningComponents.render_ku_system_metrics(ku_metrics),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            Card(
                H2("User KU Progress", cls="text-xl font-semibold mb-4"),
                render_error_banner("User progress data unavailable", severity="warning")
                if user_progress_error
                else AdminLearningComponents.render_user_progress_table(user_progress),
                cls="bg-background shadow-sm p-6",
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="learning",
            page_title="Learning Dashboard",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/learning/user/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_learning_user_detail(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Per-user KU detail — viewed, in-progress, and mastered KUs with timestamps."""
        if not admin_stats:
            content = Div(
                render_error_banner("Learning stats service unavailable", severity="warning"),
                ButtonLink(
                    "← Learning Dashboard",
                    href="/teaching/learning",
                    variant=ButtonT.ghost,
                    cls="mt-4",
                ),
            )
            return await SidebarPage(
                content=content,
                items=TEACHING_SIDEBAR_ITEMS,
                active="learning",
                page_title="User KU Detail",
                request=request,
                **_SIDEBAR_DEFAULTS,
            )

        user_result = await user_service.get_user(uid)
        if user_result.is_error or not user_result.value:
            content = Div(
                render_error_banner(f"No user found with UID: {uid}"),
                ButtonLink(
                    "← Learning Dashboard",
                    href="/teaching/learning",
                    variant=ButtonT.ghost,
                    cls="mt-4",
                ),
            )
            return await SidebarPage(
                content=content,
                items=TEACHING_SIDEBAR_ITEMS,
                active="learning",
                page_title="User Not Found",
                request=request,
                **_SIDEBAR_DEFAULTS,
            )

        user = user_result.value

        user_ku_detail_result = await admin_stats.get_user_ku_detail(uid)
        if user_ku_detail_result.is_error:
            logger.warning(f"Failed to load KU detail for {uid}: {user_ku_detail_result.error}")
        user_ku_detail = user_ku_detail_result.value if not user_ku_detail_result.is_error else {}

        submissions_result = await admin_stats.get_user_submissions_detail(uid)
        if submissions_result.is_error:
            logger.warning(f"Failed to load submissions for {uid}: {submissions_result.error}")
        submissions = submissions_result.value if not submissions_result.is_error else []

        content = Div(
            ButtonLink(
                "← Learning Dashboard",
                href="/teaching/learning",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mb-4",
            ),
            PageHeader(f"{user.display_name or user.title} — KU Progress"),
            Card(
                H2("Progress Summary", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_summary(user_ku_detail),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            Card(
                H2("Exercise Submissions", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_submissions_list(submissions),
                cls="bg-background shadow-sm p-6 mb-6",
            ),
            Card(
                H2("Knowledge Units", cls="text-xl font-semibold mb-4"),
                AdminLearningComponents.render_user_ku_detail_list(user_ku_detail),
                cls="bg-background shadow-sm p-6",
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="learning",
            page_title=f"Learning: {user.display_name or user.title}",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    @rt("/teaching/reports/user/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_user_reports_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """User reports placeholder page."""
        user_result = await user_service.get_user(uid)
        
        user_name = uid
        if not user_result.is_error and user_result.value:
            user_name = user_result.value.display_name or user_result.value.title or uid

        content = Div(
            PageHeader(f"Reports: {user_name}", subtitle="Exercise and Activity Reports"),
            render_empty_state("Reports coming soon", "This feature is currently under development."),
            ButtonLink(
                "← Back to Students",
                href="/teaching/students",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="mt-4 block text-center",
            ),
        )
        return await SidebarPage(
            content=content,
            items=TEACHING_SIDEBAR_ITEMS,
            active="students",
            page_title=f"Reports: {user_name}",
            request=request,
            **_SIDEBAR_DEFAULTS,
        )

    logger.info("Teaching UI routes registered")
    return []
