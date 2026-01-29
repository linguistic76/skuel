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


def SkeletonCard() -> Div:
    """Animated skeleton for card loading state.

    Returns:
        A div with skeleton animation representing a card
    """
    return Div(
        # Title skeleton
        Div(cls="h-6 bg-base-300 rounded w-3/4 animate-pulse"),
        # Content line 1
        Div(cls="h-4 bg-base-300 rounded w-full mt-2 animate-pulse"),
        # Content line 2
        Div(cls="h-4 bg-base-300 rounded w-5/6 mt-2 animate-pulse"),
        cls="card bg-base-100 shadow-sm p-4",
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
    return Div(
        Div(
            # Stat 1
            Div(
                Div(cls="h-4 bg-base-300 rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-base-300 rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            # Stat 2
            Div(
                Div(cls="h-4 bg-base-300 rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-base-300 rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            # Stat 3
            Div(
                Div(cls="h-4 bg-base-300 rounded w-16 animate-pulse"),
                Div(cls="h-8 bg-base-300 rounded w-12 mt-2 animate-pulse"),
                cls="flex flex-col items-center",
            ),
            cls="flex justify-around w-full",
        ),
        cls="card bg-base-100 shadow-sm p-6",
    )


def SkeletonTable(rows: int = 5) -> Div:
    """Skeleton for table loading state.

    Args:
        rows: Number of table rows to show

    Returns:
        A div with skeleton animation representing a table
    """
    return Div(
        # Table header
        Div(
            Div(cls="h-4 bg-base-300 rounded w-24 animate-pulse"),
            Div(cls="h-4 bg-base-300 rounded w-32 animate-pulse"),
            Div(cls="h-4 bg-base-300 rounded w-20 animate-pulse"),
            cls="flex justify-between border-b border-base-300 pb-3",
        ),
        # Table rows
        Div(
            *[
                Div(
                    Div(cls="h-4 bg-base-300 rounded w-24 animate-pulse"),
                    Div(cls="h-4 bg-base-300 rounded w-32 animate-pulse"),
                    Div(cls="h-4 bg-base-300 rounded w-20 animate-pulse"),
                    cls="flex justify-between py-3 border-b border-base-300/50",
                )
                for _ in range(rows)
            ],
            cls="divide-y divide-base-300/50",
        ),
        cls="card bg-base-100 shadow-sm p-4",
    )


__all__ = ["SkeletonCard", "SkeletonList", "SkeletonStats", "SkeletonTable"]
