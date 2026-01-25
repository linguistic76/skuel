"""Entity card pattern used across all 14 SKUEL domains.

This is the primary pattern for displaying domain entities (Tasks, Goals,
Habits, Events, etc.) in lists and grids. It provides consistent layout
with priority indicators, status badges, and proper text truncation.
"""

from typing import Any

from fasthtml.common import Div

from ui.primitives.badge import PriorityBadge, StatusBadge
from ui.primitives.card import Card
from ui.primitives.layout import FlexItem, Row
from ui.primitives.text import CardTitle, SmallText, TruncatedText


def EntityCard(
    title: str,
    description: str = "",
    status: str | None = None,
    priority: str | None = None,
    metadata: list[str] | None = None,
    actions: Any = None,
    href: str | None = None,
    **kwargs: Any,
) -> Div:
    """Generic entity card for all SKUEL domains.

    This card pattern is designed to work with all 14 domains:
    Tasks, Goals, Habits, Events, Choices, Principles, Finance,
    KU, LS, LP, MOC, Journals, Assignments, and LifePath.

    Args:
        title: Entity title (will be truncated if too long)
        description: Optional description (truncated to 2 lines)
        status: Optional status string (active, completed, pending, etc.)
        priority: Optional priority string (critical, high, medium, low)
        metadata: Optional list of metadata strings to display
        actions: Optional action elements (buttons, links)
        href: Optional URL - if provided, card becomes clickable
        **kwargs: Additional attributes passed to Card

    Returns:
        A Card component with the entity content

    Example:
        EntityCard(
            title="Complete project proposal",
            description="Draft and finalize the Q4 project proposal",
            status="in_progress",
            priority="high",
            metadata=["Due: Dec 15", "Project: Q4 Planning"],
            actions=ButtonLink("View", href="/tasks/123"),
        )
    """
    # Priority border colors
    border_colors = {
        "critical": "border-l-error",
        "high": "border-l-error",
        "medium": "border-l-warning",
        "low": "border-l-success",
    }
    border_cls = ""
    if priority:
        border_cls = border_colors.get(priority.lower(), "border-l-base-300")

    # Build header row: title + badges
    badges = []
    priority_badge = PriorityBadge(priority)
    status_badge = StatusBadge(status)
    if priority_badge:
        badges.append(priority_badge)
    if status_badge:
        badges.append(status_badge)

    if badges:
        badge_row = Row(*badges, gap=2)
        header = Row(
            FlexItem(CardTitle(title, truncate=True), grow=True),
            FlexItem(badge_row, shrink=False),
            gap=3,
        )
    else:
        header = FlexItem(CardTitle(title, truncate=True), grow=True)

    # Build content list
    content = [header]

    if description:
        content.append(
            TruncatedText(
                description,
                lines=2,
                cls="text-sm text-base-content/70 mt-2 block",
            )
        )

    if metadata:
        meta_items = [SmallText(m) for m in metadata]
        content.append(Div(*meta_items, cls="flex flex-wrap gap-3 mt-3"))

    if actions:
        content.append(Div(actions, cls="mt-4 pt-3 border-t border-base-200"))

    # Card styling
    card_cls = ""
    if border_cls:
        card_cls = f"border-l-4 {border_cls}"

    # Merge with kwargs cls
    extra_cls = kwargs.pop("cls", "")
    if extra_cls:
        card_cls = f"{card_cls} {extra_cls}".strip()

    return Card(*content, cls=card_cls, **kwargs)
