"""Shared helpers for Activity Domain UI views.

Extracted from the 6 Activity Domain view files to eliminate duplication.
Domain-specific logic stays in each domain's *_views.py file.

Usage:
    from ui.activities._shared import safe_id, PRIORITY_ORDER, PriorityBadgeDropdown, ConnectionBadges
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Button, Div, Li, Small, Span, Ul

from core.models.enums import Priority
from ui.components import Icon
from ui.feedback import Badge, BadgeT, PriorityBadge
from ui.patterns.empty_state import EmptyState
from ui.primitives import dropdown_menu, section_label

if TYPE_CHECKING:
    from fasthtml.common import FT


def ConnectionsSection(
    connections: list[dict[str, str]],
    domain_labels: dict[str, tuple[str, str, str]],
) -> "FT":
    """Detail-page 'Connections' block: linked entities grouped by domain.

    Args:
        connections: Dicts with connected_type / connected_uid / title keys.
        domain_labels: connected_type -> (section label, icon name, href prefix).
            An href prefix of "#" renders a dead link (detail page not built yet).
    """
    groups: dict[str, list[dict[str, str]]] = {}
    for conn in connections:
        connected_type = conn.get("connected_type", "unknown")
        if connected_type not in groups:
            groups[connected_type] = []
        groups[connected_type].append(conn)

    sections: list[Any] = []
    for domain, conns in groups.items():
        label, icon, base_href = domain_labels.get(
            domain, (f"{domain.title()} connections", "link", "#")
        )
        links = [
            Li(
                Icon(icon, size=12, cls="inline mr-2"),
                A(
                    conn.get("title", conn.get("connected_uid", "?")),
                    href=f"{base_href}{conn.get('connected_uid', '')}" if base_href != "#" else "#",
                    cls="hover:underline text-muted-foreground",
                ),
            )
            for conn in conns
        ]
        sections.append(
            Div(
                Small(
                    label,
                    cls="text-muted-foreground uppercase text-sm block mb-2",
                ),
                Ul(*links, cls="divide-y"),
                cls="mb-2",
            )
        )

    return ConnectionsBlock(*sections)


def tag_badges(tags: Sequence[str], limit: int | None = None) -> list["FT"]:
    """Secondary badges for an entity's tags, optionally capped at ``limit``.

    Cards cap at 5; detail pages render the full set.
    """
    shown = tags[:limit] if limit is not None else tags
    return [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in shown]


def TagsBlock(tags: Sequence[str]) -> "FT":
    """Detail-page 'Tags' block. Renders an empty Div when there are no tags."""
    if not tags:
        return Div()
    return Div(
        Small("Tags", cls="text-muted-foreground block mb-2"),
        *tag_badges(tags),
        cls="my-4",
    )


def ConnectionsBlock(*body: "FT") -> "FT":
    """Detail-page 'Connections' wrapper: the section label + a caller-supplied body.

    The body varies by lens — flat :func:`ConnectionBadges` for domains that show
    outgoing links (Tasks, Habits, Events, Choices), domain-grouped lists for the
    gravity-well domains (see :func:`ConnectionsSection`). Only the label and
    spacing are shared, so they live here and nowhere else.
    """
    return Div(section_label("Connections"), *body, cls="my-4")


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


def PriorityBadgeDropdown(
    uid: str,
    priority: str | None,
    domain: str,
    singular: str,
) -> "FT":
    """Interactive priority badge: click opens a dropdown of the 4 priority levels.

    Alpine owns the open/close state (inline ``x-data``); picking a level does
    ``POST /api/{domain}/{uid}/priority`` via HTMX and swaps the re-rendered
    card (``#{singular}-{safe_id(uid)}`` — the id every Activity card uses)
    back in, mirroring the status-toggle pattern.

    Args:
        uid: Entity UID.
        priority: Current priority value (e.g. ``"high"``), or None if unset.
        domain: Plural URL path segment, e.g. ``"tasks"``.
        singular: Singular card-id prefix, e.g. ``"task"``.
    """
    current = Priority.from_value(priority) if priority else None
    card_target = f"#{singular}-{safe_id(uid)}"

    badge = (
        PriorityBadge(current.value)
        if current is not None
        else Badge("Priority", variant=BadgeT.ghost)
    )
    trigger = Button(
        badge,
        Icon("chevron-down", size=12, cls="inline text-muted-foreground"),
        type="button",
        cls="inline-flex items-center gap-0.5 border-0 bg-transparent p-0 cursor-pointer",
        title="Change priority",
        aria_label="Change priority",
        **{"@click": "open = !open"},
    )

    options: list[Any] = []
    for level in Priority:
        is_current = level == current
        options.append(
            Button(
                Span(
                    cls="w-2 h-2 rounded-full flex-none",
                    style=f"background-color: {level.get_color()}",
                ),
                Span(level.value.title(), cls="flex-1 text-left text-sm"),
                Icon("check", size=14, cls="flex-none text-blue-600") if is_current else None,
                type="button",
                cls=(
                    "w-full flex items-center gap-2 px-2.5 py-1.5 rounded-[8px] border-0 "
                    "text-left cursor-pointer transition-colors "
                    + ("bg-blue-50" if is_current else "bg-transparent hover:bg-slate-100")
                ),
                hx_post=f"/api/{domain}/{uid}/priority",
                hx_vals=f'{{"priority": "{level.value}"}}',
                hx_target=card_target,
                hx_swap="outerHTML",
                **{"@click": "open = false"},
            )
        )

    return Div(
        trigger,
        dropdown_menu(
            *options,
            cls="w-36 right-auto",
            **{"x-show": "open"},
            **{"x-cloak": True},
        ),
        x_data="{ open: false }",
        cls="relative inline-flex",
        **{"@click.outside": "open = false"},
    )


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
        Icon(icon, size=14, cls="inline mr-1"),
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
                Icon(icon, size=12, cls="inline mr-1"),
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
                Icon(icon, size=10, cls="inline"),
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
                description=f"Sync your Obsidian vault to add {domain}s, or adjust your filters.",
                action_text="Sync Vault",
                action_href="/submissions/sync",
            ),
            id=list_id,
        )
    cards = [
        card_fn(item, connections_map.get(item.uid, []) if connections_map else [])
        for item in items
    ]
    return Div(*cards, id=list_id, cls="mt-4 space-y-3")
