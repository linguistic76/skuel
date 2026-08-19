"""
Notifications UI Routes
========================

Student-facing pages for viewing in-app notifications.
Shows feedback received, revision requests, and other alerts.

Layout: Standard BasePage (no sidebar needed — simple list view).

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.components import Button, ButtonT
from ui.layouts.base_page import BasePage
from ui.notifications import render_notification_card, render_notification_empty_state
from ui.patterns.page_header import PageHeader

if TYPE_CHECKING:
    from core.services.notifications.notification_service import NotificationService

logger = get_logger("skuel.routes.notifications.ui")


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
        unread_count = sum(1 for n in notifications if not n.read)

        header = PageHeader(
            title="Notifications",
            subtitle=f"{unread_count} unread" if unread_count > 0 else "All caught up",
        )

        mark_all_btn = ""
        if unread_count > 0:
            mark_all_btn = Button(
                "Mark all as read",
                cls=ButtonT.ghost,
                size="sm",
                hx_post="/notifications/read-all",
                hx_target="#notification-list",
                hx_swap="innerHTML",
            )

        if notifications:
            notif_cards = [render_notification_card(n) for n in notifications]
            content = Div(
                Div(mark_all_btn, cls="flex justify-end mb-4") if mark_all_btn else "",
                Div(*notif_cards, cls="space-y-3"),
                id="notification-list",
            )
        else:
            content = Div(render_notification_empty_state(), id="notification-list")

        return BasePage(
            Div(header, content),
            title="Notifications",
            request=request,
        )

    @rt("/notifications/{notification_uid}/read", methods=["POST"])
    @csrf_protected
    async def mark_notification_read(request: Request, notification_uid: str) -> Any:
        """Mark a single notification as read. Returns updated card via HTMX."""
        user_uid = require_authenticated_user(request)

        await notification_service.mark_read(notification_uid, user_uid)

        # Return the updated notification card
        result = await notification_service.get_notifications(user_uid=user_uid, limit=50)
        notifications = result.value if not result.is_error else []

        # Find the specific notification to re-render
        for n in notifications:
            if n.uid == notification_uid:
                return render_notification_card(n)

        # If not found, return empty (was deleted)
        return ""

    @rt("/notifications/read-all", methods=["POST"])
    @csrf_protected
    async def mark_all_read(request: Request) -> Any:
        """Mark all notifications as read. Returns updated list via HTMX."""
        user_uid = require_authenticated_user(request)

        await notification_service.mark_all_read(user_uid)

        # Return full updated list
        result = await notification_service.get_notifications(user_uid=user_uid, limit=50)
        notifications = result.value if not result.is_error else []

        if notifications:
            return Div(*[render_notification_card(n) for n in notifications], cls="space-y-3")

        return render_notification_empty_state()

    return []
