"""
Explore Filtering & Sorting
============================

Pure functions for filtering and sorting the Explore discovery grid.
No async, no service calls — operates on (item, entity_type) tuples.
"""

from typing import Any


def created_at_key(item: Any) -> str:
    """Sort key: created_at timestamp as string (handles mixed Neo4j DateTimes)."""
    val = getattr(item, "created_at", None)
    if val is None:
        return ""
    return str(val)


def title_key(item: Any) -> str:
    """Sort key: lowercased title."""
    return (getattr(item, "title", None) or "").lower()


def sort_by_title(pair: tuple[Any, str]) -> str:
    """Sort key for (item, entity_type) pairs by title."""
    return title_key(pair[0])


def sort_by_created_at(pair: tuple[Any, str]) -> str:
    """Sort key for (item, entity_type) pairs by created_at."""
    return created_at_key(pair[0])


def filter_items(
    items: list[tuple[Any, str]],
    q: str,
    type_filter: str,
    tag: str,
    sort: str,
) -> list[tuple[Any, str]]:
    """Filter and sort unified (item, entity_type) list."""
    results = items

    if type_filter:
        results = [(item, et) for item, et in results if et == type_filter]

    if tag:
        tag_lower = tag.lower()
        results = [
            (item, et)
            for item, et in results
            if any(t.lower() == tag_lower for t in (getattr(item, "tags", None) or ()))
        ]

    if q:
        q_lower = q.lower()
        results = [
            (item, et)
            for item, et in results
            if q_lower in (getattr(item, "title", None) or "").lower()
            or q_lower in (getattr(item, "description", None) or "").lower()
            or any(q_lower in t.lower() for t in (getattr(item, "tags", None) or ()))
        ]

    if sort == "title":
        results.sort(key=sort_by_title)
    else:
        results.sort(key=sort_by_created_at, reverse=True)

    return results
