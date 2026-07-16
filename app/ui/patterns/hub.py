"""Hub page components — shared card grid infrastructure for hub pages.

Hub pages are standalone pages that organize navigation through card grids.
Profile is THE main hub; domain pages (KU, PathSteps, Submissions, Reports)
are rich functional hubs that may use these components for sections.

See: /docs/patterns/HUB_PAGE_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fasthtml.common import H2, A, Details, Div, P, Span, Summary

from core.ports.query_types import OrganizerResult, RootOrganizerResult
from ui.components import ButtonT, Icon
from ui.patterns.skeleton import SkeletonList
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from collections.abc import Callable

    from fasthtml.common import FT


@dataclass(frozen=True)
class HubCardData:
    """Data for a single hub card."""

    icon: str
    name: str
    href: str
    description: str
    badge: str | int | None = None


def HubCard(card: HubCardData) -> A:
    """Single hub card — icon + title + description + optional badge, wrapped in <A>."""
    title_row_items: list[Span] = [
        Span(card.icon, cls="text-xl"),
        Span(card.name, cls="text-base font-semibold text-foreground"),
    ]

    if card.badge is not None and card.badge != 0:
        title_row_items.append(
            Span(
                str(card.badge),
                cls="ml-auto text-xs font-medium bg-primary/10 text-primary px-2 py-0.5 rounded-full",
            )
        )

    return A(
        Div(
            Div(*title_row_items, cls="flex items-center gap-2"),
            cls="mb-3",
        ),
        P(card.description, cls="text-sm text-muted-foreground"),
        href=card.href,
        cls="bg-card border border-border rounded-[12px] p-[22px] shadow-sm hover:shadow-md transition-shadow block",
    )


def MocCard(
    title: str,
    description: str,
    href: str,
    icon: str,
    icon_bg: str = "bg-muted",
) -> A:
    """MOC root-page card — icon tile + title + description, wrapped in <A>.

    Used by the MOC hub roots (/library, /submissions, /gradebook) to link
    their sub-pages.
    """
    return A(
        Div(
            Div(
                Icon(icon, size=28),
                cls=f"w-14 h-14 rounded-2xl {icon_bg} flex items-center justify-center mb-4",
            ),
            H2(title, cls="text-lg font-semibold mb-1"),
            P(description, cls="text-sm text-muted-foreground"),
            cls="p-6",
        ),
        href=href,
        cls=(
            "block border border-border rounded-2xl bg-card "
            "hover:border-primary/40 hover:shadow-md transition-all duration-150"
        ),
    )


def HubSection(title: str | None, cards: list[HubCardData], cols: int = 2) -> Div:
    """Section header + responsive card grid.

    Args:
        title: Section label (uppercase). None for flat grids without header.
        cards: Card data to render.
        cols: Grid columns at sm breakpoint (2, 3, or 4).
    """
    col_classes = {
        2: "grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5",
        3: "grid grid-cols-1 sm:grid-cols-3 gap-4 lg:gap-5",
        4: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-5",
    }
    grid_cls = col_classes.get(cols, col_classes[2])

    parts: list[Span | Div] = []
    if title is not None:
        parts.append(
            Span(
                title,
                cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground",
            )
        )

    parts.append(Div(*[HubCard(c) for c in cards], cls=grid_cls))
    return Div(*parts, cls="mb-6")


# ---------------------------------------------------------------------------
# Graph-driven card bridges
# ---------------------------------------------------------------------------


def HubContainer(card: HubCardData) -> A:
    """Hub container — a substantial navigational block for hub pages.

    Bigger than HubCard: more padding, larger icon, full description paragraph,
    arrow affordance suggesting you are entering a section.
    """
    title_row: list[Span | P] = [
        Span(card.icon, cls="text-2xl"),
        Span(card.name, cls="text-lg font-semibold text-foreground"),
    ]

    if card.badge is not None and card.badge != 0:
        title_row.append(
            Span(
                str(card.badge),
                cls="ml-auto text-xs font-medium bg-primary/10 text-primary px-2 py-0.5 rounded-full",
            )
        )

    return A(
        Div(*title_row, cls="flex items-center gap-3 mb-3"),
        P(card.description, cls="text-sm text-muted-foreground leading-relaxed"),
        Div(
            Span("→", cls="text-muted-foreground/60 text-lg"),
            cls="flex justify-end mt-4",
        ),
        href=card.href,
        cls="bg-background rounded-xl p-6 sm:p-8 shadow-sm hover:shadow-md transition-shadow block border border-border/50",
    )


def HubContainerGrid(cards: list[HubCardData], cols: int = 2) -> Div:
    """Responsive grid of hub containers.

    Args:
        cards: Card data to render as containers.
        cols: Grid columns at sm breakpoint (2 or 3).
    """
    col_classes = {
        2: "grid grid-cols-1 sm:grid-cols-2 gap-5 lg:gap-6",
        3: "grid grid-cols-1 sm:grid-cols-3 gap-5 lg:gap-6",
    }
    grid_cls = col_classes.get(cols, col_classes[2])
    return Div(*[HubContainer(c) for c in cards], cls=grid_cls)


# ---------------------------------------------------------------------------
# HTMX-loaded hub domain blocks (Activity, GradeBook, Library hubs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubBlockData:
    """Configuration for one domain block on a hub page."""

    label: str
    slug: str
    icon: str  # Lucide icon name (rendered via Icon)
    color: str  # hex color for header
    href: str  # Target for the header label link (primary action)
    preview_url: str | None = None  # HTMX endpoint; None = OOB-populated by a combined endpoint
    view_all_href: str | None = None  # Override for "View all →"; falls back to href


def HubPreviewCard(
    title: str,
    href: str,
    badge: FT | None = None,
    description: str | None = None,
) -> A:
    """Compact preview card — entity title first, optional description snippet
    and badge in a meta row below, links to detail."""
    parts: list[Span | Div | FT] = [
        Span(
            title,
            cls="text-sm font-semibold text-foreground line-clamp-1 leading-snug",
        )
    ]
    if description:
        parts.append(
            Span(
                description,
                cls="text-xs text-muted-foreground line-clamp-2 leading-snug",
            )
        )
    if badge is not None:
        parts.append(Div(badge, cls="mt-auto flex items-center gap-1.5"))
    return A(
        *parts,
        href=href,
        cls=(
            "flex flex-col gap-1 p-2.5 rounded-lg border border-border "
            "bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors "
            "min-h-[60px] no-underline"
        ),
    )


def HubPreviewGrid(cards: list[A]) -> Div:
    """Responsive preview card grid — 2 columns on mobile, 3 on sm+."""
    return Div(*cards, cls="grid grid-cols-2 sm:grid-cols-3 gap-2")


def HubPreviewEmpty(domain: str) -> Div:
    """Empty state for a preview block."""
    return Div(
        P(f"No {domain} yet", cls="text-sm text-foreground/40 text-center py-3"),
    )


_HUB_BLOCK_CLS = "pb-5 mb-5 border-b border-border last:border-b-0 last:mb-0 last:pb-0"


def _preview_panel(block: HubBlockData, trigger: str) -> Div:
    """HTMX lazy-loaded card area — self-loading when preview_url set, OOB target otherwise.

    ``intersect once`` (the trigger at both call sites) only fires when the
    panel gains a layout box in the viewport, so panels inside hidden tab
    containers or closed ``<details>`` defer their fetch until revealed.
    """
    return Div(
        SkeletonList(count=3),
        id=f"hub-panel-{block.slug}",
        **(
            {
                "hx_get": block.preview_url,
                "hx_trigger": trigger,
                "hx_swap": "innerHTML",
            }
            if block.preview_url is not None
            else {}
        ),
    )


def HubDomainBlock(block: HubBlockData) -> Div:
    """A single domain block: colored header + HTMX lazy-loaded preview area."""
    return Div(
        # Domain header — icon + title + "View all" link
        Div(
            A(
                Icon(block.icon, cls="size-4"),
                Span(
                    block.label,
                    cls="text-sm font-semibold uppercase tracking-wider",
                ),
                href=block.href,
                cls="flex items-center gap-2 no-underline hover:opacity-80 transition-opacity",
                style=f"color: {block.color};",
            ),
            ButtonLink(
                "View all \u2192",
                href=block.view_all_href or block.href,
                cls=ButtonT.ghost,
                size="xs",
            ),
            cls="flex items-center justify-between mb-3",
        ),
        _preview_panel(block, "intersect once"),
        cls=_HUB_BLOCK_CLS,
    )


def HubDomainBlockList(blocks: list[HubBlockData]) -> Div:
    """Vertical stack of domain blocks."""
    return Div(*[HubDomainBlock(b) for b in blocks])


def HubAccordionBlock(block: HubBlockData, open: bool = False) -> FT:
    """Collapsible domain block — native ``<details>``/``<summary>``.

    The whole summary row toggles (label is a Span, not a link); "View all"
    is the sole navigation and stops propagation so it doesn't also toggle.
    The preview panel's ``intersect once`` trigger defers the HTMX fetch until
    the block is actually open AND visible — closed accordions cost nothing.
    """
    return Details(
        Summary(
            Div(
                Icon(
                    "chevron-right",
                    cls="size-4 transition-transform group-open:rotate-90",
                ),
                Icon(block.icon, cls="size-4"),
                Span(
                    block.label,
                    cls="text-sm font-semibold uppercase tracking-wider",
                ),
                cls="flex items-center gap-2",
                style=f"color: {block.color};",
            ),
            ButtonLink(
                "View all →",
                href=block.view_all_href or block.href,
                cls=ButtonT.ghost,
                size="xs",
                **{"@click.stop": ""},
            ),
            cls=(
                "list-none [&::-webkit-details-marker]:hidden cursor-pointer "
                "select-none flex items-center justify-between mb-3"
            ),
        ),
        _preview_panel(block, "intersect once"),
        open=open,
        cls=f"group {_HUB_BLOCK_CLS}",
    )


def HubAccordionBlockList(blocks: list[HubBlockData], open_first: bool = True) -> Div:
    """Vertical stack of accordion blocks; the first starts open by default."""
    return Div(*[HubAccordionBlock(b, open=open_first and i == 0) for i, b in enumerate(blocks)])


# ---------------------------------------------------------------------------
# Graph-driven card bridges
# ---------------------------------------------------------------------------


def hub_cards_from_organizers(
    children: list[OrganizerResult],
    href_template: str = "/ku/{uid}",
    default_icon: str = "\U0001f4d6",
    default_description: str = "",
    href_for: Callable[[OrganizerResult], str] | None = None,
) -> list[HubCardData]:
    """Convert ORGANIZES query results into HubCardData list.

    Args:
        children: Results from get_organized_children().
        href_template: URL template with {uid} placeholder.
        default_icon: Fallback icon for cards.
        default_description: Fallback description for cards.
        href_for: Per-child href resolver — overrides ``href_template`` when
            children span entity types (e.g. a user-entry MOC organizing
            tasks, Kus, and entries; see ``ui/patterns/entity_links.py``).

    Returns:
        List of HubCardData sorted by order.
    """

    def by_order(c: OrganizerResult) -> int:
        return c.get("order") or 0

    def child_href(c: OrganizerResult) -> str:
        if href_for is not None:
            return href_for(c)
        return href_template.format(uid=c["uid"])

    sorted_children = sorted(children, key=by_order)
    return [
        HubCardData(
            icon=default_icon,
            name=child["title"],
            href=child_href(child),
            description=default_description,
        )
        for child in sorted_children
    ]


def hub_cards_from_root_organizers(
    roots: list[RootOrganizerResult],
    href_template: str = "/ku/{uid}",
    default_icon: str = "\U0001f4d6",
    default_description: str = "",
) -> list[HubCardData]:
    """Convert root organizer results into HubCardData list.

    child_count maps to the badge slot.

    Args:
        roots: Results from list_root_organizers().
        href_template: URL template with {uid} placeholder.
        default_icon: Fallback icon for cards.
        default_description: Fallback description for cards.

    Returns:
        List of HubCardData with child_count as badge.
    """
    return [
        HubCardData(
            icon=default_icon,
            name=root["title"],
            href=href_template.format(uid=root["uid"]),
            description=default_description,
            badge=root["child_count"] or None,
        )
        for root in roots
    ]
