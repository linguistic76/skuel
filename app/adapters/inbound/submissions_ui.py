"""
Submissions UI Routes — ExerciseSubmission Pages
=================================================

Routes for submitting work, browsing submissions, and viewing submission details.

Routes:
- GET /submit — File upload form (standalone, deep-linked from exercises)
- GET /submissions — Tabbed hub: My Submissions | Submit | Request Report
- GET /submissions/{uid} — Submission detail page
- HTMX fragments: /submissions/list, /upload, /grid,
  /submissions/{uid}/{info,content,report,exercise,category-selector,tags-manager,shared-users}

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import (
    H1,
    H3,
    H4,
    Div,
    P,
    Span,
)
from starlette.datastructures import UploadFile

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator, RouteList
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Alert, AlertT, Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.page_header import PageHeader
from ui.profile.hub import submissions_section
from ui.submissions.cards import (
    render_processed_content,
    render_submission_detail,
    render_submissions_grid,
    render_upload_status,
)
from ui.submissions.forms import (
    render_category_selector,
    render_tags_manager,
    render_upload_form,
    upload_form_script,
)
from ui.submissions.report import (
    render_yours_list,
)
from ui.submissions.sharing import render_sharing_section

logger = get_logger("skuel.routes.submissions")


def _parse_md_frontmatter(content: bytes) -> dict[str, str]:
    """Parse simple YAML frontmatter from a Markdown file's bytes.

    Reads the block between the opening and closing ``---`` lines and
    returns a flat key→value mapping.  Only the scalar ``key: value``
    lines produced by the exercise renderer are expected — no nested
    structures or multi-line values.
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:  # safety-net: malformed bytes should not crash upload
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    result: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


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


def create_submissions_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    submissions_service: Any,
    processing_service: Any,
    exercises_service: Any = None,
    submissions_search_service: Any = None,
    submissions_core_service: Any = None,
    teacher_review_service: Any = None,
) -> RouteList:
    """Create /submit and /submissions UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        submissions_service: SubmissionsService
        processing_service: SubmissionsProcessingService
        exercises_service: ExerciseService for exercise dropdown
        submissions_search_service: SubmissionsSearchService for feedback status queries
        submissions_core_service: SubmissionsCoreService for received assessments
        teacher_review_service: TeacherReviewService for feedback on submissions
    """

    # ========================================================================
    # SUBMIT PAGE (standalone — deep-linked from exercises)
    # ========================================================================

    @rt("/submit")
    async def submit_page(request: Request) -> Any:
        """Submit page: upload form with optional exercise selector."""
        user_uid = require_authenticated_user(request)

        assigned_exercises: list[Any] = []
        if exercises_service:
            exercises_result = await exercises_service.get_student_exercises(user_uid)
            if not exercises_result.is_error and exercises_result.value:
                assigned_exercises = exercises_result.value

        selected_exercise_uid = request.query_params.get("exercise_uid")

        content = Div(
            PageHeader("Submit", subtitle="Upload your completed exercise worksheet"),
            render_upload_form(assigned_exercises, selected_exercise_uid=selected_exercise_uid),
            upload_form_script(),
        )
        return await BasePage(
            content=content,
            title="Submit",
            request=request,
            active_page="submissions",
        )

    # ========================================================================
    # MY SUBMISSIONS PAGE — merges yours + browse
    # ========================================================================

    @rt("/submissions")
    async def submissions_page(request: Request) -> Any:
        """Submissions hub: tabbed My Submissions | Submit | Request Report."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Submissions",
                subtitle="Your submitted work, upload new work, or request a report",
            ),
            submissions_section(),
        )
        return await BasePage(
            content=content,
            title="Submissions",
            request=request,
            active_page="submissions",
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/submissions/list")
    async def submissions_list(request: Request) -> Any:
        """HTMX fragment: student's submissions with teacher review status."""
        try:
            user_uid = require_authenticated_user(request)
            if not submissions_search_service:
                return Div(
                    render_error_banner("Submissions service unavailable"),
                    id="submissions-yours-list",
                )
            result = await submissions_search_service.get_submissions_with_feedback_status(user_uid)
            if result.is_error:
                logger.error(f"Error loading submissions history: {result.error}")
                return Div(
                    render_error_banner("Failed to load submissions", str(result.error)),
                    id="submissions-yours-list",
                )
            return render_yours_list(result.value or [])
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submissions history: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading submissions", str(e)),
                id="submissions-yours-list",
            )

    @rt("/submissions/upload")
    async def upload_submission(request: Request) -> Any:
        """HTMX endpoint for submission file upload (human review).

        For .md files with YAML frontmatter (downloaded from /api/exercises/md),
        exercise_uid and revision are read directly from the file — no extra
        form fields required.
        """
        try:
            form = await request.form()
            uploaded_file = form.get("file")

            if not uploaded_file or not isinstance(uploaded_file, UploadFile):
                return render_upload_status("error", "No file provided", is_error=True)

            user_uid = require_authenticated_user(request)
            file_content = await uploaded_file.read()
            filename = uploaded_file.filename or "unknown"

            # Parse YAML frontmatter from .md files (exercise worksheets)
            frontmatter: dict[str, str] = {}
            if filename.endswith(".md"):
                frontmatter = _parse_md_frontmatter(file_content)

            # exercise_uid: form selector wins; fallback to frontmatter
            raw_exercise_uid = form.get("fulfills_exercise_uid")
            fulfills_exercise_uid = (
                (str(raw_exercise_uid).strip() or None if raw_exercise_uid else None)
                or frontmatter.get("exercise_uid")
                or None
            )

            # revision from frontmatter (default 1)
            revision_str = frontmatter.get("revision", "1")
            try:
                revision_number = int(revision_str)
            except ValueError:
                revision_number = 1

            submission_metadata: dict[str, Any] = {}
            if frontmatter.get("exercise_number"):
                submission_metadata["exercise_number"] = frontmatter["exercise_number"]
            if revision_number != 1:
                submission_metadata["revision_number"] = revision_number

            logger.info(
                f"Submission upload: {filename} ({len(file_content)} bytes, "
                f"exercise={fulfills_exercise_uid}, revision={revision_number})"
            )

            result = await submissions_service.submit_file(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.EXERCISE_SUBMISSION,
                processor_type=ProcessorType.HUMAN,
                metadata=submission_metadata,
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

        except Exception as e:  # safety-net: HTMX fragment error boundary
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
                    render_error_banner("Failed to load reports", str(result.error)),
                    id="submissions-grid-container",
                )

            reports = result.value or []
            return render_submissions_grid(reports)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading reports: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading reports", str(e)),
                id="submissions-grid-container",
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
                    Alert(
                        P(f"Failed to load submission: {result.error}"),
                        variant=AlertT.error,
                    ),
                    id="submission-info",
                )

            submission = result.value
            if not submission:
                return Div(
                    Alert(
                        P(f"Report {uid} not found"),
                        variant=AlertT.warning,
                    ),
                    id="submission-info",
                )
            return render_submission_detail(submission)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submission info: {e}", exc_info=True)
            return Div(
                Alert(
                    P(f"Error: {e}"),
                    variant=AlertT.error,
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

        except Exception as e:  # safety-net: HTMX fragment error boundary
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
                return Div(render_inline_error("Submission not found"), id="feedback-section")
            if sub_result.value.user_uid != user_uid:
                return Div(render_inline_error("Access denied"), id="feedback-section")

            if not teacher_review_service:
                return Div(
                    EmptyState(title="No feedback yet"),
                    id="feedback-section",
                )

            history_result = await teacher_review_service.get_report_history(uid)
            if history_result.is_error:
                logger.error(f"Error loading feedback for {uid}: {history_result.error}")
                return Div(
                    render_error_banner("Failed to load feedback", str(history_result.error)),
                    id="feedback-section",
                )
            items = history_result.value or []

            if not items:
                return Div(
                    H4("Feedback", cls="mb-4"),
                    EmptyState(title="No feedback yet"),
                    id="feedback-section",
                )

            return Div(
                H4("Feedback", cls="mb-4"),
                *[render_report_item(fb) for fb in items],
                id="feedback-section",
            )
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading feedback for {uid}: {e}", exc_info=True)
            return Div(
                render_error_banner("Error loading feedback", str(e)),
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
        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading exercise link for {uid}: {e}", exc_info=True)
            return Div(id="exercise-link")

    @rt("/submissions/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await submissions_service.get_submission(uid)
            if result.is_error:
                return render_inline_error("Report not found")

            submission = result.value
            return render_category_selector(submission)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return render_inline_error("Error loading category selector")

    @rt("/submissions/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await submissions_service.get_submission(uid)
            if result.is_error:
                return render_inline_error("Report not found")

            submission = result.value
            return render_tags_manager(submission)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return render_inline_error("Error loading tags manager")

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

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading shared users: {e}", exc_info=True)
            return render_inline_error("Error loading shared users")

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
                    ButtonLink(
                        "\u2190 Back to Submissions",
                        href="/submissions",
                        variant=ButtonT.ghost,
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
            active_page="submissions",
        )

    logger.info("Submissions UI routes created (/submit, /submissions, /submissions/{uid})")

    # Route order matters! Specific routes before parameterized routes.
    return [
        submit_page,  # /submit
        submissions_page,  # /submissions
        submissions_list,  # /submissions/list (HTMX)
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
