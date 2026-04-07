"""
GradeBook UI Routes — ExerciseSubmission Pages
===============================================

Routes for submitting work and viewing submission details.
Submission listing moved to Submissions (/submissions/history) — see workbench_routes.py.

Routes:
- GET /submit — File upload form (Submissions sidebar)
- GET /gradebook — Hub page (no sidebar, container navigation)
- GET /gradebook/mysubmissions — 301 redirect to /submissions/history
- GET /gradebook/{uid} — Submission detail page
- HTMX fragments: /upload, /grid,
  /gradebook/{uid}/{info,content,report,exercise,category-selector,tags-manager,shared-users}

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import (
    H4,
    Div,
    P,
    Span,
)
from starlette.datastructures import UploadFile

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.utils.logging import get_logger
from ui.buttons import ButtonLink, ButtonT
from ui.cards import Card, CardBody, CardHeader, CardTitle
from ui.feedback import Alert, AlertT, Badge, BadgeT
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.page_header import PageHeader
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
from ui.submissions.sharing import render_sharing_section

logger = get_logger("skuel.routes.submissions")


def _parse_md_frontmatter(content: bytes) -> dict[str, Any]:
    """Parse YAML frontmatter from a Markdown file's bytes.

    Delegates to core/utils/frontmatter.parse_frontmatter for robust
    YAML parsing. Returns empty dict on malformed/missing frontmatter.
    """
    from core.utils.frontmatter import parse_frontmatter

    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:  # safety-net: malformed bytes should not crash upload
        return {}
    frontmatter, _ = parse_frontmatter(text)
    return frontmatter


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
    orchestrator: Any,
) -> list[Any]:
    """Create /submit and /gradebook UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: SubmissionsOrchestrator for unified access to services
    """
    if orchestrator is None:
        raise RuntimeError("SubmissionsOrchestrator is required — check bootstrap wiring")

    # ========================================================================
    # SUBMIT PAGE (standalone — deep-linked from exercises)
    # ========================================================================

    @rt("/submit")
    async def submit_page(request: Request) -> Any:
        """Submit page: upload form with optional exercise selector."""
        user_uid = require_authenticated_user(request)

        assigned_exercises: list[Any] = []
        exercises_result = await orchestrator.get_student_exercises(user_uid)
        if not exercises_result.is_error and exercises_result.value:
            assigned_exercises = exercises_result.value

        selected_exercise_uid = request.query_params.get("exercise_uid")
        # PathStep context from navigation — passed through as hidden field so the
        # Interaction audit record captures where in the curriculum the student was.
        from_ps = request.query_params.get("from_ps") or None

        content = Div(
            PageHeader("Submit", subtitle="Upload your completed exercise worksheet"),
            render_upload_form(
                assigned_exercises,
                selected_exercise_uid=selected_exercise_uid,
                from_ps=from_ps,
            ),
            upload_form_script(),
        )
        from ui.workbench.nav import render_submissions_sidebar_page

        return await render_submissions_sidebar_page(
            content=content,
            active="submit",
            request=request,
        )

    # ========================================================================
    # GRADEBOOK PAGE — merges yours + browse
    # ========================================================================

    @rt("/gradebook")
    async def gradebook_hub(request: Request) -> Any:
        """GradeBook hub — entry point with container navigation, no sidebar."""
        require_authenticated_user(request)
        from ui.gradebook.hub import GradeBookHub
        from ui.layouts.base_page import BasePage

        return await BasePage(
            content=GradeBookHub(),
            title="GradeBook",
            request=request,
            active_page="gradebook",
        )

    @rt("/gradebook/mysubmissions")
    async def gradebook_mysubmissions_redirect(request: Request) -> Any:
        """301 redirect — submissions list moved to Submissions."""
        from starlette.responses import RedirectResponse

        return RedirectResponse("/submissions/history", status_code=301)

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/gradebook/upload")
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
            frontmatter: dict[str, Any] = {}
            if filename.endswith(".md"):
                frontmatter = _parse_md_frontmatter(file_content)

            # exercise_uid: form selector wins; fallback to frontmatter
            raw_exercise_uid = form.get("fulfills_exercise_uid")
            fm_exercise_uid = frontmatter.get("exercise_uid")
            fulfills_exercise_uid = (
                (str(raw_exercise_uid).strip() or None if raw_exercise_uid else None)
                or (str(fm_exercise_uid) if fm_exercise_uid else None)
                or None
            )

            # revision from frontmatter (default 1)
            try:
                revision_number = int(frontmatter.get("revision", 1))
            except (ValueError, TypeError):
                revision_number = 1

            submission_metadata: dict[str, Any] = {}
            if frontmatter.get("exercise_number"):
                submission_metadata["exercise_number"] = str(frontmatter["exercise_number"])
            if revision_number != 1:
                submission_metadata["revision_number"] = revision_number

            logger.info(
                f"Submission upload: {filename} ({len(file_content)} bytes, "
                f"exercise={fulfills_exercise_uid}, revision={revision_number})"
            )

            # Capture learning context for Interaction audit record (best-effort).
            # Prefer from_ps (explicit navigation context) over the nondeterministic
            # next(iter(current_ps_uids)) that breaks when multiple PathSteps are IN_PROGRESS.
            context_path_step_uid: str | None = (
                str(form.get("from_ps")).strip() or None if form.get("from_ps") else None
            )
            context_learning_path_uid: str | None = None
            ctx_result = await orchestrator.build_user_context(user_uid)
            if ctx_result.is_ok:
                ctx = ctx_result.value
                if not context_path_step_uid:
                    context_path_step_uid = next(iter(ctx.current_ps_uids), None)
                context_learning_path_uid = ctx.current_learning_path_uid

            result = await orchestrator.process_submission(
                file_content=file_content,
                original_filename=filename,
                user_uid=user_uid,
                entity_type=EntityType.EXERCISE_SUBMISSION,
                processor_type=ProcessorType.HUMAN,
                metadata=submission_metadata,
                fulfills_exercise_uid=fulfills_exercise_uid,
                context_path_step_uid=context_path_step_uid,
                context_learning_path_uid=context_learning_path_uid,
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

            result = await orchestrator.list_submissions(**kwargs)

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

    @rt("/gradebook/{uid}/info")
    async def get_submission_info(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission detail info."""
        try:
            result = await orchestrator.get_submission(uid)

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

    @rt("/gradebook/{uid}/content")
    async def get_submission_content(request: Request, uid: str) -> Any:
        """HTMX endpoint for loading submission processed content."""
        try:
            result = await orchestrator.get_submission(uid)

            if result.is_error or not result.value:
                return render_processed_content(None, False)

            submission = result.value
            content = submission.processed_content if submission else None
            return render_processed_content(content, bool(content))

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading submission content: {e}", exc_info=True)
            return render_processed_content(None, False)

    @rt("/gradebook/{uid}/report")
    async def get_submission_report(request: Request, uid: str) -> Any:
        """HTMX endpoint: report received on this submission."""
        from ui.patterns.report_item import render_report_item

        try:
            user_uid = require_authenticated_user(request)

            sub_result = await orchestrator.get_submission(uid)
            if sub_result.is_error or not sub_result.value:
                return Div(render_inline_error("Submission not found"), id="feedback-section")
            if sub_result.value.user_uid != user_uid:
                return Div(render_inline_error("Access denied"), id="feedback-section")

            history_result = await orchestrator.get_report_history(uid)
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

    @rt("/gradebook/{uid}/exercise")
    async def get_submission_exercise(request: Request, uid: str) -> Any:
        """HTMX endpoint: which exercise this submission fulfills."""
        try:
            require_authenticated_user(request)

            result = await orchestrator.get_exercise_for_submission(uid)

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

    @rt("/gradebook/{uid}/category-selector")
    async def get_category_selector(request: Request, uid: str) -> Any:
        """HTMX endpoint for category selector."""
        try:
            result = await orchestrator.get_submission(uid)
            if result.is_error:
                return render_inline_error("Report not found")

            submission = result.value
            return render_category_selector(submission)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading category selector: {e}", exc_info=True)
            return render_inline_error("Error loading category selector")

    @rt("/gradebook/{uid}/tags-manager")
    async def get_tags_manager(request: Request, uid: str) -> Any:
        """HTMX endpoint for tags manager."""
        try:
            result = await orchestrator.get_submission(uid)
            if result.is_error:
                return render_inline_error("Report not found")

            submission = result.value
            return render_tags_manager(submission)

        except Exception as e:  # safety-net: HTMX fragment error boundary
            logger.error(f"Error loading tags manager: {e}", exc_info=True)
            return render_inline_error("Error loading tags manager")

    @rt("/gradebook/{uid}/shared-users")
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

    @rt("/gradebook/{uid}")
    async def submission_detail(request: Request, uid: str) -> Any:
        """Submission detail view with HTMX-loaded sections."""
        user_uid = require_authenticated_user(request)

        submission_result = await orchestrator.get_submission(uid)
        is_owner = False
        if not submission_result.is_error and submission_result.value is not None:
            is_owner = submission_result.value.user_uid == user_uid

        detail_card = Card(
            CardHeader(CardTitle("Submission Details")),
            CardBody(
                Div(
                    P("Loading submission details...", cls="text-center text-muted-foreground"),
                    id="submission-info",
                    cls="mb-4",
                    **{
                        "hx-get": f"/gradebook/{uid}/info",
                        "hx-trigger": "load",
                        "hx-swap": "outerHTML",
                    },
                ),
                Div(
                    id="exercise-link",
                    **{
                        "hx-get": f"/gradebook/{uid}/exercise",
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
                            "hx-get": f"/gradebook/{uid}/content",
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
                        "hx-get": f"/gradebook/{uid}/report",
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
                        "\u2190 Back to Submission History",
                        href="/submissions/history",
                        variant=ButtonT.ghost,
                    ),
                    cls="mt-4",
                ),
            ),
            cls="bg-background shadow-sm",
        )

        content = Div(
            PageHeader("Submission Details", subtitle=f"UID: {uid}"),
            detail_card,
        )

        return await render_gradebook_sidebar_page(
            content=content,
            active="submissions",
            request=request,
        )

    logger.info("GradeBook UI routes created (/submit, /gradebook, /gradebook/{uid})")

    # Route order matters! Specific routes before parameterized routes.
    return [
        submit_page,  # /submit
        gradebook_hub,  # /gradebook (hub page)
        gradebook_mysubmissions_redirect,  # /gradebook/mysubmissions → 301
        upload_submission,  # /gradebook/upload (HTMX POST)
        get_submissions_grid,  # /grid (HTMX GET)
        get_submission_info,  # /gradebook/{uid}/info
        get_submission_content,  # /gradebook/{uid}/content
        get_submission_report,  # /gradebook/{uid}/report
        get_submission_exercise,  # /gradebook/{uid}/exercise
        get_category_selector,  # /gradebook/{uid}/category-selector
        get_tags_manager,  # /gradebook/{uid}/tags-manager
        get_shared_users_ui,  # /gradebook/{uid}/shared-users
        submission_detail,  # /gradebook/{uid} (catch-all — LAST)
    ]
