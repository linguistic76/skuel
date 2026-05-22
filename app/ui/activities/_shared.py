"""Shared helpers for Activity Domain UI views.

Extracted from the 6 Activity Domain view files to eliminate duplication.
Domain-specific logic stays in each domain's *_views.py file.

Usage:
    from ui.activities._shared import safe_id, PRIORITY_ORDER, ConnectionBadges, ConnectionSummary
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, Small, Span
from monsterui.franken import UkIcon

from ui.patterns.empty_state import EmptyState

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
    "ku": ("atom", "/explore/ku/"),
    "path_step": ("list", "/explore/ps/"),
    "learning_path": ("map", "#"),
}


def CurriculumOriginField(ps_uid: str, ps_title: str) -> "FT":
    """Breadcrumb-style banner linking a spawned activity to its source PathStep.

    Rendered above the detail body when an activity carries ``source_path_step_uid``
    (i.e. it was spawned by engaging a PathStep). User-created activities omit it.
    """
    icon = CONNECTION_ICONS["path_step"][0]
    return Div(
        UkIcon(icon, height=14, width=14, cls="inline mr-1"),
        Span("From learning step: ", cls="text-muted-foreground"),
        A(
            ps_title or ps_uid,
            href=f"/explore/ps/{ps_uid}",
            cls="font-medium",
            style="text-decoration: none;",
        ),
        cls="mb-4 flex items-center text-sm",
    )


def ConnectionBadges(connections: list[dict[str, str]]) -> "FT":
    """Render typed connection badges for cross-domain links.

    Each badge shows an icon + title and links to the target entity's detail page.
    Used by domains that show outgoing connections (Tasks, Habits, Events, Choices).
    """
    if not connections:
        return Span()

    badges: list[Any] = []
    for conn in connections:
        connected_type = conn.get("connected_type", "")
        title = conn.get("title", conn.get("connected_uid", "?"))
        connected_uid = conn.get("connected_uid", "")
        icon, base_href = CONNECTION_ICONS.get(connected_type, ("link", "#"))
        href = f"{base_href}{connected_uid}" if base_href != "#" else "#"

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
        connected_type = conn.get("connected_type", "unknown")
        counts[connected_type] = counts.get(connected_type, 0) + 1

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


def ActivityList(
    items: list,
    domain: str,
    card_fn: Callable,
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Generic list renderer for any Activity Domain.

    Eliminates the near-identical {Domain}List functions across the 6 view files.
    Each domain's {Domain}List becomes a one-liner delegating here.

    Args:
        items: Domain entities to render.
        domain: Singular domain slug (e.g. "task", "goal"). Used for the list
            container id and EmptyState copy.
        card_fn: Domain card component (e.g. TaskCard).
        connections_map: Cross-domain connection data keyed by entity UID.
    """
    list_id = f"{domain}-list"
    if not items:
        return Div(
            EmptyState(
                title=f"No {domain}s found",
                description=f"Upload YAML files to add {domain}s, or adjust your filters.",
                action_text=f"Upload {domain.title()}s",
                action_href="/upload",
            ),
            id=list_id,
        )
    cards = [
        card_fn(item, connections_map.get(item.uid, []) if connections_map else [])
        for item in items
    ]
    return Div(*cards, id=list_id, cls="mt-4 space-y-3")
