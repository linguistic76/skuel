"""
Submissions UI Routes
=====================

File submission with sidebar navigation (Submit / Browse / Your Submissions).
Regular users upload files here to share with teachers, peers, or mentors.
Processor type is auto-set to HUMAN — AI processing lives in Report Projects
(role-gated to TEACHER+).

Layout: Unified sidebar (Tailwind + Alpine) with 5 nav items.
Desktop: collapsible sidebar. Mobile: horizontal tabs.
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import (
    H1,
    H3,
    H4,
    A,
    Div,
    Form,
    Label,
    Option,
    P,
    Select,
    Span,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage
from ui.submissions.assignments import render_assignments_list
from ui.submissions.cards import (
    render_processed_content,
    render_submission_detail,
    render_submissions_grid,
    render_upload_status,
)
from ui.submissions.report import (
    render_activity_report_list,
    render_progress_report_list,
    render_received_report_list,
    render_yours_list,
)
from ui.submissions.forms import (
    render_category_selector,
    render_filters_section,
    render_submissions_grid_container,
    render_tags_manager,
    render_upload_form,
    render_yours_list_container,
    upload_form_script,
)
from ui.submissions.sharing import render_sharing_section

logger = get_logger("skuel.routes.submissions.ui")


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class SubmissionFilters:
    """Typed filters for submission list queries."""

    report_type: str
    status: str


def parse_submission_filters(request: Request) -> SubmissionFilters:
    """Extract submission filter parameters from request query params."""
    return SubmissionFilters(
        report_type=request.query_params.get("report_type", ""),
        status=request.query_params.get("status", ""),
    )


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

SUBMISSIONS_SIDEBAR_ITEMS = [
    SidebarItem("Assignments", "/submissions/assignments", "assignments", icon="📋"),
    SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
    SidebarItem("Your Submissions", "/submissions/yours", "yours", icon="📝"),
    SidebarItem("Reports", "/submissions/reports", "reports", icon="💬"),
    SidebarItem("Progress", "/submissions/progress", "progress", icon="📊"),
]


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_submissions_ui_routes(
    _app,
    rt,
    _submissions_service,
    _processing_service,
    _exercises_service=None,
    _submissions_search_service=None,
    _submissions_core_service=None,
    _activity_report_service=None,
    _teacher_review_service=None,
):
    """
    Create all submission UI routes.

    Args:
        app: FastHTML application instance
        rt: Router instance
        report_service: SubmissionsService
        processing_service: SubmissionsProcessingService
        _exercises_service: ExerciseService for exercise dropdown (optional)
        _submissions_search_service: SubmissionsSearchService for feedback status queries (optional)
        _submissions_core_service: SubmissionsCoreService for received assessments (optional)
        _activity_report_service: ActivityReportService for activity feedback history (optional)
    """

    logger.info("Creating Submissions UI routes")

    # ========================================================================
    # SIDEBAR PAGES
    # ========================================================================

    @rt("/submissions")
    async def submissions_landing(request: Request) -> Any:
        """Submissions landing — defaults to Submit page."""
        return await _render_submit_page(request)

    @rt("/submissions/submit")
    async def submissions_submit_page(request: Request) -> Any:
        """Submit page: upload form."""
        return await _render_submit_page(request)

    async def _render_submit_page(request: Request) -> Any:
        user_uid = require_authenticated_user(request)

        # Fetch assigned exercises for exercise dropdown (via group membership)
        assigned_exercises: list[Any] = []
        if _exercises_service:
            exercises_result = await _exercises_service.get_student_exercises(user_uid)
            if not exercises_result.is_error and exercises_result.value:
                assigned_exercises = exercises_result.value

        # Pre-select exercise if arriving from assignments page
        selected_exercise_uid = request.query_params.get("exercise_uid")

        content = Div(
            PageHeader("Submit", subtitle="Upload a file linked to a Knowledge Unit"),
            render_upload_form(assigned_exercises, selected_exercise_uid=selected_exercise_uid),
            upload_form_script(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="submit",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Submit",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/assignments")
    async def submissions_assignments_page(request: Request) -> Any:
        """Assignments page: exercises assigned to this student via group membership."""
        user_uid = require_authenticated_user(request)

        exercises: list[dict[str, Any]] = []
        if _exercises_service:
            result = await _exercises_service.get_student_exercises_with_status(user_uid)
            if not result.is_error and result.value:
                exercises = result.value

        content = Div(
            PageHeader(
                "Assignments",
                subtitle="Exercises assigned by your teachers",
            ),
            render_assignments_list(exercises),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="assignments",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Assignments",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/browse")
    async def submissions_browse_page(request: Request) -> Any:
        """Browse page: filters + results grid."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Browse Submissions", subtitle="Filter and find submissions"),
            render_filters_section(),
            render_submissions_grid_container(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="browse",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Browse Submissions",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/yours")
    async def submissions_yours_page(request: Request) -> Any:
        """Your Submissions page: list with teacher review status badges."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Your Submissions",
                subtitle="See which submissions have been reviewed by a teacher",
            ),
            render_yours_list_container(),
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="yours",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Your Submissions",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/yours/list")
    async def submissions_yours_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            if not _submissions_search_service:
                return Div(
                    P("Submissions service unavailable.", cls="text-center text-error"),
                    id="submissions-yours-list",
                )
            result = await _submissions_search_service.get_submissions_with_feedback_status(
                user_uid
            )
            items = result.value if not result.is_error else []
            return render_yours_list(items)
        except Exception as e:
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                P("Error loading submissions.", cls="text-center text-error"),
                id="submissions-yours-list",
            )

    @rt("/submissions/upload")
    async def upload_submission(request: Request) -> Any:
        """HTMX endpoint for submission file upload (human review)."""
        try:
            form = await request.form()
            uploaded_file = form.get("file")
            raw_identifier = form.get("identifier")
            identifier = str(raw_identifier).strip() if raw_identifier else ""

            if not identifier:
                return render_upload_status("error", "Identifier is required", is_error=True)

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"

            logger.info(
                f"Report upload: {filename} ({len(file_content)} bytes, identifier={identifier})"
            )

            # Extract optional exercise link
            raw_exercise_uid = form.get("fulfills_exercise_uid")
            fulfills_exercise_uid = (
                str(raw_exercise_uid).strip() or None if raw_exercise_uid else None
            )

            # Submit for human review — processor_type always HUMAN for regular users
            result = await _submissions_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.SUBMISSION,
                processor_type=ProcessorType.HUMAN,
                metadata={"identifier": identifier},
                fulfills_exercise_uid=fulfills_exercise_uid,
            )

            if result.is_error:
                return render_upload_status("error", str(result.error), is_error=True)

            submission = result.value
            return render_upload_status(
                status=submission.status,
                message="File uploaded successfully",
                submission_uid=submission.uid,
            )

        except Exception as e:
            logger.error(f"Error uploading submission: {e}", exc_info=True)
            return render_upload_status("error", f"Upload failed: {e}", is_error=True)

    @rt("/submissions/grid")
    async def get_submissions_grid(request: Request) -> Any:
        """HTMX endpoint for loading reports grid with filters."""
        try:
            user_uid = require_authenticated_user(request)

            filters = parse_submission_filters(request)

            kwargs = {"user_uid": user_uid, "limit": 50}
            if filters.report_type:
                kwargs["report_type"] = filters.report_type
            if filters.status:
                kwargs["status"] = filters.status

            result = await _submissions_service.list_submissions(**kwargs)

            if result.is_error:
                return Div(
                    P("Failed to load reports", cls="text-center text-error"),
                    id="submissions-grid-container",
                )

            reports = result.value or []
            return render_submissions_grid(reports)

        except Exception as e:
            logger.error(f"Error loading reports: {e}", exc_info=True)
            return Div(
                P(f"Error: {e}", cls="text-center text-error"),
                id="submissions-grid-container",
            )

    @rt("/submissions/{uid}/info")
    async def get_submission_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission detail info."""
        try:
            result = await _submissions_service.get_submission(uid)

            if result.is_error:
                return Div(
                    Div(
                        P(f"Failed to load submission: {result.error}"),
                        cls="alert alert-error",
                    ),
                    id="submission-info",
                )

            submission = result.value
            if not submission:
                return Div(
                    Div(
                        P(f"Report {uid} not found"),
                        cls="alert alert-warning",
                    ),
                    id="submission-info",
                )
            return render_submission_detail(submission)

        except Exception as e:
            logger.error(f"Error loading submission info: {e}", exc_info=True)
            return Div(
                Div(
                    P(f"Error: {e}"),
                    cls="alert alert-error",
                ),
                id="submission-info",
            )

    @rt("/submissions/{uid}/content")
    async def get_submission_content(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission processed content."""
        try:
            result = await _submissions_service.get_submission(uid)

            if result.is_error or not result.value:
                return render_processed_content(None, False)

            submission = result.value
            content = submission.processed_content if submission else None
            return render_processed_content(content, bool(content))

        except Exception as e:
            logger.error(f"Error loading submission content: {e}", exc_info=True)
            return render_processed_content(None, False)

    # ========================================================================
    # FEEDBACK & EXERCISE LINK HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/{uid}/report")
    async def get_submission_report(request: Request, uid: str) -> Any:
        """HTMX endpoint: report received on this submission."""
        from ui.patterns.report_item import render_report_item

        try:
            user_uid = require_authenticated_user(request)

            # Verify ownership
            sub_result = await _submissions_service.get_submission(uid)
            if sub_result.is_error or not sub_result.value:
                return Div(P("Submission not found.", cls="text-error"), id="feedback-section")
            if sub_result.value.user_uid != user_uid:
                return Div(P("Access denied.", cls="text-error"), id="feedback-section")

            if not _teacher_review_service:
                return Div(
                    P("No feedback yet.", cls="text-center text-base-content/60 py-4"),
                    id="feedback-section",
                )

            history_result = await _teacher_review_service.get_feedback_history(uid)
            items = history_result.value if not history_result.is_error else []

            if not items:
                return Div(
                    H4("Feedback", cls="mb-4"),
                    P("No feedback yet.", cls="text-center text-base-content/60 py-4"),
                    id="feedback-section",
                )

            return Div(
                H4("Feedback", cls="mb-4"),
                *[render_report_item(fb) for fb in items],
                id="feedback-section",
            )
        except Exception as e:
            logger.error(f"Error loading feedback for {uid}: {e}", exc_info=True)
            return Div(
                P("Error loading feedback.", cls="text-error"),
                id="feedback-section",
            )

    @rt("/submissions/{uid}/exercise")
    async def get_submission_exercise(request: Request, uid: str) -> Any:
        """HTMX endpoint: which exercise this submission fulfills."""
        try:
            require_authenticated_user(request)

            if not _exercises_service:
                return Div(id="exercise-link")

            result = await _exercises_service.get_exercise_for_submission(uid)

            if result.is_error or not result.value:
                return Div(id="exercise-link")

            record = result.value
            ex_title = record.get("exercise_title", "Exercise")

            return Div(
                Span("Exercise: ", cls="font-medium text-sm text-base-content/60"),
                Span(ex_title, cls="badge badge-outline badge-sm"),
                id="exercise-link",
                cls="mt-2",
            )
        except Exception as e:
            logger.error(f"Error loading exercise link for {uid}: {e}", exc_info=True)
            return Div(id="exercise-link")

    # ========================================================================
    # CONTENT MANAGEMENT UI ROUTES
    # ========================================================================

    @rt("/submissions/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await _submissions_service.get_submission(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            submission = result.value
            return render_category_selector(submission)

        except Exception as e:
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return Div("Error loading category selector", cls="text-error")

    @rt("/submissions/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await _submissions_service.get_submission(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            submission = result.value
            return render_tags_manager(submission)

        except Exception as e:
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return Div("Error loading tags manager", cls="text-error")

    # ========================================================================
    # FEEDBACK PAGE (assessments received)
    # ========================================================================

    @rt("/submissions/reports")
    async def submissions_reports_page(request: Request) -> Any:
        """Reports page: assessments received from teachers + AI activity reports."""
        require_authenticated_user(request)

        teacher_section = Div(
            H3("Teacher Assessments", cls="font-semibold mb-4"),
            Div(
                P("Loading feedback...", cls="text-center text-base-content/60"),
                id="feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/submissions/reports/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="card bg-base-100 shadow-sm p-4 mb-6",
        )

        activity_feedback_section = Div(
            H3("Activity Feedback", cls="font-semibold mb-4"),
            Div(
                P("Loading activity feedback...", cls="text-center text-base-content/60"),
                id="activity-feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/submissions/reports/activity-list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="card bg-base-100 shadow-sm p-4",
        )

        content = Div(
            PageHeader("Submission Reports", subtitle="Assessments and feedback from teachers"),
            teacher_section,
            activity_feedback_section,
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="reports",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Submission Reports",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/reports/list")
    async def submissions_reports_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of teacher assessments received."""
        try:
            user_uid = require_authenticated_user(request)
            if not _submissions_core_service:
                return Div(
                    P("Feedback service unavailable.", cls="text-center text-error"),
                    id="feedback-list",
                )
            result = await _submissions_core_service.get_assessments_for_student(
                student_uid=user_uid
            )
            items = result.value if not result.is_error else []
            return render_received_report_list(items)
        except Exception as e:
            logger.error(f"Error loading feedback list: {e}", exc_info=True)
            return Div(
                P("Error loading feedback.", cls="text-center text-error"),
                id="feedback-list",
            )

    @rt("/submissions/reports/activity-list")
    async def submissions_activity_report_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of activity reports."""
        try:
            user_uid = require_authenticated_user(request)
            if not _activity_report_service:
                return Div(
                    P(
                        "Activity feedback unavailable.",
                        cls="text-center text-base-content/60 py-4",
                    ),
                    id="activity-feedback-list",
                )
            result = await _activity_report_service.get_history(subject_uid=user_uid, limit=10)
            items = result.value if not result.is_error else []
            return render_activity_report_list(items)
        except Exception as e:
            logger.error(f"Error loading activity feedback list: {e}", exc_info=True)
            return Div(
                P("Error loading activity feedback.", cls="text-center text-error"),
                id="activity-feedback-list",
            )

    # ========================================================================
    # PROGRESS PAGE (generate + view progress reports)
    # ========================================================================

    @rt("/submissions/progress")
    async def submissions_progress_page(request: Request) -> Any:
        """Progress page: generate and view progress reports."""
        require_authenticated_user(request)

        generate_card = Div(
            Div(
                H3("Generate Progress Report", cls="font-semibold mb-4"),
                Form(
                    Div(
                        Label("Time Period", cls="label"),
                        Select(
                            Option("Last 7 days", value="7d", selected=True),
                            Option("Last 14 days", value="14d"),
                            Option("Last 30 days", value="30d"),
                            Option("Last 90 days", value="90d"),
                            name="time_period",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-3",
                    ),
                    Div(
                        Label("Depth", cls="label"),
                        Select(
                            Option("Summary (counts only)", value="summary"),
                            Option("Standard (counts + examples)", value="standard", selected=True),
                            Option("Detailed (full breakdown)", value="detailed"),
                            name="depth",
                            cls="select select-bordered w-full",
                        ),
                        cls="mb-4",
                    ),
                    Div(
                        Button(
                            "Generate Now",
                            type="submit",
                            variant=ButtonT.primary,
                        ),
                        cls="text-center",
                    ),
                    Div(id="generate-status", cls="mt-4"),
                    **{
                        "hx-post": "/api/reports/progress/generate",
                        "hx-target": "#generate-status",
                        "hx-swap": "innerHTML",
                        "hx-vals": 'js:JSON.stringify({time_period: document.querySelector("[name=time_period]").value, depth: document.querySelector("[name=depth]").value, include_insights: true})',
                        "hx-headers": '{"Content-Type": "application/json"}',
                    },
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm mb-6",
        )

        recent_reports = Div(
            H3("Recent Progress Reports", cls="font-semibold mb-4"),
            Div(
                P("Loading...", cls="text-center text-base-content/60"),
                id="progress-list",
                **{
                    "hx-get": "/submissions/progress/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
        )

        content = Div(
            PageHeader("Progress Reports", subtitle="Track your activity over time"),
            generate_card,
            recent_reports,
        )
        return await SidebarPage(
            content=content,
            items=SUBMISSIONS_SIDEBAR_ITEMS,
            active="progress",
            title="Submissions",
            subtitle="Submit and manage files",
            storage_key="submissions-sidebar",
            page_title="Progress Reports",
            request=request,
            active_page="submissions",
            title_href="/submissions",
        )

    @rt("/submissions/progress/list")
    async def submissions_progress_list(request: Request) -> Any:
        """HTMX fragment: server-rendered list of progress reports."""
        try:
            user_uid = require_authenticated_user(request)
            result = await _submissions_service.list_submissions(
                user_uid=user_uid,
                entity_type=EntityType.ACTIVITY_REPORT,
                limit=10,
            )
            items = result.value if not result.is_error else []
            return render_progress_report_list(items)
        except Exception as e:
            logger.error(f"Error loading progress report list: {e}", exc_info=True)
            return Div(
                P("Error loading progress reports.", cls="text-center text-error"),
                id="progress-list",
            )

    @rt("/submissions/{uid}/shared-users")
    async def get_shared_users_ui(request: Request, uid: str) -> Any:
        """HTMX endpoint for rendering shared users list."""
        try:
            _user_uid = require_authenticated_user(request)

            return Div(
                P(
                    "Shared users list will appear here after sharing",
                    cls="text-sm text-base-content/60",
                ),
                Span("No users yet", cls="badge badge-ghost"),
                id="shared-users-content",
            )

        except Exception as e:
            logger.error(f"Error loading shared users: {e}", exc_info=True)
            return Div("Error loading shared users", cls="text-error text-sm")

    # ========================================================================
    # REPORT DETAIL VIEW - HTMX-powered
    # ========================================================================
    # IMPORTANT: This route MUST be defined LAST because /submissions/{uid}
    # is a catch-all pattern that would match specific routes like
    # /reports/grid, /reports/upload, etc.
    # ========================================================================

    @rt("/submissions/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
        """
        Report detail view.

        Shows:
        - Report metadata (loaded via HTMX)
        - Processing status and duration
        - Processed content (formatted)
        - Download links for original and processed files
        - Sharing controls (visibility, share button, shared users)
        """
        user_uid = require_authenticated_user(request)

        submission_result = await _submissions_service.get_submission(uid)
        is_owner = False
        if not submission_result.is_error and submission_result.value is not None:
            is_owner = submission_result.value.user_uid == user_uid

        detail_card = Div(
            Div(
                H3("Submission Details", cls="card-title"),
                Div(
                    P("Loading submission details...", cls="text-center text-base-content/60"),
                    id="submission-info",
                    cls="mb-4",
                    **{
                        "hx-get": f"/submissions/{uid}/info",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                Div(
                    id="exercise-link",
                    **{
                        "hx-get": f"/submissions/{uid}/exercise",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                Div(
                    H4("Processed Content", cls="mt-6 mb-4"),
                    Div(
                        P("Loading content...", cls="text-center text-base-content/60"),
                        id="processed-content",
                        cls="p-4 bg-base-200 rounded-lg",
                        style="max-height: 600px; overflow-y: auto;",
                        **{
                            "hx-get": f"/submissions/{uid}/content",
                            "hx-trigger": "load",
                            "hx-swap": "outerHTML",
                        },
                    ),
                    id="content-section",
                    cls="mb-4",
                ),
                Div(
                    P("Loading feedback...", cls="text-center text-base-content/60 py-2"),
                    id="feedback-section",
                    cls="mb-4",
                    **{
                        "hx-get": f"/submissions/{uid}/report",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                (
                    render_sharing_section(submission_result.value)
                    if is_owner and not submission_result.is_error
                    else None
                ),
                Div(
                    A(
                        "\u2190 Back to Submissions",
                        href="/submissions",
                        cls="btn btn-ghost",
                    ),
                    cls="mt-4",
                ),
                cls="card-body",
            ),
            cls="card bg-base-100 shadow-sm",
        )

        content = Div(
            Div(
                H1("Submission Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-base-content/60"),
                cls="text-center mb-8",
            ),
            detail_card,
        )

        return await BasePage(
            content,
            title="Submission Details",
            request=request,
            active_page="submissions",
        )

    logger.info("Submissions UI routes created successfully")

    # Route order matters! Specific routes must come BEFORE parameterized routes.
    # Otherwise /submissions/grid would match /submissions/{uid} with uid="grid"
    return [
        submissions_landing,  # /submissions (exact)
        submissions_assignments_page,  # /submissions/assignments (specific)
        submissions_submit_page,  # /submissions/submit (specific)
        submissions_browse_page,  # /submissions/browse (specific)
        submissions_yours_page,  # /submissions/yours (specific)
        submissions_reports_page,  # /submissions/reports (specific)
        submissions_activity_report_list,  # /submissions/reports/activity-list (HTMX fragment)
        submissions_progress_page,  # /submissions/progress (specific)
        submissions_progress_list,  # /submissions/progress/list (HTMX fragment)
        upload_submission,  # /reports/upload (specific, HTMX POST)
        get_submissions_grid,  # /reports/grid (specific, HTMX GET)
        get_submission_info,  # /submissions/{uid}/info (pattern + suffix)
        get_submission_content,  # /submissions/{uid}/content (pattern + suffix)
        get_submission_report,  # /submissions/{uid}/report (pattern + suffix)
        get_submission_exercise,  # /submissions/{uid}/exercise (pattern + suffix)
        get_category_selector,  # /submissions/{uid}/category-selector (pattern + suffix)
        get_tags_manager,  # /submissions/{uid}/tags-manager (pattern + suffix)
        get_shared_users_ui,  # /submissions/{uid}/shared-users (pattern + suffix)
        submission_detail,  # /submissions/{uid} (catch-all - MUST BE LAST)
    ]
