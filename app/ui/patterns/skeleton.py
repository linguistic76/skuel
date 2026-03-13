"""Skeleton loader components for loading states.

These components provide animated placeholders that improve perceived
performance during content loading.

Usage:
    from ui.patterns.skeleton import SkeletonCard, SkeletonList

    # Show skeleton during HTMX load
    Div(
        id="content",
        hx_get="/api/data",
        hx_trigger="load",
        # Initial content: skeleton
        SkeletonList(count=5),
    )
"""

from fasthtml.common import Div
from ui.cards import Card


def SkeletonCard() -> Div:
    """Animated skeleton for card loading state.

    Returns:
        A div with skeleton animation representing a card
    """
    return Card(
        # Title skeleton
        Div(cls="h-6 bg-secondary rounded w-3/4 animate-pulse"),
        # Content line 1
        Div(cls="h-4 bg-secondary rounded w-full mt-2 animate-pulse"),
        # Content line 2
        Div(cls="h-4 bg-secondary rounded w-5/6 mt-2 animate-pulse"),
        cls="bg-background shadow-sm p-4",
    )


def SkeletonList(count: int = 3) -> Div:
    """Skeleton for list loading state.

    Args:
        count: Number of skeleton cards to show

    Returns:
        A div containing multiple skeleton cards
    """
    return Div(
        *[SkeletonCard() for _ in range(count)],
        cls="space-y-4",
    )


def SkeletonStats() -> Div:
    """Skeleton for stats/metrics loading state.

    Returns:
        A div with skeleton animation representing a stats card
    """
    return Card(
        Div(
            # Stat 1
            Div(
                Div(cls="h-4 bg-secondary rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-secondary rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            # Stat 2
            Div(
                Div(cls="h-4 bg-secondary rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-secondary rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            # Stat 3
            Div(
                Div(cls="h-4 bg-secondary rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-secondary rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            cls="flex justify-around w-full",
        ),
        cls="bg-background shadow-sm p-6",
    )


def SkeletonTable(rows: int = 5) -> Div:
    """Skeleton for table loading state.

    Args:
        rows: Number of table rows to show

    Returns:
        A div with skeleton animation representing a table
    """
    return Card(
        # Table header
        Div(
            Div(cls="h-4 bg-secondary rounded w-24 animate-pulse"),
            Div(cls="h-4 bg-secondary rounded w-32 animate-pulse"),
            Div(cls="h-4 bg-secondary rounded w-20 animate-pulse"),
            cls="flex justify-between border-b border-border pb-3",
        ),
        # Table rows
        Div(
            *[
                Div(
                    Div(cls="h-4 bg-secondary rounded w-24 animate-pulse"),
                    Div(cls="h-4 bg-secondary rounded w-32 animate-pulse"),
                    Div(cls="h-4 bg-secondary rounded w-20 animate-pulse"),
                    cls="flex justify-between py-3 border-b border-border/50",
                )
                for _ in range(rows)
            ],
            cls="divide-y divide-base-300/50",
        ),
        cls="bg-background shadow-sm p-4",
    )


def SkeletonSidebarItem() -> Div:
    """Skeleton for profile sidebar domain item.

    Returns:
        A div with skeleton animation representing a sidebar domain item
    """
    return Div(
        # Icon + Name
        Div(
            Div(cls="size-5 bg-secondary rounded-full animate-pulse"),
            Div(cls="h-4 bg-secondary rounded w-24 animate-pulse"),
            cls="flex items-center gap-3",
        ),
        # Badges (count, status)
        Div(
            Div(cls="h-6 w-12 bg-secondary rounded-full animate-pulse"),
            Div(cls="h-6 w-16 bg-secondary rounded-full animate-pulse"),
            cls="flex items-center gap-2",
        ),
        cls="flex items-center justify-between p-3 rounded-lg bg-muted/50",
    )


def SkeletonSidebar(domain_count: int = 7) -> Div:
    """Skeleton for profile sidebar with multiple domain items.

    Args:
        domain_count: Number of domain skeleton items (default 7 for Activity Domains)

    Returns:
        A div with skeleton animation representing the full sidebar
    """
    return Div(
        # Header
        Div(
            Div(cls="h-6 bg-secondary rounded w-32 animate-pulse mb-4"),
            cls="mb-6",
        ),
        # Domain items
        Div(
            *[SkeletonSidebarItem() for _ in range(domain_count)],
            cls="space-y-2",
        ),
        cls="p-4",
    )


def SkeletonIntelligence() -> Div:
    """Skeleton for intelligence section (alignment, daily plan, etc).

    Returns:
        A div with skeleton animation representing intelligence cards
    """
    return Div(
        # Alignment breakdown card
        Card(
            Div(cls="h-5 bg-secondary rounded w-48 animate-pulse mb-4"),
            Div(
                *[
                    Div(
                        Div(cls="h-4 bg-secondary rounded w-24 animate-pulse"),
                        Div(cls="h-8 bg-secondary rounded w-16 animate-pulse mt-2"),
                        cls="text-center",
                    )
                    for _ in range(5)
                ],
                cls="grid grid-cols-5 gap-4",
            ),
            cls="bg-background shadow-sm p-6 mb-6",
        ),
        # Daily plan card
        Card(
            Div(cls="h-5 bg-secondary rounded w-40 animate-pulse mb-4"),
            Div(
                *[Div(cls="h-4 bg-secondary rounded w-full animate-pulse") for _ in range(4)],
                cls="space-y-2",
            ),
            cls="bg-background shadow-sm p-6 mb-6",
        ),
        # Synergies card
        Card(
            Div(cls="h-5 bg-secondary rounded w-56 animate-pulse mb-4"),
            Div(
                *[Div(cls="h-4 bg-secondary rounded w-full animate-pulse") for _ in range(3)],
                cls="space-y-2",
            ),
            cls="bg-background shadow-sm p-6",
        ),
    )


def SkeletonDomainView() -> Div:
    """Skeleton for domain-specific view (stats + item list).

    Returns:
        A div with skeleton animation representing a domain view
    """
    return Div(
        # Summary card
        Div(
            Div(cls="h-6 bg-secondary rounded w-32 animate-pulse mb-4"),
            Div(
                *[
                    Div(
                        Div(cls="h-8 bg-secondary rounded w-12 animate-pulse"),
                        Div(cls="h-4 bg-secondary rounded w-16 animate-pulse mt-2"),
                        cls="text-center",
                    )
                    for _ in range(3)
                ],
                cls="grid grid-cols-3 gap-4",
            ),
            cls="p-6 rounded-xl border-2 border-border bg-muted/50 mb-6",
        ),
        # Items list header
        Div(cls="h-5 bg-secondary rounded w-40 animate-pulse mb-4"),
        # Item list
        SkeletonList(count=5),
    )


__all__ = [
    "SkeletonCard",
    "SkeletonList",
    "SkeletonStats",
    "SkeletonTable",
    "SkeletonSidebarItem",
    "SkeletonSidebar",
    "SkeletonIntelligence",
    "SkeletonDomainView",
]
