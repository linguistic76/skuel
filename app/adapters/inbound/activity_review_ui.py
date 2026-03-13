"""
Activity Review UI Routes — Admin Human Feedback on Activity Domains
=====================================================================

Admin-facing UI for reviewing a user's Activity Domain data and writing
structured feedback. Feedback stored as ActivityReport with ProcessorType.HUMAN.

Two trigger paths:
1. Admin-initiated: admin navigates to /activity-review/new?subject_uid=...
2. User-initiated: user requests review → appears in /activity-review/queue

Routes:
- GET /activity-review           — redirect to queue
- GET /activity-review/queue     — pending review requests (admin-only)
- GET /activity-review/new       — admin review form (admin-only)
- GET /activity-review/snapshot-fragment  — HTMX domain snapshot fragment
- POST /activity-review/submit-feedback   — HTMX feedback submission fragment

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.report_protocols import ActivityReportOperations, ReviewQueueOperations
    from core.services.user.user_context_builder import UserContextBuilder

from fasthtml.common import (
    H3,
    H4,
    A,
    Div,
    Form,
    Label,
    NotStr,
    Option,
    P,
    Script,
    Span,
)
from starlette.requests import Request
from starlette.responses import RedirectResponse

from adapters.inbound.auth import make_service_getter, require_admin
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.feedback import Badge, BadgeT
from ui.forms import Input, Select, Textarea
from ui.layout import Size
from ui.patterns.page_header import PageHeader
from ui.patterns.sidebar import SidebarItem, SidebarPage
from ui.cards import Card, CardBody

logger = get_logger("skuel.routes.activity_review.ui")


# ============================================================================
# SIDEBAR NAVIGATION
# ============================================================================

ACTIVITY_REVIEW_SIDEBAR_ITEMS = [
    SidebarItem("Queue", "/activity-review/queue", "queue", icon="📋"),
    SidebarItem("New Review", "/activity-review/new", "new", icon="✍️"),
]

_DOMAIN_CHOICES = [
    ("tasks", "Tasks"),
    ("goals", "Goals"),
    ("habits", "Habits"),
    ("events", "Events"),
    ("choices", "Choices"),
    ("principles", "Principles"),
]


# ============================================================================
# FRAGMENT RENDERERS
# ============================================================================


def _render_queue_item(item: dict[str, Any]) -> Any:
    """Render a single pending review request card."""
    subject_uid = item.get("subject_uid", "")
    time_period = item.get("time_period", "7d")
    domains = item.get("domains") or []
    message = item.get("message") or ""
    created_at = item.get("created_at", "")

    date_str = ""
    if created_at:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(str(created_at))
            date_str = dt.strftime("%d %b %Y")
        except (ValueError, TypeError):
            date_str = str(created_at)[:10]

    domain_badges = [Badge(d, variant=BadgeT.ghost, size=Size.xs) for d in (domains or [])]

    review_href = f"/activity-review/new?subject_uid={subject_uid}&time_period={time_period}"

    return Div(
        Card(
            CardBody(
                H4(subject_uid, cls="font-semibold mb-1"),
                P(
                    f"{date_str} · {time_period}",
                    cls="text-xs text-muted-foreground mb-2",
                ),
                Div(*domain_badges, cls="flex flex-wrap gap-1 mb-2") if domain_badges else None,
                P(message, cls="text-sm text-muted-foreground mb-3") if message else None,
                A(
                    "Start Review",
                    href=review_href,
                    cls="btn btn-sm btn-primary",
                ),
                cls="p-4",
            ),
            cls="bg-background shadow-sm mb-3",
        ),
    )


def _render_snapshot_domain_card(domain_name: str, items: list[Any]) -> Any:
    """Render a single domain's activity snapshot card."""
    if not items:
        return Card(
            H4(domain_name.title(), cls="font-semibold mb-1"),
            P("No recent activity.", cls="text-sm text-muted-foreground"),
            cls="bg-muted p-4 mb-3",
        )

    item_rows = []
    for item in items[:10]:
        title = item.get("title", "") if isinstance(item, dict) else getattr(item, "title", "")
        status = item.get("status", "") if isinstance(item, dict) else getattr(item, "status", "")
        item_rows.append(
            Div(
                Span(title, cls="text-sm flex-1"),
                Badge(status, variant=BadgeT.ghost, size=Size.xs) if status else None,
                cls="flex items-center gap-2 py-1 border-b border-border last:border-0",
            )
        )

    return Card(
        H4(f"{domain_name.title()} ({len(items)})", cls="font-semibold mb-3"),
        Div(*item_rows),
        cls="bg-muted p-4 mb-3",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_activity_review_ui_routes(
    _app: Any,
    rt: Any,
    activity_report: "ActivityReportOperations",
    review_queue: "ReviewQueueOperations | None" = None,
    user_service: Any = None,
    context_builder: "UserContextBuilder | None" = None,
) -> list[Any]:
    """
    Create Activity Review admin UI routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        activity_report: ActivityReportService for snapshot + feedback operations
        review_queue: ReviewQueueService for pending review queue
        context_builder: UserContextBuilder for building UserContext (required for snapshots)
        user_service: UserService for admin role checks

    Returns:
        List of registered route functions
    """
    logger.info("Creating Activity Review UI routes")

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # REDIRECT
    # ========================================================================

    @rt("/activity-review")
    async def activity_review_landing(request: Request) -> Any:
        """Redirect to queue."""
        return RedirectResponse("/activity-review/queue", status_code=303)

    # ========================================================================
    # QUEUE PAGE (admin-only)
    # ========================================================================

    @rt("/activity-review/queue")
    @require_admin(get_user_service)
    async def activity_review_queue_page(request: Request, current_user: Any) -> Any:
        """Admin queue: pending review requests from users."""
        _not_found = object()
        _uid_val = getattr(current_user, "uid", _not_found)
        admin_uid = str(current_user) if _uid_val is _not_found else str(_uid_val)

        pending: list[Any] = []
        try:
            if review_queue is not None:
                result = await review_queue.get_pending_reviews(_admin_uid=admin_uid)
                if not result.is_error:
                    pending = result.value or []
        except Exception as e:
            logger.error(f"Error loading review queue: {e}", exc_info=True)

        if pending:
            queue_content: Any = Div(*[_render_queue_item(item) for item in pending])
        else:
            queue_content = Div(
                P("No pending review requests.", cls="text-center text-muted-foreground py-8"),
                P(
                    "Users can request an activity review from their feedback page.",
                    cls="text-sm text-center text-foreground/40",
                ),
            )

        content = Div(
            PageHeader("Review Queue", subtitle="Pending activity review requests from users"),
            Card(
                H3("Pending Requests", cls="font-semibold mb-4"),
                queue_content,
                cls="bg-background shadow-sm p-4",
            ),
        )

        return await SidebarPage(
            content=content,
            items=ACTIVITY_REVIEW_SIDEBAR_ITEMS,
            active="queue",
            title="Activity Review",
            subtitle="Admin feedback on Activity Domains",
            storage_key="activity-review-sidebar",
            page_title="Review Queue",
            request=request,
            active_page="activity-review",
            title_href="/activity-review",
        )

    # ========================================================================
    # NEW REVIEW PAGE (admin-only)
    # ========================================================================

    @rt("/activity-review/new")
    @require_admin(get_user_service)
    async def activity_review_new_page(
        request: Request,
        current_user: Any,
        subject_uid: str = "",
        time_period: str = "7d",
    ) -> Any:
        """Admin review form: load snapshot, write feedback, submit."""
        domain_checkboxes = []
        for domain_value, domain_label in _DOMAIN_CHOICES:
            domain_checkboxes.append(
                Div(
                    Input(
                        type="checkbox",
                        name="domains",
                        value=domain_value,
                        checked=True,
                        cls="checkbox checkbox-sm",
                        id=f"domain-{domain_value}",
                    ),
                    Label(domain_label, fr=f"domain-{domain_value}", cls="label label-text ml-2"),
                    cls="flex items-center gap-1",
                )
            )

        snapshot_form = Card(
            H3("Load Activity Snapshot", cls="font-semibold mb-4"),
            Form(
                Div(
                    Label("User UID", cls="label label-text"),
                    Input(
                        type="text",
                        name="subject_uid",
                        value=subject_uid,
                        placeholder="user_name",
                        id="snapshot-subject-uid",
                    ),
                    cls="mb-3",
                ),
                Div(
                    Label("Time Period", cls="label label-text"),
                    Select(
                        Option("Last 7 days", value="7d", selected=(time_period == "7d")),
                        Option("Last 14 days", value="14d", selected=(time_period == "14d")),
                        Option("Last 30 days", value="30d", selected=(time_period == "30d")),
                        Option("Last 90 days", value="90d", selected=(time_period == "90d")),
                        name="time_period",
                        id="snapshot-time-period",
                    ),
                    cls="mb-3",
                ),
                Div(
                    Label("Domains", cls="label label-text"),
                    Div(*domain_checkboxes, cls="flex flex-wrap gap-4 mt-1"),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "Load Snapshot",
                        type="submit",
                        variant=ButtonT.secondary,
                    ),
                    cls="text-right",
                ),
                **{
                    "hx-get": "/activity-review/snapshot-fragment",
                    "hx-target": "#snapshot-display",
                    "hx-swap": "innerHTML",
                    "hx-include": "[name='subject_uid'],[name='time_period'],[name='domains']",
                },
            ),
            cls="bg-background shadow-sm p-4 mb-4",
        )

        snapshot_display = Div(
            P(
                'Enter a user UID and click "Load Snapshot" to preview their activity data.',
                cls="text-center text-muted-foreground py-6",
            ),
            id="snapshot-display",
        )

        feedback_form = Card(
            H3("Write Feedback", cls="font-semibold mb-4"),
            Form(
                Input(
                    type="hidden", name="subject_uid", id="feedback-subject-uid", value=subject_uid
                ),
                Input(
                    type="hidden", name="time_period", id="feedback-time-period", value=time_period
                ),
                Div(
                    Label("Feedback", cls="label label-text"),
                    Textarea(
                        name="feedback_text",
                        placeholder="Write your qualitative feedback here. What patterns do you notice? What recommendations do you have?",
                        cls="h-40",
                    ),
                    cls="mb-4",
                ),
                Div(
                    Button(
                        "Submit Feedback",
                        type="submit",
                        variant=ButtonT.primary,
                    ),
                    cls="text-right",
                ),
                Div(id="submit-status", cls="mt-3"),
                **{
                    "hx-post": "/activity-review/submit-feedback",
                    "hx-target": "#submit-status",
                    "hx-swap": "innerHTML",
                    "hx-include": "[name='subject_uid'],[name='time_period'],[name='feedback_text']",
                },
            ),
            # Sync hidden fields from snapshot form before posting
            Script(
                NotStr("""
                document.body.addEventListener('htmx:afterRequest', function(evt) {
                    if (evt.detail.elt.getAttribute('hx-target') === '#snapshot-display') {
                        var subjectEl = document.getElementById('snapshot-subject-uid');
                        var periodEl = document.getElementById('snapshot-time-period');
                        var fbSubjectEl = document.getElementById('feedback-subject-uid');
                        var fbPeriodEl = document.getElementById('feedback-time-period');
                        if (subjectEl && fbSubjectEl) fbSubjectEl.value = subjectEl.value;
                        if (periodEl && fbPeriodEl) fbPeriodEl.value = periodEl.value;
                    }
                });
                """)
            ),
            cls="bg-background shadow-sm p-4 mt-4",
        )

        content = Div(
            PageHeader(
                "New Activity Review",
                subtitle="Review a user's Activity Domain data and write feedback",
            ),
            snapshot_form,
            snapshot_display,
            feedback_form,
        )

        return await SidebarPage(
            content=content,
            items=ACTIVITY_REVIEW_SIDEBAR_ITEMS,
            active="new",
            title="Activity Review",
            subtitle="Admin feedback on Activity Domains",
            storage_key="activity-review-sidebar",
            page_title="New Review",
            request=request,
            active_page="activity-review",
            title_href="/activity-review",
        )

    # ========================================================================
    # SNAPSHOT FRAGMENT (HTMX)
    # ========================================================================

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
            return Div(
                P("Please enter a user UID.", cls="text-error text-sm"),
            )

        try:
            if not context_builder:
                return Div(P("Context builder not configured.", cls="text-error text-sm"))

            ctx_result = await context_builder.build_rich(subject_uid, window=time_period)
            if ctx_result.is_error:
                return Div(
                    P(f"Failed to build context: {ctx_result.error}", cls="text-error text-sm")
                )

            result = await activity_report.create_snapshot(
                context=ctx_result.value,
                time_period=time_period,
                domains=domains,
            )
        except Exception as e:
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

        # Build domain cards from snapshot data
        domain_cards = []
        for domain_name in domains or [d for d, _ in _DOMAIN_CHOICES]:
            items = snapshot.get(domain_name) or []
            domain_cards.append(_render_snapshot_domain_card(domain_name, items))

        return Div(
            H3(
                f"Activity Snapshot: {subject_uid} — {time_period}",
                cls="font-semibold mb-4",
            ),
            *domain_cards,
        )

    # ========================================================================
    # SUBMIT FEEDBACK FRAGMENT (HTMX)
    # ========================================================================

    @rt("/activity-review/submit-feedback", methods=["POST"])
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
        admin_uid = str(admin_uid_val) if admin_uid_val is not _missing else str(current_user)

        if not subject_uid or not feedback_text:
            return Div(
                Div(
                    P("User UID and feedback text are required.", cls="mb-0"),
                    cls="alert alert-error",
                ),
            )

        try:
            result = await activity_report.submit_report(
                admin_uid=admin_uid,
                subject_uid=subject_uid,
                feedback_text=feedback_text,
                time_period=time_period,
                domains=domains,
            )
        except Exception as e:
            logger.error(f"Error submitting activity feedback: {e}", exc_info=True)
            return Div(
                Div(
                    P(f"Error submitting feedback: {e}", cls="mb-0"),
                    cls="alert alert-error",
                ),
            )

        if result.is_error:
            return Div(
                Div(
                    P(
                        f"Failed: {result.error.message if result.error else 'Unknown error'}",
                        cls="mb-0",
                    ),
                    cls="alert alert-error",
                ),
            )

        feedback_entity = result.value
        uid_val = getattr(feedback_entity, "uid", None) if feedback_entity else None
        uid_display = f" (uid: {uid_val})" if uid_val else ""

        return Div(
            Div(
                P(
                    f"Feedback submitted successfully{uid_display}.",
                    cls="mb-0 font-semibold",
                ),
                P(
                    f"Activity feedback for {subject_uid} saved with ProcessorType.HUMAN.",
                    cls="mb-0 text-sm",
                ),
                cls="alert alert-success",
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
