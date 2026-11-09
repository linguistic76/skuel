"""
Activity Review UI Routes — Admin Human Feedback on Activity Domains
=====================================================================

Admin-facing UI for reviewing a user's Activity Domain data and writing
structured feedback. All HTML construction delegated to ui/activity_review/.

Routes:
- GET /activity-review           — redirect to queue
- GET /activity-review/queue     — pending review requests (admin-only)
- GET /activity-review/new       — admin review form (admin-only)
- GET /activity-review/snapshot-fragment  — HTMX domain snapshot fragment
- POST /activity-review/submit-feedback   — HTMX feedback submission fragment

A learner's request (``POST /api/activity-reviews/request``, activity_reports_ui.py)
lands in the queue; the queue card opens the form with the request, and writing
the review closes it.

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator

from fasthtml.common import FT, H3, Div, FtResponse, Input, P
from starlette.responses import RedirectResponse

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import ui_boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from adapters.inbound.form_helpers import parse_body
from adapters.inbound.route_factories.route_helpers import refuse_unavailable
from core.config.settings import get_settings
from core.models.entity_requests import ActivityFeedbackSubmitRequest
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import ErrorContext
from ui.activity_review import (
    activity_review_sidebar_page,
    render_feedback_form,
    render_queue_item,
    render_snapshot_domain_card,
    render_snapshot_form,
)
from ui.activity_review.types import DOMAIN_CHOICES
from ui.components import Card, CardBody, CardHeader, CardTitle
from ui.feedback import Alert, AlertT
from ui.layouts.base_page import HtmlDocument
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.activity_review.ui")


def _queue_page(request: Request, content: FT) -> HtmlDocument:
    """The review queue's shell, for its queue, its failed read and its crash alike."""
    return activity_review_sidebar_page("queue", content, request, page_title="Review Queue")


def _alert(*lines: FT | None, ok: bool) -> FT:
    """The feedback form's status slot: one alert."""
    return Div(Alert(*lines, variant=AlertT.success if ok else AlertT.error))


def _refuse_feedback(error: ErrorContext, message: str) -> FtResponse:
    """A refused review, rendered into the status slot at the status it earns (400 / 5xx)."""
    return refuse_unavailable(_alert(P(message, cls="mb-0"), ok=False), error)


#: What the form needs, said once: the parse refusal's message.
_FEEDBACK_UNREADABLE = (
    "Load a user's snapshot and write feedback before submitting; the period must be "
    "one the form offers."
)


def create_activity_review_ui_routes(
    rt: RouteDecorator,
    orchestrator: ActivityReviewOrchestrator,
) -> None:
    """Create Activity Review admin UI routes."""
    logger.info("Creating Activity Review UI routes")

    get_user_service = make_service_getter(orchestrator.user_service)

    @rt("/activity-review")
    def activity_review_landing(
        request: Request,
    ) -> RedirectResponse:
        """Redirect to queue."""
        return RedirectResponse("/activity-review/queue", status_code=303)

    @rt("/activity-review/queue")
    @require_admin(get_user_service)
    @ui_boundary_handler("Could not load the review queue", page=_queue_page)
    async def activity_review_queue_page(
        request: Request, current_user: Any = None
    ) -> HtmlDocument:
        """Admin queue: pending review requests from users.

        A failed read is a banner in the queue's shell, never an empty queue.
        """
        result = await orchestrator.get_pending_reviews(UserUID(current_user.uid))
        if result.is_error:
            return _queue_page(
                request,
                render_error_banner(
                    "Could not load the review queue",
                    technical_details=result.expect_error().message,
                    show_details=get_settings().application.debug,
                ),
            )

        pending = result.value or []
        if pending:
            queue_content: Any = Div(*[render_queue_item(item) for item in pending])
        else:
            queue_content = EmptyState(
                title="No pending review requests",
                description=(
                    "A learner asks for one from Request activity report, "
                    "the button on their GradeBook."
                ),
            )

        content = Div(
            PageHeader("Review Queue", subtitle="Pending activity review requests from users"),
            Card(
                CardHeader(CardTitle("Pending Requests")),
                CardBody(queue_content),
            ),
        )

        return _queue_page(request, content)

    @rt("/activity-review/new")
    @require_admin(get_user_service)
    def activity_review_new_page(
        request: Request,
        current_user: Any = None,
        subject_uid: str = "",
        time_period: str = "7d",
        review_request_uid: str = "",
        domains: list[str] | None = None,
    ) -> HtmlDocument:
        """Admin review form: load snapshot, write feedback, submit.

        Opened from a queue card, it carries the learner's request (its period,
        its domains and its uid, so submitting closes it).
        """
        snapshot_display = Div(
            P(
                'Enter a user UID and click "Load Snapshot" to preview their activity data.',
                cls="text-center text-muted-foreground py-6",
            ),
            id="snapshot-display",
        )

        content = Div(
            PageHeader(
                "New Activity Review",
                subtitle="Review a user's Activity Domain data and write feedback",
            ),
            render_snapshot_form(subject_uid, time_period, domains),
            snapshot_display,
            render_feedback_form(subject_uid, time_period, review_request_uid),
        )

        return activity_review_sidebar_page("new", content, request, page_title="New Review")

    @rt("/activity-review/snapshot-fragment")
    @require_admin(get_user_service)
    async def activity_review_snapshot_fragment(
        request: Request,
        current_user: Any = None,
        subject_uid: str = "",
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> FT:
        """HTMX fragment: load and display activity snapshot for admin review.

        Carries the snapshot itself as a hidden ``snapshot_context`` field, which the
        feedback form posts with the review; a failed load carries none.
        """
        if not subject_uid:
            return render_inline_error("Please enter a user UID")

        admin_uid = UserUID(current_user.uid)
        ctx_result = await orchestrator.build_rich_context(UserUID(subject_uid), window=time_period)
        if ctx_result.is_error:
            return render_inline_error(
                f"Could not build the context: {ctx_result.expect_error().message}"
            )
        result = await orchestrator.create_snapshot(
            context=ctx_result.value,
            admin_uid=admin_uid,
            time_period=time_period,
            domains=domains,
        )
        if result.is_error:
            return render_inline_error(f"Could not load snapshot: {result.expect_error().message}")

        snapshot = result.value or {}
        sections = snapshot.get("domains") or {}
        domain_cards = [
            render_snapshot_domain_card(domain_name, sections.get(domain_name))
            for domain_name in domains or [d for d, _ in DOMAIN_CHOICES]
        ]

        return Div(
            H3(
                f"Activity Snapshot: {subject_uid} — {time_period}",
                cls="font-semibold mb-4",
            ),
            *domain_cards,
            # A node value the encoder does not know (a driver temporal) reads as its text.
            Input(
                type="hidden",
                name="snapshot_context",
                id="feedback-snapshot-context",
                value=json.dumps(snapshot, default=str),
            ),
        )

    @rt("/activity-review/submit-feedback", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def activity_review_submit_feedback(
        request: Request, current_user: Any = None
    ) -> FT | FtResponse:
        """HTMX fragment: admin submits written activity feedback (``ActivityFeedbackSubmitRequest``).

        A body the model refuses, an unknown subject, a snapshot of another user and a
        request no longer pending are refused at 400; a failed write at its own
        status. Each refusal renders into the form's status slot.
        """
        admin_uid = UserUID(current_user.uid)
        parsed = await parse_body(request, ActivityFeedbackSubmitRequest)
        if parsed.is_error:
            return _refuse_feedback(parsed.expect_error(), _FEEDBACK_UNREADABLE)
        review = parsed.value

        result = await orchestrator.submit_report(
            admin_uid=admin_uid,
            subject_uid=UserUID(review.subject_uid),
            feedback_text=review.feedback_text,
            time_period=review.time_period,
            domains=list(review.domains) if review.domains else None,
            snapshot_context=review.snapshot_context,
            review_request_uid=review.review_request_uid,
        )
        if result.is_error:
            error = result.expect_error()
            return _refuse_feedback(error, f"Not sent: {error.message}")

        # The report is the subject's now (Submit & Share arc R11) and the admin has no
        # read-back of it (ADR-042), so the confirmation echoes what was sent
        # and to whom — the one place the admin sees it again.
        submitted = result.value
        closed_line: FT | None = None
        if submitted.request_closed is True:
            closed_line = P(
                "Their review request is answered and leaves the queue.", cls="mb-0 text-sm"
            )
        elif submitted.request_closed is False:
            closed_line = P(
                "Their review request could not be closed; it is still in the queue.",
                cls="mb-0 text-sm font-semibold",
            )
        return _alert(
            P(
                f"Report sent to {review.subject_uid} (uid: {submitted.report.uid}).",
                cls="mb-0 font-semibold",
            ),
            P(
                f"Period {review.time_period}. They own it, and their bell will tell them; "
                "you have no read-back of it.",
                cls="mb-0 text-sm",
            ),
            closed_line,
            P(review.feedback_text, cls="mb-0 mt-2 text-sm whitespace-pre-wrap"),
            ok=True,
        )


__all__ = ["create_activity_review_ui_routes"]
