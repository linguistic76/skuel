"""Shared skeleton for get_filtered_context() across all domain facades.

Domains provide callables for domain-specific stats, filters, and sorting.
The helper enforces the common pattern: fetch → stats → filter → sort → return.

See: /docs/patterns/FILTERED_CONTEXT_PATTERN.md (planned)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.ports.query_types import ListContext
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def build_filtered_context(
    fetch_all: Callable[[], Awaitable[Result[list[Any]]]],
    compute_stats: Callable[[list[Any]], dict[str, int | float]],
    apply_filters: Callable[[list[Any]], list[Any]],
    apply_sort: Callable[[list[Any], str], list[Any]],
    sort_by: str,
    compute_metadata: Callable[[list[Any]], dict[str, Any]] | None = None,
) -> Result[ListContext]:
    """Build a filtered, sorted entity list with pre-filter stats.

    Args:
        fetch_all: Async callable that fetches ALL entities (pre-filtering).
        compute_stats: Computes stats dict from the full entity set (before filtering).
        apply_filters: Applies domain-specific filters. Should capture filter params
            via closure or functools.partial.
        apply_sort: Sorts filtered entities by the given sort_by field.
        sort_by: Sort field name, passed to apply_sort.
        compute_metadata: Optional. Computes domain-specific metadata from the full
            entity set (e.g., tasks' project/assignee lists for UI dropdowns).

    Returns:
        Result[ListContext] with entities, stats, and optional metadata.
    """
    all_result = await fetch_all()
    if all_result.is_error:
        return Result.fail(all_result)
    all_entities = all_result.value

    stats = compute_stats(all_entities)
    filtered = apply_filters(all_entities)
    sorted_entities = apply_sort(filtered, sort_by)

    context: ListContext = {"entities": sorted_entities, "stats": stats}
    if compute_metadata is not None:
        context["metadata"] = compute_metadata(all_entities)
    return Result.ok(context)
