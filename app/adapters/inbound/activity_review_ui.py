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

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator

from fasthtml.common import H3, Div, P
from starlette.responses import RedirectResponse

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
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
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_inline_error
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.activity_review.ui")


def create_activity_review_ui_routes(
    _app: Any,
    rt: Any,
    orchestrator: "ActivityReviewOrchestrator",
) -> list[Any]:
    """Create Activity Review admin UI routes."""
    logger.info("Creating Activity Review UI routes")

    get_user_service = make_service_getter(orchestrator.user_service)

    @rt("/activity-review")
    def activity_review_landing(
        request: Request,
    ) -> Any:
        """Redirect to queue."""
        return RedirectResponse("/activity-review/queue", status_code=303)

    @rt("/activity-review/queue")
    @require_admin(get_user_service)
    async def activity_review_queue_page(request: Request, current_user: Any = None) -> Any:
        """Admin queue: pending review requests from users."""
        _not_found = object()
        _uid_val = getattr(current_user, "uid", _not_found)
        admin_uid = UserUID(str(current_user) if _uid_val is _not_found else str(_uid_val))

        pending: list[Any] = []
        try:
            result = await orchestrator.get_pending_reviews(admin_uid)
            if not result.is_error:
                pending = result.value or []
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error loading review queue: {e}", exc_info=True)

        if pending:
            queue_content: Any = Div(*[render_queue_item(item) for item in pending])
        else:
            queue_content = EmptyState(
                title="No pending review requests",
                description="Users can request an activity review from their feedback page.",
            )

        content = Div(
            PageHeader("Review Queue", subtitle="Pending activity review requests from users"),
            Card(
                CardHeader(CardTitle("Pending Requests")),
                CardBody(queue_content),
            ),
        )

        return await activity_review_sidebar_page(
            "queue", content, request, page_title="Review Queue"
        )

    @rt("/activity-review/new")
    @require_admin(get_user_service)
    async def activity_review_new_page(
        request: Request,
        current_user: Any,
        subject_uid: str = "",
        time_period: str = "7d",
    ) -> Any:
        """Admin review form: load snapshot, write feedback, submit."""
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
            render_snapshot_form(subject_uid, time_period),
            snapshot_display,
            render_feedback_form(subject_uid, time_period),
        )

        return await activity_review_sidebar_page("new", content, request, page_title="New Review")

    @rt("/activity-review/snapshot-fragment")
    @require_admin(get_user_service)
    async def activity_review_snapshot_fragment(
        request: Request,
        current_user: Any,
        subject_uid: str = "",
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> Any:
        """HTMX fragment: load and display activity snapshot for admin review."""
        if not subject_uid:
            return render_inline_error("Please enter a user UID")

        try:
            ctx_result = await orchestrator.build_rich_context(
                UserUID(subject_uid), window=time_period
            )
            if ctx_result.is_error:
                return Div(
                    P(f"Failed to build context: {ctx_result.error}", cls="text-error text-sm")
                )

            result = await orchestrator.create_snapshot(
                context=ctx_result.value,
                time_period=time_period,
                domains=domains,
            )
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error creating snapshot for {subject_uid}: {e}", exc_info=True)
            return Div(
                P(f"Error loading snapshot: {e}", cls="text-error text-sm"),
            )

        if result.is_error:
            return Div(
                P(
                    f"Could not load snapshot: {result.error.message if result.error else 'Unknown error'}",
                    cls="text-error text-sm",
                ),
            )

        snapshot = result.value or {}

        domain_cards = []
        for domain_name in domains or [d for d, _ in DOMAIN_CHOICES]:
            items = snapshot.get(domain_name) or []
            domain_cards.append(render_snapshot_domain_card(domain_name, items))

        return Div(
            H3(
                f"Activity Snapshot: {subject_uid} — {time_period}",
                cls="font-semibold mb-4",
            ),
            *domain_cards,
        )

    @rt("/activity-review/submit-feedback", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def activity_review_submit_feedback(
        request: Request,
        current_user: Any,
        subject_uid: str = "",
        feedback_text: str = "",
        time_period: str = "7d",
        domains: list[str] | None = None,
    ) -> Any:
        """HTMX fragment: admin submits written activity feedback."""
        _missing = object()
        admin_uid_val = getattr(current_user, "uid", _missing)
        admin_uid = UserUID(
            str(admin_uid_val) if admin_uid_val is not _missing else str(current_user)
        )

        if not subject_uid or not feedback_text:
            return Div(
                Alert(
                    P("User UID and feedback text are required.", cls="mb-0"),
                    variant=AlertT.error,
                ),
            )

        try:
            result = await orchestrator.submit_report(
                admin_uid=admin_uid,
                subject_uid=UserUID(subject_uid),
                feedback_text=feedback_text,
                time_period=time_period,
                domains=domains,
            )
        except Exception as e:  # safety-net: HTTP error boundary
            logger.error(f"Error submitting activity feedback: {e}", exc_info=True)
            return Div(
                Alert(
                    P(f"Error submitting feedback: {e}", cls="mb-0"),
                    variant=AlertT.error,
                ),
            )

        if result.is_error:
            return Div(
                Alert(
                    P(
                        f"Failed: {result.error.message if result.error else 'Unknown error'}",
                        cls="mb-0",
                    ),
                    variant=AlertT.error,
                ),
            )

        feedback_entity = result.value
        uid_val = getattr(feedback_entity, "uid", None) if feedback_entity else None
        uid_display = f" (uid: {uid_val})" if uid_val else ""

        return Div(
            Alert(
                P(
                    f"Feedback submitted successfully{uid_display}.",
                    cls="mb-0 font-semibold",
                ),
                P(
                    f"Activity feedback for {subject_uid} saved with ReportSource.HUMAN.",
                    cls="mb-0 text-sm",
                ),
                variant=AlertT.success,
            ),
        )

    return [
        activity_review_landing,
        activity_review_queue_page,
        activity_review_new_page,
        activity_review_snapshot_fragment,
        activity_review_submit_feedback,
    ]


__all__ = ["create_activity_review_ui_routes"]
