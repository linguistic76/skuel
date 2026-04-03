"""
Teaching UI Routes — Teacher Dashboard
========================================

Teacher-facing pages for the teaching workflow:
- Teaching hub (root page)
- Student list + student hub + student submissions
- Review queue + review detail
- Groups management

TEACHER role required for all endpoints.

Layout: Hub pages use BasePage (no sidebar), child pages use SidebarPage.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Div,
    Form,
    Input,
    Label,
    P,
)
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Textarea
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import (
    SidebarPage,
    alpine_mobile_section_renderer,
    alpine_section_renderer,
)
from ui.teaching.cards import (
    render_class_card,
    render_empty_state,
    render_queue_item,
    render_student_name_row,
)
from ui.teaching.detail import (
    render_class_member_row,
    render_report_item,
    render_student_detail_sections,
    render_submission_content,
    student_detail_sidebar_items,
)
from ui.teaching.hub import TeachingHub
from ui.teaching.nav import render_teaching_sidebar_page
from ui.teaching.student_hub import StudentHub
from ui.teaching.types import (
    ClassMember,
    ClassSummary,
    QueueItem,
    SubmissionDetail,
    SubmissionRow,
)

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger("skuel.routes.teaching.ui")


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
    Create teaching UI routes for the teacher dashboard.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
        exercises_service: ExerciseService (retained for route config compatibility)
        admin_stats: AdminStatsService for KU progression data
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
    # TEACHING HUB — root page
    # ------------------------------------------------------------------

    @rt("/teaching")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_hub_page(request: Request, current_user: Any = None) -> Any:
        """Teaching hub — entry point with container cards for Students, Groups, Queue."""
        return await BasePage(
            content=TeachingHub(),
            title="Teaching",
            request=request,
            active_page="teaching",
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
        return await render_teaching_sidebar_page(
            content=content,
            active="queue",
            request=request,
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
            submission_section,
            feedback_history_section,
            # Submit feedback — file upload
            Card(
                CardBody(
                    P(
                        "Upload your feedback as a Markdown file (.md).",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Form(
                        Div(
                            Label(
                                "Feedback file",
                                fr="feedback_file",
                                cls="text-sm font-medium mb-1 block",
                            ),
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
                    P(
                        "Request the student revise their work.",
                        cls="text-sm text-muted-foreground mb-3",
                    ),
                    Form(
                        Div(
                            Label(
                                "Revision notes",
                                fr="revision_notes",
                                cls="text-sm font-medium mb-1 block",
                            ),
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
        return await render_teaching_sidebar_page(
            content=content,
            active="queue",
            request=request,
        )

    # ------------------------------------------------------------------
    # STUDENTS LIST — simple clickable name rows
    # ------------------------------------------------------------------

    @rt("/teaching/students")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_students_page(request: Request, current_user: Any = None) -> Any:
        """Students page — clean list of clickable student names."""
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
                    render_student_name_row(
                        student_name=_display_student_name(
                            item.get("student_name") or item.get("student_uid") or "Unknown"
                        ),
                        student_uid=item.get("student_uid", ""),
                    )
                    for item in result.value
                ]
            )

        content = Div(
            PageHeader("Students", subtitle="Students who have submitted work"),
            students_content,
        )
        return await render_teaching_sidebar_page(
            content=content,
            active="students",
            request=request,
        )

    # ------------------------------------------------------------------
    # STUDENT HUB — teacher's view of individual student
    # ------------------------------------------------------------------

    @rt("/teaching/students/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_student_hub_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Student hub — overview page with container cards for submission sections + KU progress."""
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_student_submissions(
            teacher_uid=user_uid, student_uid=uid
        )

        student_name = uid
        pending_count = 0
        revision_count = 0
        completed_count = 0

        if not result.is_error and result.value:
            _needs_review = {"submitted", "active", "queued", "processing"}
            _revision = {"revision_requested"}
            _completed = {"completed", "failed"}

            for item in result.value:
                raw_name = item.get("student_name")
                if raw_name and student_name == uid:
                    student_name = str(raw_name)

                status_str = (item.get("status") or "").lower()
                if status_str in _needs_review:
                    pending_count += 1
                elif status_str in _revision:
                    revision_count += 1
                elif status_str in _completed:
                    completed_count += 1
                else:
                    pending_count += 1  # unknown status → treat as pending

        display_name = _display_student_name(student_name)

        return await BasePage(
            content=StudentHub(
                student_name=display_name,
                student_uid=uid,
                pending_count=pending_count,
                revision_count=revision_count,
                completed_count=completed_count,
            ),
            title=display_name,
            request=request,
            active_page="teaching",
        )

    # ------------------------------------------------------------------
    # STUDENT SUBMISSIONS — Alpine section switching (moved from student detail)
    # ------------------------------------------------------------------

    @rt("/teaching/students/{uid}/submissions")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_student_submissions_page(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """Student submissions — sidebar-driven sections for submissions + KU progress.

        Sections: Needs Review | Revision Requested | Completed | KU Progress
        Uses a student-specific sidebar with Alpine-controlled instant section switching.
        Supports ?tab=pending|revision|completed|ku query param.
        """
        user_uid = require_authenticated_user(request)

        result = await teacher_review_service.get_student_submissions(
            teacher_uid=user_uid, student_uid=uid
        )

        pending: list[Any] = []
        revision_requested: list[Any] = []
        completed: list[Any] = []
        student_name = uid

        if result.is_error:
            section_content: Any = render_error_banner(
                "Failed to load submissions", str(result.error)
            )
        else:
            if result.value:
                for item in result.value:
                    raw_name = item.get("student_name")
                    if raw_name:
                        student_name = str(raw_name)
                        break

                _needs_review = {"submitted", "active", "queued", "processing"}
                _revision = {"revision_requested"}
                _completed = {"completed", "failed"}

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
                        pending.append(row)

            ku_detail = await _fetch_ku_detail(admin_stats, uid)
            section_content = render_student_detail_sections(
                pending=pending,
                revision_requested=revision_requested,
                completed=completed,
                student_name=student_name,
                ku_detail=ku_detail,
            )

        # Determine default section from query param or submission state
        tab_param = request.query_params.get("tab")
        if tab_param in ("pending", "revision", "completed", "ku"):
            default_section = tab_param
        elif pending:
            default_section = "pending"
        elif revision_requested:
            default_section = "revision"
        else:
            default_section = "completed"

        display_name = _display_student_name(student_name)

        sidebar_items = student_detail_sidebar_items(
            pending_count=len(pending),
            revision_count=len(revision_requested),
            completed_count=len(completed),
        )

        # Back arrow linking to student hub
        back_arrow = A(
            UkIcon("arrow-left", height=18, width=18),
            href=f"/teaching/students/{uid}",
            cls="p-1.5 rounded hover:bg-accent transition-colors inline-flex items-center",
            aria_label="Back to student overview",
        )

        # Mobile back link (above tabs)
        mobile_back = Div(
            A(
                UkIcon("arrow-left", height=14, width=14, cls="inline mr-1"),
                display_name,
                href=f"/teaching/students/{uid}",
                cls="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1",
            ),
            cls="mb-2",
        )

        return await SidebarPage(
            content=Div(section_content),
            items=sidebar_items,
            active=default_section,
            page_title=display_name,
            request=request,
            title=display_name,
            subtitle="Student submissions",
            storage_key="student-detail-sidebar",
            active_page="teaching",
            item_renderer=alpine_section_renderer("section"),
            mobile_item_renderer=alpine_mobile_section_renderer("section"),
            alpine_state=f"{{ section: '{default_section}' }}",
            title_prefix=back_arrow,
            extra_mobile_sections=[mobile_back],
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
        return await render_teaching_sidebar_page(
            content=content,
            active="groups",
            request=request,
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
        return await render_teaching_sidebar_page(
            content=content,
            active="groups",
            request=request,
        )

    # ------------------------------------------------------------------
    # TRANSITION REDIRECTS — added 2026-04-03
    # ------------------------------------------------------------------

    @rt("/teaching/approved")
    async def teaching_approved_redirect(request: Request) -> Any:
        """301 redirect: /teaching/approved → /teaching/queue."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

    @rt("/teaching/exercises")
    async def teaching_exercises_redirect(request: Request) -> Any:
        """301 redirect: /teaching/exercises → /teaching/queue."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

    @rt("/teaching/exercises/new")
    async def teaching_exercises_new_redirect(request: Request) -> Any:
        """301 redirect: /teaching/exercises/new → /teaching/queue."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

    @rt("/teaching/exercises/{uid}/edit")
    async def teaching_exercises_edit_redirect(request: Request, uid: str) -> Any:
        """301 redirect: /teaching/exercises/{uid}/edit → /teaching/queue."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

    @rt("/teaching/exercises/{uid}/submissions")
    async def teaching_exercises_submissions_redirect(request: Request, uid: str) -> Any:
        """301 redirect: /teaching/exercises/{uid}/submissions → /teaching/queue."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/queue", status_code=301)

    @rt("/teaching/learning")
    async def teaching_learning_redirect(request: Request) -> Any:
        """301 redirect: /teaching/learning → /teaching/students."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/students", status_code=301)

    @rt("/teaching/learning/user/{uid}")
    async def teaching_learning_user_redirect(request: Request, uid: str) -> Any:
        """301 redirect: /teaching/learning/user/{uid} → /teaching/students/{uid}/submissions?tab=ku."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(
            url=f"/teaching/students/{uid}/submissions?tab=ku", status_code=301
        )

    @rt("/teaching/reports/user/{uid}")
    async def teaching_reports_redirect(request: Request, uid: str) -> Any:
        """301 redirect: /teaching/reports/user/{uid} → /teaching/students/{uid}."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url=f"/teaching/students/{uid}", status_code=301)

    @rt("/admin/learning")
    async def admin_learning_redirect(request: Request) -> Any:
        """301 redirect: /admin/learning → /teaching/students."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/students", status_code=301)

    @rt("/admin/learning/user/{uid}")
    async def admin_learning_user_redirect(request: Request, uid: str) -> Any:
        """301 redirect: /admin/learning/user/{uid} → /teaching/students/{uid}/submissions?tab=ku."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(
            url=f"/teaching/students/{uid}/submissions?tab=ku", status_code=301
        )

    logger.info("Teaching UI routes registered")
    return []


def _display_student_name(name: str) -> str:
    """Strip the 'user_' prefix from student names for display."""
    if name.startswith("user_"):
        return name[5:]
    return name


async def _fetch_ku_detail(admin_stats: Any, student_uid: str) -> dict[str, Any] | None:
    """Fetch KU detail for a student, returning None if unavailable."""
    if not admin_stats:
        return None
    result = await admin_stats.get_user_ku_detail(student_uid)
    if result.is_error:
        logger.warning(f"Failed to load KU detail for {student_uid}: {result.error}")
        return None
    return result.value or None
