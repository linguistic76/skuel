"""Type-narrowing accessors for ListContext.

ListContext stores ``entities: list[Any]`` because the FilteredContextProvider
protocol serves all domain types through one interface.  These helpers give
consumers type-safe access without complicating the protocol.

Usage::

    from core.utils.list_context_helpers import (
        get_entities,
        get_stats,
        get_metadata,
    )

    ctx = result.value
    tasks = get_entities(ctx, Task)  # list[Task]
    stats = get_stats(ctx)  # dict[str, int | float]
    meta = get_metadata(ctx)  # dict[str, Any]
"""

from __future__ import annotations

from typing import Any

from core.ports.query_types import ListContext


def get_entities[T](ctx: ListContext, _entity_type: type[T]) -> list[T]:
    """Return entities from *ctx*, narrowed to *_entity_type* for MyPy."""
    return ctx.get("entities", [])


def get_stats(ctx: ListContext) -> dict[str, int | float]:
    """Return stats dict with safe default."""
    return ctx.get("stats", {})


def get_metadata(ctx: ListContext) -> dict[str, Any]:
    """Return metadata dict with safe default."""
    return ctx.get("metadata", {})
