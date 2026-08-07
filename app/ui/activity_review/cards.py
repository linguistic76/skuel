"""Activity Review card components."""

from typing import Any

from fasthtml.common import H4, Div, P, Span

from ui.components import ButtonT, Card
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.primitives import ButtonLink


def render_queue_item(item: dict[str, Any]) -> Any:
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
        except (ValueError, TypeError):  # fmt: skip
            date_str = str(created_at)[:10]

    domain_badges = [Badge(d, variant=BadgeT.ghost, size=Size.xs) for d in (domains or [])]

    review_href = f"/activity-review/new?subject_uid={subject_uid}&time_period={time_period}"

    return Div(
        Card(
            H4(subject_uid, cls="font-semibold mb-1"),
            P(
                f"{date_str} · {time_period}",
                cls="text-xs text-muted-foreground mb-2",
            ),
            Div(*domain_badges, cls="flex flex-wrap gap-1 mb-2") if domain_badges else None,
            P(message, cls="text-sm text-muted-foreground mb-3") if message else None,
            ButtonLink(
                "Start Review",
                href=review_href,
                cls=ButtonT.primary,
                size="sm",
            ),
            cls="bg-background shadow-xs mb-3 p-4",
        ),
    )


def render_snapshot_domain_card(domain_name: str, items: list[Any]) -> Any:
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
