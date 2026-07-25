"""
Search Domain Events
====================

Events published by SearchRouter for search behavior logging.

Event Catalog:
- search.executed - A search ran through one of SearchRouter's external
  entry points (faceted / intelligent / advanced)

Subscribers:
- SearchEventRecorder (persists :SearchEvent nodes for discovery analytics —
  content-gap analysis now, clustering/temporal/CTR once 1000+ events exist;
  see /docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md)
"""

from dataclasses import dataclass

from core.events.base import BaseEvent
from core.models.type_hints import UserUID


@dataclass(frozen=True)
class SearchExecuted(BaseEvent):
    """
    Published when a search runs through a SearchRouter external entry point.

    One event per external search — internal fan-out (intelligent_search's
    per-domain faceted_search calls, cross-domain sweeps) never publishes.
    Empty/whitespace-only queries are not published: filter-only searches
    carry no gap signal, and /search/results short-circuits them anyway.

    Subscribers:
    - SearchEventRecorder (persist :SearchEvent for discovery analytics)
    """

    query_text: str
    user_uid: UserUID | None
    entry_point: str  # "faceted" | "intelligent" | "advanced"
    result_count: int
    zero_results: bool
    semantic_boost: bool = False
    domains: tuple[str, ...] = ()  # requested domain scope; () = cross-domain sweep
    filters_json: str = "{}"  # json.dumps of active property filters

    @property
    def event_type(self) -> str:
        return "search.executed"
