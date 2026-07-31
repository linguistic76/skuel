"""
Teaching UI Routes — Orchestrator-Driven Teacher Dashboard
============================================================

Teacher-facing pages for the teaching workflow:
- Student list + student hub + student submissions
- Review queue + review detail
- Groups management

All data access goes through TeacherOrchestrator — the routing layer
only handles HTTP concerns (auth, request parsing, template rendering).

TEACHER role required for all endpoints.

Layout: Student hub uses BasePage, child pages use SidebarPage.

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, A, Div, Form, P

from adapters.inbound.auth import make_service_getter, require_authenticated_user
from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from ui.components import Button, ButtonT, Icon
from ui.forms import LabelInput, LabelTextArea
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.modal import AlpineModal
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import (
    SidebarPage,
    alpine_mobile_section_renderer,
    alpine_section_renderer,
)
from ui.primitives import ButtonLink
from ui.teaching.badges import submission_preview_badge
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
from ui.teaching.forms import render_feedback_submission_form, render_revision_request_form
from ui.teaching.nav import render_teaching_sidebar_page
from ui.teaching.student_hub import StudentHub
from ui.teaching.types import (
    ClassMember,
    ClassSummary,
    SubmissionDetail,
    SubmissionRow,
    queue_item_from_dict,
    submission_row_from_dict,
)

if TYPE_CHECKING:
    from core.orchestrator.teacher_orchestrator import TeacherOrchestrator
    from core.ports.report_protocols import EntryReportOperations

logger = get_logger("skuel.routes.teaching.ui")

# Review-page section tabs. Tab ids are UI naming — "ku" the tab, not the
# entity_type value (route segments and tab ids never carry enum semantics).
_REVIEW_TAB_IDS = ("pending", "revision", "completed", "ku")


def _new_group_modal() -> Any:
    """Modal form that POSTs JSON to /api/groups/create and refreshes on success."""
    hx_vals_js = (
        "js:{"
        'name: document.getElementById("new-group-name").value,'
        'description: document.getElementById("new-group-description").value || null,'
        'max_members: document.getElementById("new-group-max-members").value'
        ' ? parseInt(document.getElementById("new-group-max-members").value, 10) : null'
        "}"
    )
    after_request = (
        "if(event.detail.successful){window.location.href='/teaching/groups'}"
        "else{document.getElementById('new-group-status').textContent="
        "'Failed to create group: ' + (event.detail.xhr.statusText || 'unknown error')}"
    )

    form = Form(
        H3("New Group", cls="text-xl font-bold mb-4"),
        Div(id="new-group-status", cls="text-sm text-destructive mb-2"),
        LabelInput(
            "Name",
            name="name",
            id="new-group-name",
            placeholder="e.g. Physics 101 — Spring 2026",
            required=True,
        ),
        LabelTextArea(
            "Description",
            name="description",
            id="new-group-description",
            placeholder="Optional",
            rows="3",
        ),
        LabelInput(
            "Max Members",
            name="max_members",
            id="new-group-max-members",
            type="number",
            min="1",
            max="500",
            placeholder="Optional",
        ),
        Div(
            Button(
                "Cancel",
                type="button",
                cls=(ButtonT.ghost, "mr-2"),
                **{
                    "x-on:click": "open = false"
                },  # fasthtml dynamic-attr splat: Alpine colon attr has no underscore-kwarg form
            ),
            Button("Create", type="submit", cls=ButtonT.primary),
            cls="flex justify-end mt-4",
        ),
        hx_post="/api/groups/create",
        hx_swap="none",
        hx_vals=hx_vals_js,
        hx_headers='{"Content-Type": "application/json"}',
        **{"hx-on::after-request": after_request},
        cls="space-y-4",
    )

    return AlpineModal(form, show="open", close="open = false", max_width="max-w-lg")


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_teaching_ui_routes(
    _app: Any,
    rt: Any,
    orchestrator: "TeacherOrchestrator",
    user_service: Any,
    entry_report_service: "EntryReportOperations | None" = None,
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

    async def _get_bucketed_submissions(
        user_uid: UserUID, student_uid: str
    ) -> tuple[list[SubmissionRow], list[SubmissionRow], list[SubmissionRow], str]:
        """Fetch bucketed submissions from orchestrator and convert to view models."""
        result = await orchestrator.get_bucketed_student_submissions(
            teacher_uid=user_uid, student_uid=student_uid
        )
        if result.is_error:
            return [], [], [], student_uid

        raw_pending, raw_revision, raw_completed, student_name = result.value
        return (
            [submission_row_from_dict(d) for d in raw_pending],
            [submission_row_from_dict(d) for d in raw_revision],
            [submission_row_from_dict(d) for d in raw_completed],
            student_name,
        )

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
            queue_content = Div(
                *[render_queue_item(queue_item_from_dict(item)) for item in result.value]
            )

        content = Div(
            PageHeader("Review Queue", subtitle="Student submissions awaiting your review"),
            queue_content,
        )
        return render_teaching_sidebar_page(
            content=content,
            active="queue",
            request=request,
        )

    # ------------------------------------------------------------------
    # REVIEW DETAIL
    # ------------------------------------------------------------------

    @rt("/teaching/review/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    def teaching_review_detail(request: Request, uid: str, current_user: Any = None) -> Any:
        """Review detail — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Review Submission"),
            content_loading_placeholder(f"/teaching/review/{uid}/content", "review-detail-content"),
        )
        return render_teaching_sidebar_page(
            content=content,
            active="queue",
            request=request,
        )

    @rt("/teaching/review/{uid}/content")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_review_detail_content_fragment(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """HTMX fragment: review detail with submission content + feedback history + forms."""
        user_uid = require_authenticated_user(request)

        # get_submission_detail is the access gate — it returns not-found for a
        # submission outside a group this teacher owns. The role gate said "may
        # review"; this says "not this one". Everything below (feedback history,
        # the feedback/revision forms whose Save is itself group-gated) reads or
        # writes this student's private work, so it must sit behind the same
        # check. Short-circuit to the byte-identical fragment a missing UID
        # yields, so a denied read cannot be told from a nonexistent one and no
        # dead Save form is shown (OWNERSHIP_VERIFICATION.md).
        detail_result = await orchestrator.get_submission_detail(
            submission_uid=uid, teacher_uid=user_uid
        )
        if detail_result.is_error or not detail_result.value:
            return Div(
                P("Submission not found.", cls="text-sm text-muted-foreground italic"),
                id="review-detail-content",
            )

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
        submission_section: Any = render_submission_content(detail)

        # Fetch feedback history via the typed read path — access already
        # established above.
        feedback_history_section: Any = ""
        if entry_report_service is not None:
            history_result = await entry_report_service.list_for_submission(uid)
            if not history_result.is_error and history_result.value:
                feedback_items = [render_report_item(fb) for fb in history_result.value]
                feedback_history_section = Div(
                    H3("Feedback History", cls="text-lg font-semibold mb-3"),
                    Div(*feedback_items),
                    cls="mb-6",
                )

        return Div(
            submission_section,
            feedback_history_section,
            render_feedback_submission_form(uid),
            render_revision_request_form(uid),
            Div(
                ButtonLink(
                    "Back to Queue",
                    href="/teaching/queue",
                    cls=(ButtonT.ghost, "mt-4"),
                    size="sm",
                ),
            ),
            id="review-detail-content",
        )

    # ------------------------------------------------------------------
    # STUDENTS LIST — simple clickable name rows
    # ------------------------------------------------------------------

    @rt("/teaching/students")
    @require_role(UserRole.TEACHER, get_user_service)
    def teaching_students_page(request: Request, current_user: Any = None) -> Any:
        """Students page — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Students", subtitle="Students who have submitted work"),
            content_loading_placeholder("/teaching/students/content", "students-content"),
        )
        return render_teaching_sidebar_page(
            content=content,
            active="students",
            request=request,
        )

    @rt("/teaching/students/content")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_students_content_fragment(request: Request, current_user: Any = None) -> Any:
        """HTMX fragment: students list."""
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

        return Div(students_content, id="students-content")

    # ------------------------------------------------------------------
    # STUDENT HUB — teacher's view of individual student
    # ------------------------------------------------------------------

    @rt("/teaching/students/{uid}")
    @require_role(UserRole.TEACHER, get_user_service)
    def teaching_student_hub_page(request: Request, uid: str, current_user: Any = None) -> Any:
        """Student hub — shell renders immediately, content loads via HTMX."""
        return BasePage(
            content=content_loading_placeholder(
                f"/teaching/students/{uid}/content", "student-hub-content"
            ),
            title="Student",
            request=request,
            active_page="teaching",
        )

    @rt("/teaching/students/{uid}/content")
    @require_role(UserRole.TEACHER, get_user_service)
    async def teaching_student_hub_content_fragment(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """HTMX fragment: student hub with resolved display name."""
        user_uid = require_authenticated_user(request)
        result = await orchestrator.get_student_submissions(teacher_uid=user_uid, student_uid=uid)
        student_name = uid
        if not result.is_error and result.value:
            for item in result.value:
                raw_name = item.get("student_name")
                if raw_name:
                    student_name = str(raw_name)
                    break
        display_name = _display_student_name(student_name)
        return StudentHub(student_name=display_name, student_uid=uid)

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

        ku_detail = await orchestrator.get_student_ku_detail(teacher_uid=user_uid, student_uid=uid)
        section_content: Any = render_student_detail_sections(
            pending=pending,
            revision_requested=revision_requested,
            completed=completed,
            student_name=student_name,
            ku_detail=ku_detail,
        )

        # Determine default section from query param or submission state
        tab_param = request.query_params.get("tab")
        if tab_param in _REVIEW_TAB_IDS:
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
            Icon("arrow-left", size=18),
            href=f"/teaching/students/{uid}",
            cls="p-1.5 rounded hover:bg-accent transition-colors inline-flex items-center",
            aria_label="Back to student overview",
        )

        # Mobile back link (above tabs)
        mobile_back = Div(
            A(
                Icon("arrow-left", size=14, cls="inline mr-1"),
                display_name,
                href=f"/teaching/students/{uid}",
                cls="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1",
            ),
            cls="mb-2",
        )

        return SidebarPage(
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
                description="Click “New Group” above to create your first group, "
                "or upload a group YAML at /upload.",
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

        new_group_button = Button(
            "+ New Group",
            type="button",
            cls=ButtonT.primary,
            size="sm",
            **{
                "x-on:click": "open = true"
            },  # fasthtml dynamic-attr splat: Alpine colon attr has no underscore-kwarg form
        )

        content = Div(
            PageHeader(
                "Groups",
                subtitle="Your groups and their activity",
                actions=new_group_button,
            ),
            groups_content,
            _new_group_modal(),
            x_data="{ open: false }",
        )
        return render_teaching_sidebar_page(
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
                cls=(ButtonT.ghost, "mt-4"),
                size="sm",
            ),
        )

        content = Div(
            PageHeader(group_name, subtitle="Members and their submission progress"),
            members_content,
            back_link,
        )
        return render_teaching_sidebar_page(
            content=content,
            active="groups",
            request=request,
        )

    # ------------------------------------------------------------------
    # STUDENT HUB PREVIEW ENDPOINTS (HTMX lazy-loaded)
    # ------------------------------------------------------------------

    @rt("/api/teaching/students/{uid}/submissions/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_submissions_preview(
        request: Request, uid: str, current_user: Any = None
    ) -> Any:
        """HTMX OOB fragment: all 3 submission bucket previews in one DB round-trip.

        Replaces the former /pending/preview, /revision/preview, /completed/preview
        endpoints that each called _get_bucketed_submissions() independently.
        Returns 3 OOB-swapped Divs targeting hub-panel-{slug} placeholders rendered
        by StudentHub without HTMX attrs.
        """
        user_uid = require_authenticated_user(request)
        pending, revision, completed, _ = await _get_bucketed_submissions(user_uid, uid)

        def _make_fragment(slug: str, rows: list[SubmissionRow], empty_label: str) -> Div:
            if not rows:
                content: Any = HubPreviewEmpty(empty_label)
            else:
                cards = [
                    HubPreviewCard(
                        title=row.title or "Untitled",
                        href=f"/teaching/students/{uid}/submissions?tab={slug}",
                        badge=submission_preview_badge(row.status),
                    )
                    for row in rows[:3]
                ]
                content = HubPreviewGrid(cards)
            return Div(content, id=f"hub-panel-{slug}", hx_swap_oob="true")

        return Div(
            _make_fragment("pending", pending, "submissions needing review"),
            _make_fragment("revision", revision, "revision requests"),
            _make_fragment("completed", completed, "completed submissions"),
        )

    @rt("/api/teaching/students/{uid}/ku/preview")
    @require_role(UserRole.TEACHER, get_user_service)
    async def student_ku_preview(request: Request, uid: str, current_user: Any = None) -> Any:
        """HTMX fragment: top 3 KU progress items for student hub preview."""
        user_uid = require_authenticated_user(request)
        ku_detail = await orchestrator.get_student_ku_detail(teacher_uid=user_uid, student_uid=uid)
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
                badge=submission_preview_badge(label),
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
