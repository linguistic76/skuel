"""
Notifications UI Routes
========================

Student-facing pages for viewing in-app notifications.
Shows feedback received, revision requests, and other alerts.

Layout: Standard BasePage (no sidebar needed — simple list view).

See: /docs/architecture/SUBMISSION_FEEDBACK_LOOP.md
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Div,
    P,
    Span,
)
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.patterns.page_header import PageHeader

if TYPE_CHECKING:
    from core.services.notifications.notification_service import NotificationService

logger = get_logger("skuel.routes.notifications.ui")


# ============================================================================
# NOTIFICATION TYPE CONFIG
# ============================================================================

_NOTIFICATION_ICONS: dict[str, str] = {
    "feedback_received": "💬",
    "revision_requested": "✏️",
}

_NOTIFICATION_BADGE_CLS: dict[str, str] = {
    "feedback_received": "badge-info",
    "revision_requested": "badge-warning",
}


# ============================================================================
# COMPONENTS
# ============================================================================


def _notification_card(notif: dict[str, Any]) -> Div:
    """Render a single notification card."""
    ntype = notif.get("notification_type", "")
    icon = _NOTIFICATION_ICONS.get(ntype, "🔔")
    badge_cls = _NOTIFICATION_BADGE_CLS.get(ntype, "badge-ghost")
    is_read = notif.get("read", False)

    read_cls = "opacity-60" if is_read else ""
    bg_cls = "bg-background" if is_read else "bg-background border-l-4 border-primary"

    # Format created_at
    created_at = notif.get("created_at", "")
    time_display = ""
    if created_at:
        if isinstance(created_at, datetime):
            time_display = created_at.strftime("%b %d, %H:%M")
        else:
            time_display = str(created_at)[:16]

    source_uid = notif.get("source_uid", "")
    link_href = f"/submissions/{source_uid}" if source_uid else "#"

    mark_read_btn = ""
    if not is_read:
        mark_read_btn = Button(
            "Mark read",
            variant=ButtonT.ghost,
            cls="btn-xs",
            **{
                "hx-post": f"/notifications/{notif['uid']}/read",
                "hx-target": f"#notif-{notif['uid']}",
                "hx-swap": "outerHTML",
            },
        )

    return Div(
        Div(
            Div(
                Span(icon, cls="text-lg", aria_hidden="true"),
                Div(
                    Div(
                        Span(notif.get("title", ""), cls="font-medium"),
                        Span(
                            ntype.replace("_", " ").title(),
                            cls=f"badge badge-sm {badge_cls} ml-2",
                        ),
                        cls="flex items-center gap-1",
                    ),
                    P(notif.get("message", ""), cls="text-sm text-muted-foreground mt-1"),
                    Div(
                        Span(time_display, cls="text-xs text-muted-foreground"),
                        A(
                            "View →",
                            href=link_href,
                            cls="text-xs link link-primary",
                        ),
                        mark_read_btn,
                        cls="flex items-center gap-3 mt-2",
                    ),
                    cls="flex-1",
                ),
                cls="flex items-start gap-3",
            ),
            cls="card-body p-4",
        ),
        cls=f"card {bg_cls} shadow-sm {read_cls}",
        id=f"notif-{notif['uid']}",
    )


def _empty_state() -> Div:
    """Show when there are no notifications."""
    return Div(
        Div(
            Span("🔔", cls="text-4xl"),
            H3("No notifications", cls="text-lg font-medium mt-2"),
            P("You're all caught up!", cls="text-muted-foreground"),
            cls="text-center py-12",
        ),
        cls="card bg-background",
    )


# ============================================================================
# ROUTE FACTORY
# ============================================================================


def create_notifications_ui_routes(
    app: Any,
    rt: Any,
    notification_service: "NotificationService",
    **_kwargs: Any,
) -> list[Any]:
    """Create UI routes for notifications."""

    def get_notification_service() -> "NotificationService":
        return notification_service

    @rt("/notifications")
    async def notifications_page(request: Request) -> Any:
        """Notifications list page."""
        user_uid = require_authenticated_user(request)

        result = await notification_service.get_notifications(
            user_uid=user_uid, limit=50, include_read=True
        )

        notifications = result.value if not result.is_error else []
        unread_count = sum(1 for n in notifications if not n.get("read", False))

        header = PageHeader(
            title="Notifications",
            subtitle=f"{unread_count} unread" if unread_count > 0 else "All caught up",
        )

        mark_all_btn = ""
        if unread_count > 0:
            mark_all_btn = Button(
                "Mark all as read",
                variant=ButtonT.ghost,
                cls="btn-sm",
                **{
                    "hx-post": "/notifications/read-all",
                    "hx-target": "#notification-list",
                    "hx-swap": "innerHTML",
                },
            )

        if notifications:
            notif_cards = [_notification_card(n) for n in notifications]
            content = Div(
                Div(mark_all_btn, cls="flex justify-end mb-4") if mark_all_btn else "",
                Div(*notif_cards, cls="space-y-3"),
                id="notification-list",
            )
        else:
            content = Div(_empty_state(), id="notification-list")

        return BasePage(
            Div(header, content),
            title="Notifications",
            request=request,
        )

    @rt("/notifications/{notification_uid}/read", methods=["POST"])
    async def mark_notification_read(request: Request, notification_uid: str) -> Any:
        """Mark a single notification as read. Returns updated card via HTMX."""
        user_uid = require_authenticated_user(request)

        await notification_service.mark_read(notification_uid, user_uid)

        # Return the updated notification card
        result = await notification_service.get_notifications(user_uid=user_uid, limit=50)
        notifications = result.value if not result.is_error else []

        # Find the specific notification to re-render
        for n in notifications:
            if n.get("uid") == notification_uid:
                return _notification_card(n)

        # If not found, return empty (was deleted)
        return ""

    @rt("/notifications/read-all", methods=["POST"])
    async def mark_all_read(request: Request) -> Any:
        """Mark all notifications as read. Returns updated list via HTMX."""
        user_uid = require_authenticated_user(request)

        await notification_service.mark_all_read(user_uid)

        # Return full updated list
        result = await notification_service.get_notifications(user_uid=user_uid, limit=50)
        notifications = result.value if not result.is_error else []

        if notifications:
            return Div(*[_notification_card(n) for n in notifications], cls="space-y-3")

        return _empty_state()

    return []
