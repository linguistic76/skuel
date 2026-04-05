"""Shared helpers for Activity Domain UI views.

Extracted from the 6 Activity Domain view files to eliminate duplication.
Domain-specific logic stays in each domain's *_views.py file.

Usage:
    from ui.activities._shared import safe_id, PRIORITY_ORDER, ConnectionBadges, ConnectionSummary
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Small, Span
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from fasthtml.common import FT


def MetadataField(label: str, *value: "FT") -> "FT":
    """Label + value pair for detail page metadata grids."""
    return Div(
        Small(label, cls="text-muted-foreground block text-sm"),
        *value,
    )


def safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Universal icon + href mapping for cross-domain connection badges.
# Covers all Activity Domains + Curriculum types.
CONNECTION_ICONS: dict[str, tuple[str, str]] = {
    "goal": ("target", "/goals/detail?uid="),
    "task": ("check-square", "/tasks/detail?uid="),
    "habit": ("repeat", "/habits/detail?uid="),
    "event": ("calendar", "/events/detail?uid="),
    "choice": ("git-branch", "/choices/detail?uid="),
    "principle": ("compass", "/principles/detail?uid="),
    "ku": ("atom", "/ku/get?uid="),
    "path_step": ("list", "#"),
    "learning_path": ("map", "#"),
}


def ConnectionBadges(connections: list[dict[str, str]]) -> "FT":
    """Render typed connection badges for cross-domain links.

    Each badge shows an icon + title and links to the target entity's detail page.
    Used by domains that show outgoing connections (Tasks, Habits, Events, Choices).
    """
    if not connections:
        return Span()

    badges: list[Any] = []
    for conn in connections:
        target_type = conn.get("target_type", "")
        title = conn.get("title", conn.get("target_uid", "?"))
        target_uid = conn.get("target_uid", "")
        icon, base_href = CONNECTION_ICONS.get(target_type, ("link", "#"))
        href = f"{base_href}{target_uid}" if base_href != "#" else "#"

        badges.append(
            A(
                UkIcon(icon, height=12, width=12, cls="inline mr-1"),
                title,
                href=href,
                cls="inline-flex items-center mr-2",
                style="text-decoration: none;",
            )
        )

    return Div(*badges, cls="mt-2")


def ConnectionSummary(connections: list[dict[str, str]]) -> "FT":
    """Render a compact summary of connection counts by domain type.

    Shows icon + count for each domain (e.g. "2 tasks, 1 habit").
    Used by gravity-well domains (Goals, Principles) that show incoming connections.
    """
    if not connections:
        return Span()

    counts: dict[str, int] = {}
    for conn in connections:
        source_type = conn.get("source_type", "unknown")
        counts[source_type] = counts.get(source_type, 0) + 1

    parts: list[Any] = []
    for domain, count in sorted(counts.items()):
        icon = CONNECTION_ICONS.get(domain, ("link", "#"))[0]
        parts.append(
            Span(
                UkIcon(icon, height=10, width=10, cls="inline"),
                f" {count}",
                cls="text-muted-foreground text-sm mr-2",
            )
        )

    return Div(*parts, cls="mt-2")
