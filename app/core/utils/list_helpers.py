"""
Generic List Helpers for Entity Filtering and Sorting
=====================================================

Config-driven sort and filter functions that eliminate per-domain boilerplate.
Each service facade defines a declarative config dict; these functions execute it.
"""

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any

# -- Type aliases (PEP 695) --------------------------------------------------

type SortSpec = tuple[Callable[[Any], Any], bool]  # (key_func, reverse)
type SortConfig = dict[str, SortSpec]
type FilterPredicate = Callable[[Any], bool]
type FilterConfig = dict[str, FilterPredicate]


# -- Generic sort/filter -----------------------------------------------------


def apply_entity_sort(
    entities: list[Any],
    sort_by: str,
    config: SortConfig,
    default: str,
) -> list[Any]:
    """Sort entities using a declarative config dict.

    Each config entry maps a sort_by string to a (key_func, reverse) tuple.
    Falls back to *default* sort if *sort_by* is not in config.
    """
    key_func, reverse = config.get(sort_by, config[default])
    return sorted(entities, key=key_func, reverse=reverse)


def apply_entity_filter(
    entities: list[Any],
    filter_value: str,
    config: FilterConfig,
) -> list[Any]:
    """Filter entities using a declarative config dict.

    Each config entry maps a filter_value string to a predicate function.
    If *filter_value* is not in config (e.g. ``"all"``), returns all entities.
    """
    predicate = config.get(filter_value)
    if predicate is None:
        return entities
    return [e for e in entities if predicate(e)]


# -- Sort-key helpers not already in sort_functions.py -----------------------


def get_sequence_attr(item: Any) -> int:
    """Sort key: sequence attribute, defaulting to 0."""
    return getattr(item, "sequence", 0) or 0


def get_event_sort_datetime(event: Any) -> datetime:
    """Sort key: combine event_date + start_time into a single datetime.

    Handles both proper ``date``/``time`` objects and string representations.
    """
    event_date = getattr(event, "event_date", None) or date.today()
    if not isinstance(event_date, date) and getattr(event_date, "year", None) is not None:
        event_date = date(event_date.year, event_date.month, event_date.day)
    start_time_val = getattr(event, "start_time", None)
    if start_time_val is None:
        return datetime.combine(event_date, time(0, 0))
    if not isinstance(start_time_val, time) and getattr(start_time_val, "hour", None) is not None:
        start_time_val = time(
            start_time_val.hour,
            start_time_val.minute,
            getattr(start_time_val, "second", 0) or 0,
        )
    elif isinstance(start_time_val, str):
        try:
            start_time_val = datetime.strptime(start_time_val, "%H:%M:%S").time()
        except ValueError:
            start_time_val = time(0, 0)
    return datetime.combine(event_date, start_time_val)
