"""Hub page components — shared card grid infrastructure for hub pages.

Hub pages are standalone pages that organize navigation through card grids.
Profile is THE main hub; domain pages (KU, PathSteps, Submissions, Reports)
are rich functional hubs that may use these components for sections.

See: /docs/patterns/HUB_PAGE_PATTERN.md
"""

from __future__ import annotations

from dataclasses import dataclass

from fasthtml.common import A, Div, P, Span

from core.ports.query_types import OrganizerResult, RootOrganizerResult


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
        cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow block",
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
# Graph-driven card bridges
# ---------------------------------------------------------------------------


def hub_cards_from_organizers(
    children: list[OrganizerResult],
    href_template: str = "/ku/{uid}",
    default_icon: str = "\U0001f4d6",
    default_description: str = "",
) -> list[HubCardData]:
    """Convert ORGANIZES query results into HubCardData list.

    Args:
        children: Results from get_organized_children().
        href_template: URL template with {uid} placeholder.
        default_icon: Fallback icon for cards.
        default_description: Fallback description for cards.

    Returns:
        List of HubCardData sorted by order.
    """

    def by_order(c: OrganizerResult) -> int:
        return c.get("order") or 0

    sorted_children = sorted(children, key=by_order)
    return [
        HubCardData(
            icon=default_icon,
            name=child["title"],
            href=href_template.format(uid=child["uid"]),
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
