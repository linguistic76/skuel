"""
Notifications UI Cards
======================

Card components for notification rendering.
"""

from datetime import datetime
from typing import Any

from fasthtml.common import Div, P, Span

from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.primitives import ButtonLink

# ============================================================================
# NOTIFICATION TYPE CONFIG
# ============================================================================

NOTIFICATION_ICONS: dict[str, str] = {
    "feedback_received": "💬",
    "revision_requested": "✏️",
}

NOTIFICATION_BADGE_VARIANT: dict[str, BadgeT] = {
    "feedback_received": BadgeT.info,
    "revision_requested": BadgeT.warning,
}


# ============================================================================
# COMPONENTS
# ============================================================================


def render_notification_card(notif: dict[str, Any]) -> Div:
    """Render a single notification card."""
    ntype = notif.get("notification_type", "")
    icon = NOTIFICATION_ICONS.get(ntype, "🔔")
    badge_variant = NOTIFICATION_BADGE_VARIANT.get(ntype, BadgeT.ghost)
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
    link_href = f"/gradebook/{source_uid}" if source_uid else "#"

    mark_read_btn = ""
    if not is_read:
        mark_read_btn = Button(
            "Mark read",
            cls=ButtonT.ghost,
            size="xs",
            hx_post=f"/notifications/{notif['uid']}/read",
            hx_target=f"#notif-{notif['uid']}",
            hx_swap="outerHTML",
        )

    return Div(
        CardBody(
            Div(
                Span(icon, cls="text-lg", aria_hidden="true"),
                Div(
                    Div(
                        Span(notif.get("title", ""), cls="font-medium"),
                        Badge(
                            ntype.replace("_", " ").title(),
                            variant=badge_variant,
                            size=Size.sm,
                            cls="ml-2",
                        ),
                        cls="flex items-center gap-1",
                    ),
                    P(notif.get("message", ""), cls="text-sm text-muted-foreground mt-1"),
                    Div(
                        Span(time_display, cls="text-xs text-muted-foreground"),
                        ButtonLink(
                            "View →",
                            href=link_href,
                            cls=ButtonT.ghost,
                            size="xs",
                        ),
                        mark_read_btn,
                        cls="flex items-center gap-3 mt-2",
                    ),
                    cls="flex-1",
                ),
                cls="flex items-start gap-3",
            ),
            cls="p-4",
        ),
        cls=f"card {bg_cls} shadow-xs {read_cls}",
        id=f"notif-{notif['uid']}",
    )


def render_notification_empty_state() -> Div:
    """Show when there are no notifications."""
    return Card(
        EmptyState("No notifications", description="You're all caught up!", icon="🔔"),
        cls="bg-background",
    )
