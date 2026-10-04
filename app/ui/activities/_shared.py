"""Shared helpers for Activity Domain UI views.

Extracted from the 6 Activity Domain view files to eliminate duplication.
Domain-specific logic stays in each domain's *_views.py file.

Usage:
    from ui.activities._shared import safe_id, PriorityBadgeDropdown, ConnectionRows
"""

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Button, Div, Li, Small, Span, Ul

from core.models.enums import Priority
from ui.components import Icon
from ui.feedback import Badge, BadgeT, PriorityBadge
from ui.patterns.empty_state import EmptyState
from ui.primitives import dropdown_menu, section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.ports.query_types import EntityConnection


def _by_heading(connections: Sequence[EntityConnection]) -> dict[str, list[EntityConnection]]:
    """Group page links by heading, in the order the reader gives them."""
    groups: dict[str, list[EntityConnection]] = {}
    for conn in connections:
        groups.setdefault(conn["heading"], []).append(conn)
    return groups


def _connection_link(conn: EntityConnection, cls: str) -> FT:
    """The far end's title, linked to its page when it has one."""
    base_href = CONNECTION_ICONS.get(conn["connected_type"], ("link", "#"))[1]
    title = conn["title"] or conn["connected_uid"]
    if base_href == "#":
        return Span(title, cls=cls)
    return A(title, href=f"{base_href}{conn['connected_uid']}", cls=f"hover:underline {cls}")


def _connection_icon(conn: EntityConnection, size: int) -> FT:
    """The far end's kind, as an icon that keeps its size beside a wrapping title."""
    return Icon(
        CONNECTION_ICONS.get(conn["connected_type"], ("link", "#"))[0], size=size, cls="shrink-0"
    )


def ConnectionsSection(connections: Sequence[EntityConnection]) -> FT:
    """Detail-page 'Connections' block: the page's links, one list per heading.

    Each heading is this domain's name for a link (``page_heading``, ADR-090 §2), so
    two links to the same kind of entity — an event celebrating a goal and one
    contributing to it — are listed apart. Renders an empty Div when there are none.
    """
    if not connections:
        return Div()
    sections = [
        Div(
            Small(heading, cls="text-muted-foreground text-sm block mb-2"),
            Ul(
                *[
                    Li(
                        _connection_icon(conn, 12),
                        _connection_link(conn, "text-muted-foreground"),
                        cls="flex items-center gap-2 py-1",
                    )
                    for conn in conns
                ],
                cls="divide-y",
            ),
            cls="mb-3",
        )
        for heading, conns in _by_heading(connections).items()
    ]
    return Div(section_label("Connections"), *sections, cls="my-4")


def ConnectionRows(connections: Sequence[EntityConnection]) -> FT:
    """List-card links: one compact line per heading, its titles after it.

    The card's half of the detail page's :func:`ConnectionsSection` — the same
    headings, so a link shows on the card under the name the page gives it.
    """
    if not connections:
        return Span()
    rows = [
        Div(
            Span(f"{heading}:", cls="text-muted-foreground mr-1"),
            *[
                Span(
                    _connection_icon(conn, 10),
                    _connection_link(conn, ""),
                    cls="inline-flex items-center gap-1 mr-2",
                )
                for conn in conns
            ],
            cls="text-sm",
        )
        for heading, conns in _by_heading(connections).items()
    ]
    return Div(*rows, cls="mt-2 space-y-0.5")


def tag_badges(tags: Sequence[str], limit: int | None = None) -> list[FT]:
    """Secondary badges for an entity's tags, optionally capped at ``limit``.

    Cards cap at 5; detail pages render the full set.
    """
    shown = tags[:limit] if limit is not None else tags
    return [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in shown]


def TagsBlock(tags: Sequence[str]) -> FT:
    """Detail-page 'Tags' block. Renders an empty Div when there are no tags."""
    if not tags:
        return Div()
    return Div(
        Small("Tags", cls="text-muted-foreground block mb-2"),
        *tag_badges(tags),
        cls="my-4",
    )


def MetadataField(label: str, *value: FT) -> FT:
    """Label + value pair for detail page metadata grids."""
    return Div(
        Small(label, cls="text-muted-foreground block text-sm"),
        *value,
    )


def safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


def PriorityBadgeDropdown(
    uid: str,
    priority: str | None,
    domain: str,
    singular: str,
) -> FT:
    """Interactive priority badge: click opens a dropdown of the three priority levels.

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
            cls="w-36",
            align="left",
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
    "learning_path": ("map", "/lp/"),
}


def CurriculumOriginField(ps_uid: str, ps_title: str) -> FT:
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


def ActivityList(
    items: list,
    domain: str,
    card_fn: Callable,
    connections_map: Mapping[str, list[EntityConnection]] | None = None,
    *,
    empty_state: FT | None = None,
    list_id: str | None = None,
) -> FT:
    """Generic list renderer for any Activity Domain.

    Eliminates the near-identical {Domain}List functions across the 6 view files.
    Each domain's {Domain}List becomes a one-liner delegating here.

    Args:
        items: Domain entities to render.
        domain: Singular domain slug (e.g. "task", "goal"). Used for the list
            container id and EmptyState copy.
        card_fn: Domain card component (e.g. TaskCard).
        connections_map: Each entity's page links, keyed by UID (ADR-090 §2).
        empty_state: What to render when ``items`` is empty; the default is the
            domain list page's "sync your vault" state — a surface with its own
            reading of an empty list (the day view) passes its own.
        list_id: The list container's DOM id; defaults to ``{domain}-list``. A
            page rendering more than one list of the same domain passes distinct
            ids, so HTMX swaps target the right one.
    """
    list_id = list_id or f"{domain}-list"
    if not items:
        return Div(
            empty_state
            if empty_state is not None
            else EmptyState(
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
