"""
Activity Reports UI Routes — ActivityReport Pages
===================================================

Routes for viewing and requesting activity reports. The list surface is the
GradeBook's conditional "Activity reports" group (/gradebook, arc 2 C1) —
this file keeps the detail view, the request form, and the hub preview.

Routes:
- GET /activity-reports/latest — The sidebar's Reports door: redirect to the newest
  report the user OWNS, or to the request form when there is none
- GET /activity-reports/detail — Activity report detail view
- GET /activity-reports/detail/content — HTMX fragment: detail body
- GET /activity-reports/md?uid= — Download own report as Markdown
- GET /submit-activity-report — On-demand activity report request form
- POST /api/reports/progress/generate — Generate a report now (answers the request
  form's HTMX post with a fragment; a cooldown refusal renders inline)
- POST /api/activity-reports/annotate — Save commentary/revision on own report (fragment)
- GET /reports/progress-list — HTMX fragment: progress reports (request form page)
- GET /api/gradebook/activity-reports/preview — HTMX hub preview block

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    Div,
    P,
    Span,
)
from starlette.responses import RedirectResponse, Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler, ui_boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from adapters.inbound.form_helpers import parse_form_body
from adapters.inbound.route_factories import parse_date_query_param
from adapters.outbound.activity_report_renderer import (
    activity_report_filename,
    render_activity_report_md,
)
from core.models.entity_requests import AnnotationFormRequest, ProgressReportGenerateRequest
from core.utils.logging import get_logger
from core.utils.report_periods import (
    UnknownReportPeriodError,
    report_period_token,
    resolve_report_period,
)
from core.utils.result_simplified import ErrorCategory, Errors, Result
from core.utils.text_truncation import truncate_to_budget
from ui.gradebook.nav import render_gradebook_sidebar_page
from ui.learning_loop.report import (
    render_activity_report_detail,
    render_progress_report_list,
)
from ui.patterns.error_banner import render_error_banner
from ui.patterns.generate_report import (
    render_activity_report_request_card,
    render_period_report_prompt,
    render_recent_reports_section,
)
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.report_protocols import ProgressReportOperations

logger = get_logger("skuel.routes.activity_reports")

# The two report forms swap these fragments into their status slots
# (#generate-status, #annotation-status); a refusal the user can act on
# (cooldown, a mode without its text) renders here too — HTMX leaves a 4xx
# body unswapped, which would show the user nothing.
_INLINE_ERROR_CATEGORIES = frozenset({ErrorCategory.VALIDATION, ErrorCategory.BUSINESS})


def _status_note(message: str, *, ok: bool) -> "FT":
    tone = "text-success" if ok else "text-warning"
    return P(message, cls=f"text-sm {tone}", role="status")


def _progress_list_refresh() -> Div:
    """Out-of-band re-fetch of the recent-reports list after a generation."""
    return Div(
        Span("Refreshing recent reports…", cls="sr-only"),
        id="progress-list",
        hx_get="/reports/progress-list",
        hx_trigger="load",
        hx_swap="outerHTML",
        hx_swap_oob="true",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_activity_reports_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    orchestrator: Any = None,
    progress_generator: "ProgressReportOperations | None" = None,
) -> list[Any]:
    """Create activity-report detail/request/generate/annotate/download routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: UserEntryOrchestrator (owner-scoped report reads + annotate)
        progress_generator: ProgressReportGenerator — the on-demand producer
    """

    # ========================================================================
    # SUBMIT ACTIVITY REPORT — on-demand activity report request
    # ========================================================================

    @rt("/submit-activity-report")
    def submit_activity_report_page(request: Request) -> Any:
        """Submit a request to generate an activity report."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Submit Activity Report Request",
                subtitle="Request an on-demand activity report across your domains",
            ),
            render_activity_report_request_card(),
            render_recent_reports_section(),
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="submit-activity-report",
            request=request,
        )

    # ========================================================================
    # LATEST REPORT — the calendar/Today sidebar's Reports door
    # ========================================================================

    @rt("/activity-reports/latest")
    async def activity_report_latest(request: Request) -> RedirectResponse:
        """Redirect to the newest report the user owns, or to the request form.

        Owner-scoped on purpose: the history read is subject-scoped and would
        offer an admin-authored report the owner-scoped detail then refuses.
        A failed read still lands somewhere useful — the request form.
        """
        user_uid = require_authenticated_user(request)
        latest = await orchestrator.get_latest_activity_report(user_uid)
        if latest.is_error:
            logger.warning(
                "activity-reports/latest read failed for user=%s: %s",
                user_uid,
                latest.expect_error().message,
            )
            return RedirectResponse("/submit-activity-report", status_code=302)
        if latest.value is None:
            return RedirectResponse("/submit-activity-report", status_code=302)
        return RedirectResponse(f"/activity-reports/detail?uid={latest.value.uid}", status_code=302)

    # ========================================================================
    # PERIOD DOOR — the calendar's "Report for September" / "Report for W37"
    # ========================================================================

    def _period_prompt_page(
        request: Request, token: str, *, note: str | None = None
    ) -> Response | FT:
        """The period's "generate" state, or 400 for a token no vocabulary names."""
        try:
            period = resolve_report_period(token, datetime.now())
        except UnknownReportPeriodError:
            return Response("Unknown report period", status_code=400)
        return render_gradebook_sidebar_page(
            content=Div(
                PageHeader(
                    f"Report for {period.label}",
                    subtitle="A report aligned to the calendar period, reused while it stands",
                ),
                render_period_report_prompt(
                    token=token,
                    label=period.label,
                    is_closed=period.is_closed(datetime.now()),
                    note=note,
                ),
            ),
            active="submit-activity-report",
            request=request,
        )

    @rt("/activity-reports/for", methods=["GET"])
    async def activity_report_for_period(request: Request) -> Any:
        """Lookup half of the period door: ``?kind=monthly|weekly&date=YYYY-MM-DD``.

        Redirects to the period's reusable report — the newest one the user
        owns for the token, unless the period has closed and that report is
        partial (stale, superseded by the final one) — or renders the
        "generate" state. A GET mints nothing: the generation is the POST
        below, so a prefetch can never create a report.
        """
        user_uid = require_authenticated_user(request)
        kind = request.query_params.get("kind", "").strip()
        ref_date = parse_date_query_param(request.query_params, "date")
        if ref_date is None:
            return Response("Invalid or missing date", status_code=400)
        try:
            token = report_period_token(kind, ref_date)
        except UnknownReportPeriodError:
            return Response("Unknown report period kind", status_code=400)
        found = await orchestrator.find_activity_report_for_period(user_uid, token)
        if found.is_error:
            logger.warning(
                "activity-reports/for lookup failed for user=%s period=%s: %s",
                user_uid,
                token,
                found.expect_error().message,
            )
            return _period_prompt_page(
                request, token, note="Could not look up the period's report; generate it below."
            )
        if found.value is not None:
            return RedirectResponse(
                f"/activity-reports/detail?uid={found.value.uid}", status_code=302
            )
        return _period_prompt_page(request, token)

    @rt("/activity-reports/for", methods=["POST"])
    @csrf_protected
    async def generate_activity_report_for_period(request: Request) -> Any:
        """Generation half of the period door: mint the period's report.

        Url-encoded ``time_period``; a token outside the vocabulary is 400. A
        refusal the user can act on (the per-period cooldown) re-renders the
        prompt with the reason; success lands on the new report.
        """
        user_uid = require_authenticated_user(request)
        if progress_generator is None:
            return Response("Activity report generator unavailable", status_code=503)
        form = await request.form()
        token = str(form.get("time_period", "")).strip()
        try:
            resolve_report_period(token, datetime.now())
        except UnknownReportPeriodError:
            return Response("Unknown report period", status_code=400)
        result = await progress_generator.generate(user_uid=user_uid, time_period=token)
        if result.is_error:
            error = result.expect_error()
            if error.category in _INLINE_ERROR_CATEGORIES:
                return _period_prompt_page(request, token, note=error.message)
            logger.error(
                "activity-reports/for generation failed for user=%s period=%s: %s",
                user_uid,
                token,
                error.message,
            )
            return Response("Could not generate the report", status_code=500)
        return RedirectResponse(f"/activity-reports/detail?uid={result.value.uid}", status_code=302)

    # ========================================================================
    # ACTIVITY REPORT DETAIL PAGE
    # ========================================================================

    @rt("/activity-reports/detail")
    def activity_report_detail(request: Request) -> Any:
        """Activity report detail — shell only, content loads via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()
        if not uid:
            return render_gradebook_sidebar_page(
                content=Div(render_error_banner("Report UID is required")),
                active="gradebook",
                request=request,
            )
        content = Div(
            content_loading_placeholder(
                f"/activity-reports/detail/content?uid={uid}",
                "activity-report-detail-content",
            )
        )
        return render_gradebook_sidebar_page(
            content=content,
            active="gradebook",
            request=request,
        )

    @rt("/activity-reports/detail/content")
    async def activity_report_detail_content(request: Request) -> Any:
        """HTMX fragment: activity report detail body."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()
        if not uid:
            return Div(
                render_error_banner("Report UID is required"),
                id="activity-report-detail-content",
            )
        if not orchestrator:
            return Div(
                render_error_banner("Activity report orchestrator unavailable"),
                id="activity-report-detail-content",
            )
        report_result = await orchestrator.get_activity_report(uid, user_uid)
        if report_result.is_error:
            return Div(
                render_error_banner("Report not found", str(report_result.error)),
                id="activity-report-detail-content",
            )
        report = report_result.value
        metadata = getattr(report, "metadata", None) or {}
        snapshot = metadata.get("snapshot") if isinstance(metadata, dict) else None
        intelligence = metadata.get("intelligence") if isinstance(metadata, dict) else None
        comparison = metadata.get("comparison") if isinstance(metadata, dict) else None
        return Div(
            render_activity_report_detail(
                report, snapshot=snapshot, intelligence=intelligence, comparison=comparison
            ),
            id="activity-report-detail-content",
        )

    # ========================================================================
    # PRODUCERS — generate now, annotate, download
    # ========================================================================

    @rt("/api/reports/progress/generate", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def generate_activity_report(request: Request) -> Result["FT"]:
        """Generate a report for the signed-in user now.

        Answers the request form's url-encoded post (``time_period``, ``depth``)
        with a fragment for ``#generate-status``: a link to the new report plus
        an out-of-band refresh of the recent-reports list. The generator's
        cooldown refusal (a report within the last hour) renders inline; a body
        outside the period/depth vocabulary is 400; anything else propagates.
        """
        user_uid = require_authenticated_user(request)
        if progress_generator is None:
            return Result.fail(Errors.system("Activity report generator unavailable"))
        parsed = await parse_form_body(request, ProgressReportGenerateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        result = await progress_generator.generate(
            user_uid=user_uid,
            time_period=req.time_period,
            domains=req.domains or None,
            depth=req.depth,
            include_insights=req.include_insights,
        )
        if result.is_error:
            error = result.expect_error()
            if error.category in _INLINE_ERROR_CATEGORIES:
                return Result.ok(_status_note(error.message, ok=False))
            return Result.fail(result)
        report = result.value
        return Result.ok(
            Div(
                _status_note("Report generated.", ok=True),
                ButtonLink(
                    "Open report",
                    href=f"/activity-reports/detail?uid={report.uid}",
                    size="sm",
                ),
                _progress_list_refresh(),
                cls="flex items-center gap-3",
            )
        )

    @rt("/api/activity-reports/annotate", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def annotate_activity_report(request: Request) -> Result["FT"]:
        """Save the owner's commentary or replacement text on one of their reports.

        Answers the detail page's url-encoded post (``uid``, ``annotation_mode``,
        ``annotation_text``) with a fragment for ``#annotation-status``; the one
        text field lands in the field the chosen mode stores. A mode without its
        text renders inline; a report the user does not own is not found (404),
        as every owner-scoped read.
        """
        user_uid = require_authenticated_user(request)
        if orchestrator is None:
            return Result.fail(Errors.system("Activity report orchestrator unavailable"))
        parsed = await parse_form_body(request, AnnotationFormRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value.to_save_request()
        result = await orchestrator.annotate_activity_report(
            req.uid,
            user_uid,
            req.annotation_mode,
            user_annotation=req.user_annotation,
            user_revision=req.user_revision,
        )
        if result.is_error:
            error = result.expect_error()
            if error.category in _INLINE_ERROR_CATEGORIES:
                return Result.ok(_status_note(error.message, ok=False))
            return Result.fail(result)
        return Result.ok(_status_note("Saved.", ok=True))

    @rt("/activity-reports/md")
    async def download_activity_report_md(request: Request) -> Response:
        """Download one of the user's reports as a Markdown file.

        Owner-scoped through the orchestrator's ``get_activity_report`` — a
        foreign or unknown uid is "not found", never rendered; a read that
        fails for any other reason is reported as unavailable, not as absent.
        """
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "").strip()
        not_found = Response("Report not found", status_code=404, media_type="text/plain")
        if not uid or orchestrator is None:
            return not_found
        result = await orchestrator.get_activity_report(uid, user_uid)
        if result.is_error:
            error = result.expect_error()
            if error.category == ErrorCategory.NOT_FOUND:
                return not_found
            logger.error("activity-report download failed for uid=%s: %s", uid, error.message)
            return Response("Report unavailable", status_code=503, media_type="text/plain")
        if not result.value:
            return not_found
        report = result.value
        return Response(
            content=render_activity_report_md(report),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{activity_report_filename(report)}"'
            },
        )

    # ========================================================================
    # HTMX ENDPOINTS
    # ========================================================================

    @rt("/reports/progress-list")
    @ui_boundary_handler("Error loading progress reports", fragment_id="progress-list")
    async def progress_list_fragment(request: Request) -> Any:
        """HTMX fragment: progress reports."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return Div(
                render_error_banner("Submissions orchestrator unavailable"),
                id="progress-list",
            )
        result = await orchestrator.get_activity_report_history(user_uid, limit=10)
        if result.is_error:
            logger.error(f"Error loading progress reports: {result.error}")
            return Div(
                render_error_banner("Failed to load progress reports", str(result.error)),
                id="progress-list",
            )
        return render_progress_report_list(result.value or [])

    # ========================================================================
    # HUB PREVIEW ENDPOINT (HTMX lazy-loaded from /profile Reports tab)
    # ========================================================================

    @rt("/api/gradebook/activity-reports/preview")
    async def activity_reports_preview(request: Request) -> Any:
        """HTMX fragment: 3 most recent activity reports for hub preview."""
        user_uid = require_authenticated_user(request)
        if not orchestrator:
            return HubPreviewEmpty("activity reports")
        result = await orchestrator.get_activity_report_history(user_uid, limit=3)
        if result.is_error:
            return HubPreviewEmpty("activity reports")
        reports = result.value or []
        if not reports:
            return HubPreviewEmpty("activity reports")
        cards = []
        for report in reports[:3]:
            uid = getattr(report, "uid", "") or ""
            title = str(getattr(report, "title", None) or uid or "Report")
            period = getattr(report, "time_period", None) or ""
            badge = (
                Span(period, cls="text-10 font-medium text-muted-foreground") if period else None
            )
            content = getattr(report, "processed_content", None) or ""
            href = f"/activity-reports/detail?uid={uid}" if uid else "/gradebook"
            cards.append(
                HubPreviewCard(
                    title=title,
                    href=href,
                    badge=badge,
                    description=truncate_to_budget(content, 160) if content else None,
                )
            )
        return HubPreviewGrid(cards)

    logger.info(
        "Activity Reports UI routes created "
        "(/activity-reports/detail, /submit-activity-report, generate/annotate/md + hub preview)"
    )

    return [
        submit_activity_report_page,
        activity_report_detail,
        activity_report_detail_content,
        generate_activity_report,
        annotate_activity_report,
        download_activity_report_md,
        progress_list_fragment,
    ]
