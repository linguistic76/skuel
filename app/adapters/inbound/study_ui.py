"""
Study UI Routes — Student Workspace Hub
========================================

The student's core workspace for submitting work, tracking submissions,
and reviewing feedback. All sub-pages are top-level routes with shared sidebar.

Layout: 6-item sidebar (Exercises / Submit / My Submissions / Exercise Reports / Activity Reports
/ Generate Reports) on sub-pages. Landing page (/study) has no sidebar.

Routes:
- GET /study — Dashboard landing (no sidebar)
- GET /submit — File upload form
- GET /submissions — My submitted work (yours + browse merged)
- GET /exercise-reports — Teacher/AI feedback on exercise submissions
- GET /activity-reports — AI and scheduled activity feedback
- GET /generate-reports — On-demand progress report generation
- GET /submissions/{uid} — Submission detail page
- HTMX fragments for all above
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
    Span,
)
from starlette.datastructures import UploadFile
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteDecorator, RouteList
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.forms import Select
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader
from ui.study.layout import create_study_page
from ui.submissions.cards import (
    render_processed_content,
    render_submission_detail,
    render_submissions_grid,
    render_upload_status,
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
from ui.submissions.report import (
    render_activity_report_list,
    render_progress_report_list,
    render_received_report_list,
    render_yours_list,
)
from ui.submissions.sharing import render_sharing_section
from ui.cards import Card, CardBody

logger = get_logger("skuel.routes.study")


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
# ROUTE CREATION
# ============================================================================


def create_study_ui_routes(
    _app,
    rt: RouteDecorator,
    submissions_service,
    processing_service,
    user_service=None,
    exercises_service=None,
    submissions_search_service=None,
    submissions_core_service=None,
    activity_report_service=None,
    teacher_review_service=None,
) -> RouteList:
    """Create /learn UI routes (workspace hub + submission management).

    Args:
        _app: FastHTML application instance
        rt: Router instance
        submissions_service: SubmissionsService
        processing_service: SubmissionsProcessingService
        user_service: UserService for context loading
        exercises_service: ExerciseService for exercise dropdown
        submissions_search_service: SubmissionsSearchService for feedback status queries
        submissions_core_service: SubmissionsCoreService for received assessments
        activity_report_service: ActivityReportService for activity feedback history
        teacher_review_service: TeacherReviewService for feedback on submissions
    """

    logger.info("Creating Study UI routes")

    # ========================================================================
    # HELPER
    # ========================================================================

    async def _get_context(user_uid: str) -> Any:
        """Get UserContext for landing page."""
        if not user_service:
            raise ValueError("User service unavailable")
        result = await user_service.get_rich_unified_context(user_uid)
        if result.is_error:
            raise ValueError(f"Failed to load context: {result.error}")
        return result.value

    # ========================================================================
    # LANDING PAGE (no sidebar)
    # ========================================================================

    @rt("/study")
    async def study_landing(request: Request) -> Any:
        """Learning workspace hub — submit work, track submissions, review feedback."""
        user_uid = require_authenticated_user(request)

        try:
            context = await _get_context(user_uid)
        except ValueError as e:
            return await BasePage(
                Div(
                    H1("Error", cls="text-3xl font-bold text-error mb-4"),
                    P(str(e), cls="text-lg text-muted-foreground"),
                    cls="flex flex-col items-center justify-center min-h-[400px] p-8",
                ),
                title="Study",
                request=request,
                active_page="study",
            )

        from ui.study.dashboard import StudyDashboardView

        content = StudyDashboardView(context)
        return await BasePage(
            content,
            title="Study",
            request=request,
            active_page="study",
        )

    # ========================================================================
    # SUBMIT PAGE (sidebar)
    # ========================================================================

    @rt("/submit")
    async def study_submit(request: Request) -> Any:
        """Submit page: upload form with optional exercise selector."""
        user_uid = require_authenticated_user(request)

        assigned_exercises: list[Any] = []
        if exercises_service:
            exercises_result = await exercises_service.get_student_exercises(user_uid)
            if not exercises_result.is_error and exercises_result.value:
                assigned_exercises = exercises_result.value

        selected_exercise_uid = request.query_params.get("exercise_uid")

        content = Div(
            PageHeader("Submit", subtitle="Upload a file linked to a Knowledge Unit"),
            render_upload_form(assigned_exercises, selected_exercise_uid=selected_exercise_uid),
            upload_form_script(),
        )
        return await create_study_page(
            content=content,
            active_section="submit",
            request=request,
            title="Submit - Study",
        )

    # ========================================================================
    # MY SUBMISSIONS PAGE (sidebar) — merges yours + browse
    # ========================================================================

    @rt("/submissions")
    async def study_submissions(request: Request) -> Any:
        """My Submissions: your submitted work with review status + browse/filter."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "My Submissions",
                subtitle="Your submitted work and review status",
            ),
            render_yours_list_container(),
            H3("Browse All", cls="font-semibold mt-8 mb-4"),
            render_filters_section(),
            render_submissions_grid_container(),
        )
        return await create_study_page(
            content=content,
            active_section="submissions",
            request=request,
            title="My Submissions - Study",
        )

    # ========================================================================
    # EXERCISE REPORTS PAGE (sidebar) — teacher/AI feedback on submissions
    # ========================================================================

    @rt("/exercise-reports")
    async def study_exercise_reports(request: Request) -> Any:
        """Teacher and AI exercise reports on submissions."""
        require_authenticated_user(request)

        reports_section = Card(
            Div(
                P("Loading exercise reports...", cls="text-center text-muted-foreground"),
                id="feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/reports/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="bg-background shadow-sm p-4",
        )

        content = Div(
            PageHeader(
                "Exercise Reports",
                subtitle="Teacher and AI feedback on your exercise submissions",
            ),
            reports_section,
        )
        return await create_study_page(
            content=content,
            active_section="exercise-reports",
            request=request,
            title="Exercise Reports - Study",
        )

    # ========================================================================
    # ACTIVITY REPORTS PAGE (sidebar) — activity feedback + progress reports
    # ========================================================================

    @rt("/activity-reports")
    async def study_activity_reports(request: Request) -> Any:
        """Activity feedback — AI and scheduled activity reports."""
        require_authenticated_user(request)

        activity_feedback_section = Card(
            Div(
                P("Loading activity reports...", cls="text-center text-muted-foreground"),
                id="activity-feedback-list",
                cls="mt-2",
                **{
                    "hx-get": "/reports/activity-list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="bg-background shadow-sm p-4",
        )

        content = Div(
            PageHeader(
                "Activity Reports",
                subtitle="AI and scheduled feedback on your activity patterns",
            ),
            activity_feedback_section,
        )
        return await create_study_page(
            content=content,
            active_section="activity-reports",
            request=request,
            title="Activity Reports - Study",
        )

    # ========================================================================
    # GENERATE REPORTS PAGE (sidebar) — on-demand progress report generation
    # ========================================================================

    @rt("/generate-reports")
    async def study_generate_reports(request: Request) -> Any:
        """Generate and view progress reports."""
        require_authenticated_user(request)

        generate_card = Card(
            CardBody(
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

            ),
            cls="bg-background shadow-sm mb-6",
        )

        recent_reports = Div(
            H3("Recent Progress Reports", cls="font-semibold mb-4"),
            Div(
                P("Loading...", cls="text-center text-muted-foreground"),
                id="progress-list",
                **{
                    "hx-get": "/reports/progress-list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
        )

        content = Div(
            PageHeader(
                "Generate Reports",
                subtitle="Create on-demand progress reports across your domains",
            ),
            generate_card,
            recent_reports,
        )
        return await create_study_page(
            content=content,
            active_section="generate-reports",
            request=request,
            title="Generate Reports - Study",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/list")
    async def study_submissions_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_search_service:
                return Div(
                    P("Submissions service unavailable.", cls="text-center text-error"),
                    id="submissions-yours-list",
                )
            result = await submissions_search_service.get_submissions_with_feedback_status(user_uid)
            items = result.value if not result.is_error else []
            return render_yours_list(items)
        except Exception as e:
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                P("Error loading submissions.", cls="text-center text-error"),
                id="submissions-yours-list",
            )

    @rt("/upload")
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

            raw_exercise_uid = form.get("fulfills_exercise_uid")
            fulfills_exercise_uid = (
                str(raw_exercise_uid).strip() or None if raw_exercise_uid else None
            )

            result = await submissions_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.EXERCISE_SUBMISSION,
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

    @rt("/grid")
    async def get_submissions_grid(request: Request) -> Any:
        """HTMX endpoint for loading submissions grid with filters."""
        try:
            user_uid = require_authenticated_user(request)

            filters = parse_submission_filters(request)

            kwargs = {"user_uid": user_uid, "limit": 50}
            if filters.report_type:
                kwargs["report_type"] = filters.report_type
            if filters.status:
                kwargs["status"] = filters.status

            result = await submissions_service.list_submissions(**kwargs)

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

    @rt("/reports/list")
    async def study_reports_list(request: Request) -> Any:
        """HTMX fragment: teacher assessments received."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_core_service:
                return Div(
                    P("Feedback service unavailable.", cls="text-center text-error"),
                    id="feedback-list",
                )
            result = await submissions_core_service.get_assessments_for_student(
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

    @rt("/reports/activity-list")
    async def study_activity_report_list(request: Request) -> Any:
        """HTMX fragment: activity reports."""
        try:
            user_uid = require_authenticated_user(request)
            if not activity_report_service:
                return Div(
                    P(
                        "Activity feedback unavailable.",
                        cls="text-center text-muted-foreground py-4",
                    ),
                    id="activity-feedback-list",
                )
            result = await activity_report_service.get_history(subject_uid=user_uid, limit=10)
            items = result.value if not result.is_error else []
            return render_activity_report_list(items)
        except Exception as e:
            logger.error(f"Error loading activity feedback list: {e}", exc_info=True)
            return Div(
                P("Error loading activity feedback.", cls="text-center text-error"),
                id="activity-feedback-list",
            )

    @rt("/reports/progress-list")
    async def study_progress_list(request: Request) -> Any:
        """HTMX fragment: progress reports."""
        try:
            user_uid = require_authenticated_user(request)
            result = await submissions_service.list_submissions(
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

    # ========================================================================
    # SUBMISSION DETAIL HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/{uid}/info")
    async def get_submission_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission detail info."""
        try:
            result = await submissions_service.get_submission(uid)

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
            result = await submissions_service.get_submission(uid)

            if result.is_error or not result.value:
                return render_processed_content(None, False)

            submission = result.value
            content = submission.processed_content if submission else None
            return render_processed_content(content, bool(content))

        except Exception as e:
            logger.error(f"Error loading submission content: {e}", exc_info=True)
            return render_processed_content(None, False)

    @rt("/submissions/{uid}/report")
    async def get_submission_report(request: Request, uid: str) -> Any:
        """HTMX endpoint: report received on this submission."""
        from ui.patterns.report_item import render_report_item

        try:
            user_uid = require_authenticated_user(request)

            sub_result = await submissions_service.get_submission(uid)
            if sub_result.is_error or not sub_result.value:
                return Div(P("Submission not found.", cls="text-error"), id="feedback-section")
            if sub_result.value.user_uid != user_uid:
                return Div(P("Access denied.", cls="text-error"), id="feedback-section")

            if not teacher_review_service:
                return Div(
                    P("No feedback yet.", cls="text-center text-muted-foreground py-4"),
                    id="feedback-section",
                )

            history_result = await teacher_review_service.get_report_history(uid)
            items = history_result.value if not history_result.is_error else []

            if not items:
                return Div(
                    H4("Feedback", cls="mb-4"),
                    P("No feedback yet.", cls="text-center text-muted-foreground py-4"),
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

            if not exercises_service:
                return Div(id="exercise-link")

            result = await exercises_service.get_exercise_for_submission(uid)

            if result.is_error or not result.value:
                return Div(id="exercise-link")

            record = result.value
            ex_title = record.get("exercise_title", "Exercise")

            return Div(
                Span("Exercise: ", cls="font-medium text-sm text-muted-foreground"),
                Badge(ex_title, variant=BadgeT.outline, size=Size.sm),
                id="exercise-link",
                cls="mt-2",
            )
        except Exception as e:
            logger.error(f"Error loading exercise link for {uid}: {e}", exc_info=True)
            return Div(id="exercise-link")

    @rt("/submissions/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await submissions_service.get_submission(uid)
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
            result = await submissions_service.get_submission(uid)
            if result.is_error:
                return Div("Report not found", cls="text-error")

            submission = result.value
            return render_tags_manager(submission)

        except Exception as e:
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return Div("Error loading tags manager", cls="text-error")

    @rt("/submissions/{uid}/shared-users")
    async def get_shared_users_ui(request: Request, uid: str) -> Any:
        """HTMX endpoint for rendering shared users list."""
        try:
            _user_uid = require_authenticated_user(request)

            return Div(
                P(
                    "Shared users list will appear here after sharing",
                    cls="text-sm text-muted-foreground",
                ),
                Badge("No users yet", variant=BadgeT.ghost),
                id="shared-users-content",
            )

        except Exception as e:
            logger.error(f"Error loading shared users: {e}", exc_info=True)
            return Div("Error loading shared users", cls="text-error text-sm")

    # ========================================================================
    # SUBMISSION DETAIL PAGE — MUST BE LAST (catch-all pattern)
    # ========================================================================

    @rt("/submissions/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
        """Submission detail view with HTMX-loaded sections."""
        user_uid = require_authenticated_user(request)

        submission_result = await submissions_service.get_submission(uid)
        is_owner = False
        if not submission_result.is_error and submission_result.value is not None:
            is_owner = submission_result.value.user_uid == user_uid

        detail_card = Card(
            CardBody(
                H3("Submission Details"),
                Div(
                    P("Loading submission details...", cls="text-center text-muted-foreground"),
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
                        P("Loading content...", cls="text-center text-muted-foreground"),
                        id="processed-content",
                        cls="p-4 bg-muted rounded-lg",
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
                    P("Loading feedback...", cls="text-center text-muted-foreground py-2"),
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

            ),
            cls="bg-background shadow-sm",
        )

        content = Div(
            Div(
                H1("Submission Details", cls="text-3xl font-bold"),
                P(f"UID: {uid}", cls="text-lg text-muted-foreground"),
                cls="text-center mb-8",
            ),
            detail_card,
        )

        return await BasePage(
            content,
            title="Submission Details",
            request=request,
            active_page="study",
        )

    logger.info(
        "Study UI routes created (/study, /submit, /submissions, /exercise-reports, /activity-reports, /generate-reports)"
    )

    # Route order matters! Specific routes before parameterized routes.
    return [
        study_landing,  # /learn (exact)
        study_submit,  # /submit
        study_submissions,  # /submissions
        study_exercise_reports,  # /exercise-reports
        study_activity_reports,  # /activity-reports
        study_generate_reports,  # /generate-reports
        study_reports_list,  # /reports/list (HTMX)
        study_activity_report_list,  # /reports/activity-list (HTMX)
        study_progress_list,  # /reports/progress-list (HTMX)
        study_submissions_list,  # /submissions/list (HTMX)
        upload_submission,  # /upload (HTMX POST)
        get_submissions_grid,  # /grid (HTMX GET)
        get_submission_info,  # /submissions/{uid}/info
        get_submission_content,  # /submissions/{uid}/content
        get_submission_report,  # /submissions/{uid}/report
        get_submission_exercise,  # /submissions/{uid}/exercise
        get_category_selector,  # /submissions/{uid}/category-selector
        get_tags_manager,  # /submissions/{uid}/tags-manager
        get_shared_users_ui,  # /submissions/{uid}/shared-users
        submission_detail,  # /submissions/{uid} (catch-all — LAST)
    ]
