"""
Notifications UI Cards
======================

Card components for notification rendering. A card presents from the
notification's kind (``NotificationType`` — icon, badge, label) and links to
the entity it is about (``source_type`` + ``source_uid`` → the detail page),
so a handler never chooses a URL and every kind opens the right page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fasthtml.common import Div, P, Span

from core.models.enums.notification_enums import NotificationType
from ui.components import Button, ButtonT, Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from core.models.notification import Notification

# What an unknown kind (written by another build) renders as.
_GENERIC_ICON = "🔔"
_GENERIC_LABEL = "Notification"


# ============================================================================
# LINKS
# ============================================================================


def notification_href(notif: Notification) -> str | None:
    """The page a notification opens, or ``None`` when its source has no page.

    One override: a submission for review opens the teacher's review page,
    not the entry's own detail (which is the student's GradeBook view).
    Everything else is the source entity's detail page.
    """
    if notif.notification_type is NotificationType.SUBMISSION_FOR_REVIEW:
        return f"/teaching/review/{notif.source_uid}"
    return entity_detail_href(notif.source_type.value, notif.source_uid)


# ============================================================================
# COMPONENTS
# ============================================================================


def render_notification_card(notif: Notification) -> Div:
    """Render a single notification card."""
    ntype = notif.notification_type
    if ntype is None:
        icon, badge_variant, label = _GENERIC_ICON, BadgeT.ghost, _GENERIC_LABEL
    else:
        icon = ntype.get_icon()
        badge_variant = BadgeT(ntype.get_badge_variant())
        label = ntype.get_label()
    is_read = notif.read

    read_cls = "opacity-60" if is_read else ""
    bg_cls = "bg-background" if is_read else "bg-background border-l-4 border-primary"

    time_display = notif.created_at.strftime("%b %d, %H:%M")

    link_href = notification_href(notif)
    view_link = (
        ButtonLink("View →", href=link_href, cls=ButtonT.ghost, size="xs") if link_href else ""
    )

    mark_read_btn = ""
    if not is_read:
        mark_read_btn = Button(
            "Mark read",
            cls=ButtonT.ghost,
            size="xs",
            hx_post=f"/notifications/{notif.uid}/read",
            hx_target=f"#notif-{notif.uid}",
            hx_swap="outerHTML",
        )

    return Div(
        CardBody(
            Div(
                Span(icon, cls="text-lg", aria_hidden="true"),
                Div(
                    Div(
                        Span(notif.title, cls="font-medium"),
                        Badge(
                            label,
                            variant=badge_variant,
                            size=Size.sm,
                            cls="ml-2",
                        ),
                        cls="flex items-center gap-1",
                    ),
                    P(notif.message, cls="text-sm text-muted-foreground mt-1"),
                    Div(
                        Span(time_display, cls="text-xs text-muted-foreground"),
                        view_link,
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
        id=f"notif-{notif.uid}",
    )


def render_notification_empty_state() -> Div:
    """Show when there are no notifications."""
    return Card(
        EmptyState("No notifications", description="You're all caught up!", icon="🔔"),
        cls="bg-background",
    )
