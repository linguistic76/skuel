"""
Teaching UI Routes — Orchestrator-Driven Teacher Dashboard
============================================================

Teacher-facing pages for the teaching workflow:
- Student list + student hub + student submissions
- Review queue + review detail
- Groups management

/teaching redirects to /teaching/students (hub removed 2026-04-03).

All data access goes through TeacherOrchestrator — the routing layer
only handles HTTP concerns (auth, request parsing, template rendering).

TEACHER role required for all endpoints.

Layout: Student hub uses BasePage, child pages use SidebarPage.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
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
    Span,
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
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import (
    SidebarPage,
    alpine_mobile_section_renderer,
    alpine_section_renderer,
)
from ui.teaching.cards import (
    render_class_card,
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
    from core.orchestrator.teacher_orchestrator import TeacherOrchestrator

logger = get_logger("skuel.routes.teaching.ui")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_teaching_ui_routes(
    _app: Any,
    rt: Any,
    orchestrator: "TeacherOrchestrator",
    user_service: Any,
) -> None:
    """
    Create teaching UI routes for the teacher dashboard.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: TeacherOrchestrator for unified access to services
        user_service: UserService for role checks
    """
    if not orchestrator:
        raise RuntimeError("TeacherOrchestrator is required — check bootstrap wiring")

    get_user_service = make_service_getter(user_service)

    def _to_queue_item(d: dict[str, Any]) -> QueueItem:
        return QueueItem(
            title=d.get("title", ""),
            student_name=d.get("student_name") or d.get("student_uid") or "Unknown",
            student_uid=d.get("student_uid", ""),
            status=d.get("status") or "unknown",
            entity_type=d.get("entity_type"),
            exercise_name=d.get("exercise_name"),
            submission_uid=d.get("submission_uid", ""),
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

    # Status sets for bucketing submissions
    _needs_review = {"submitted", "active", "queued", "processing"}
    _revision_statuses = {"revision_requested"}
    _completed_statuses = {"completed", "failed"}

    async def _get_bucketed_submissions(
        user_uid: str, student_uid: str
    ) -> tuple[list[SubmissionRow], list[SubmissionRow], list[SubmissionRow], str]:
        """Fetch and bucket student submissions into (pending, revision, completed, student_name)."""
        result = await orchestrator.get_student_submissions(
            teacher_uid=user_uid, student_uid=student_uid
        )
        pending: list[SubmissionRow] = []
        revision: list[SubmissionRow] = []
        completed: list[SubmissionRow] = []
        student_name = student_uid

        if not result.is_error and result.value:
            for item in result.value:
                raw_name = item.get("student_name")
                if raw_name and student_name == student_uid:
                    student_name = str(raw_name)
                row = _to_submission_row(item)
                status_str = (row.status or "").lower()
                if status_str in _needs_review:
                    pending.append(row)
                elif status_str in _revision_statuses:
                    revision.append(row)
                elif status_str in _completed_statuses:
                    completed.append(row)
                else:
                    pending.append(row)

        return pending, revision, completed, student_name

    # ------------------------------------------------------------------
    # TEACHING ROOT — redirect to students list
    # ------------------------------------------------------------------

    @rt("/teaching")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_root_redirect(request: Request, current_user: Any = None) -> Any:
        """Redirect /teaching → /teaching/students (hub removed)."""
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/teaching/students", status_code=301)

    # ------------------------------------------------------------------
    # REVIEW QUEUE
    # ------------------------------------------------------------------

    @rt("/teaching/queue")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_queue_page(request: Request, current_user: Any = None) -> Any:
        """Review queue — pending student submissions."""
        user_uid = require_authenticated_user(request)

        result = await orchestrator.get_review_queue(teacher_uid=user_uid)

        if result.is_error:
            queue_content: Any = render_error_banner(
                "Failed to load review queue", str(result.error)
            )
        elif not result.value:
            queue_content = EmptyState(
                "No submissions to review",
                description="When students submit work against your assignments, it will appear here.",
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
        detail_result = await orchestrator.get_submission_detail(
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
        history_result = await orchestrator.get_report_history(uid)
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

        result = await orchestrator.get_students_summary(teacher_uid=user_uid)

        if result.is_error:
            students_content: Any = render_error_banner(
                "Failed to load students", str(result.error)
            )
        elif not result.value:
            students_content = EmptyState(
                "No students yet",
                description="Students who share work with you will appear here.",
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
        """Student hub — HTMX-loaded preview blocks for submissions + KU progress."""
        user_uid = require_authenticated_user(request)

        # Resolve student display name from submissions
        result = await orchestrator.get_student_submissions(
            teacher_uid=user_uid, student_uid=uid
        )
        student_name = uid
        if not result.is_error and result.value:
            for item in result.value:
                raw_name = item.get("student_name")
                if raw_name:
                    student_name = str(raw_name)
                    break

        display_name = _display_student_name(student_name)

        return await BasePage(
            content=StudentHub(student_name=display_name, student_uid=uid),
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

        pending, revision_requested, completed, student_name = await _get_bucketed_submissions(
            user_uid, uid
        )

        ku_detail = await orchestrator.get_student_ku_detail(uid)
        section_content: Any = render_student_detail_sections(
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

    @rt("/teaching/groups")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_groups_page(request: Request, current_user: Any = None) -> Any:
        """Groups page — teacher's groups with student and exercise counts."""
        user_uid = require_authenticated_user(request)

        result = await orchestrator.get_teacher_groups_with_stats(teacher_uid=user_uid)

        if result.is_error:
            groups_content: Any = render_error_banner("Failed to load groups", str(result.error))
        elif not result.value:
            groups_content = EmptyState(
                "No groups yet",
                description="Create your first group from the Groups section to get started.",
                action_text="Go to Groups →",
                action_href="/groups",
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

        group_name = request.query_params.get("name") or uid
        result = await orchestrator.get_group_detail(group_uid=uid, teacher_uid=user_uid)

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
            PageHeader(group_name, subtitle="Members and their submission progress"),
            members_content,
            back_link,
        )
        return await render_teaching_sidebar_page(
            content=content,
            active="groups",
            request=request,
        )

    # ------------------------------------------------------------------
    # STUDENT HUB PREVIEW ENDPOINTS (HTMX lazy-loaded)
    # ------------------------------------------------------------------

    def _submission_preview_badge(status: str) -> Span:
        """Status badge for submission preview cards."""
        label = status.replace("_", " ").title() if status else "Unknown"
        return Span(label, cls="text-[10px] font-medium text-muted-foreground")

    @rt("/api/teaching/students/{uid}/pending/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_pending_preview(request: Request, uid: str, current_user: Any = None) -> Any:
        """HTMX fragment: top 3 pending submissions for student hub preview."""
        user_uid = require_authenticated_user(request)
        pending, _, _, _ = await _get_bucketed_submissions(user_uid, uid)
        if not pending:
            return HubPreviewEmpty("submissions needing review")
        cards = [
            HubPreviewCard(
                title=row.title or "Untitled",
                href=f"/teaching/students/{uid}/submissions?tab=pending",
                badge=_submission_preview_badge(row.status),
            )
            for row in pending[:3]
        ]
        return HubPreviewGrid(cards)

    @rt("/api/teaching/students/{uid}/revision/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_revision_preview(request: Request, uid: str, current_user: Any = None) -> Any:
        """HTMX fragment: top 3 revision-requested submissions for student hub preview."""
        user_uid = require_authenticated_user(request)
        _, revision, _, _ = await _get_bucketed_submissions(user_uid, uid)
        if not revision:
            return HubPreviewEmpty("revision requests")
        cards = [
            HubPreviewCard(
                title=row.title or "Untitled",
                href=f"/teaching/students/{uid}/submissions?tab=revision",
                badge=_submission_preview_badge(row.status),
            )
            for row in revision[:3]
        ]
        return HubPreviewGrid(cards)

    @rt("/api/teaching/students/{uid}/completed/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_completed_preview(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """HTMX fragment: top 3 completed submissions for student hub preview."""
        user_uid = require_authenticated_user(request)
        _, _, completed, _ = await _get_bucketed_submissions(user_uid, uid)
        if not completed:
            return HubPreviewEmpty("completed submissions")
        cards = [
            HubPreviewCard(
                title=row.title or "Untitled",
                href=f"/teaching/students/{uid}/submissions?tab=completed",
                badge=_submission_preview_badge(row.status),
            )
            for row in completed[:3]
        ]
        return HubPreviewGrid(cards)

    @rt("/api/teaching/students/{uid}/ku/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_ku_preview(request: Request, uid: str, current_user: Any = None) -> Any:
        """HTMX fragment: top 3 KU progress items for student hub preview."""
        require_authenticated_user(request)
        ku_detail = await orchestrator.get_student_ku_detail(uid)
        if not ku_detail:
            return HubPreviewEmpty("KU progress")

        # Collect KU items across learning states, prioritized
        state_order = [
            ("mastered", "Mastered"),
            ("in_progress", "In Progress"),
            ("bookmarked", "Bookmarked"),
            ("viewed", "Viewed"),
        ]
        items: list[tuple[str, str]] = []
        for key, label in state_order:
            for ku in ku_detail.get(key, []):
                title = ku.get("title") or ku.get("uid", "Unknown KU")
                items.append((title, label))
                if len(items) >= 3:
                    break
            if len(items) >= 3:
                break

        if not items:
            return HubPreviewEmpty("KU progress")

        cards = [
            HubPreviewCard(
                title=title,
                href=f"/teaching/students/{uid}/submissions?tab=ku",
                badge=Span(label, cls="text-[10px] font-medium text-muted-foreground"),
            )
            for title, label in items
        ]
        return HubPreviewGrid(cards)

    logger.info("Teaching UI routes registered")


def _display_student_name(name: str) -> str:
    """Strip the 'user_' prefix from student names for display."""
    if name.startswith("user_"):
        return name[5:]
    return name


# _fetch_ku_detail removed — absorbed into TeacherOrchestrator.get_student_ku_detail()
