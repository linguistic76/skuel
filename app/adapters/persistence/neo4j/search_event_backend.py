"""
Search Event Backend
====================

Persistence for :SearchEvent nodes — the discovery-analytics behavioral log.

:SearchEvent is a plain infrastructure node (like :ContentChunk/:AuthEvent),
NOT an EntityType, so this backend does NOT extend UniversalNeo4jBackend —
it takes a Neo4jQueryExecutor directly (InsightBackend precedent).

Write path: SearchRouter publishes `search.executed` → SearchEventRecorder
(core/services/search_event_recorder.py) → record_search_event here.
Read path: content-gap aggregation for the admin surface.

See: /docs/roadmap/DISCOVERY_ANALYTICS_ROADMAP.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ports.query_types import SearchGapRow, to_search_gap_rows
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.ports.query_types import SearchEventProps


class SearchEventBackend:
    """Backend for :SearchEvent persistence and aggregation."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def record_search_event(self, props: SearchEventProps) -> Result[None]:
        """Persist one :SearchEvent node from a search.executed event's properties."""
        result = await self._executor.execute_query(
            """
            CREATE (e:SearchEvent {
                uid: $uid,
                query_text: $query_text,
                query_normalized: $query_normalized,
                user_uid: $user_uid,
                entry_point: $entry_point,
                domains: $domains,
                filters_json: $filters_json,
                result_count: $result_count,
                zero_results: $zero_results,
                semantic_boost: $semantic_boost,
                created_at: datetime($created_at)
            })
            RETURN e.uid AS uid
            """,
            dict(props),
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

    async def get_search_gaps(
        self,
        *,
        max_result_count: int = 2,
        days: int = 90,
        limit: int = 50,
    ) -> Result[list[SearchGapRow]]:
        """Aggregate low/zero-result searches grouped by normalized query text."""
        result = await self._executor.execute_query(
            """
            MATCH (e:SearchEvent)
            WHERE e.result_count <= $max_result_count
              AND e.created_at >= datetime() - duration({days: $days})
            RETURN e.query_normalized AS query,
                   count(e) AS searches,
                   sum(CASE WHEN e.zero_results THEN 1 ELSE 0 END) AS zero_count,
                   avg(e.result_count) AS avg_results,
                   toString(max(e.created_at)) AS last_seen,
                   collect(DISTINCT e.entry_point) AS entry_points
            ORDER BY searches DESC, last_seen DESC
            LIMIT $limit
            """,
            {"max_result_count": max_result_count, "days": days, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_search_gap_rows(result.value or []))

    async def count_search_events(self) -> Result[int]:
        """Total :SearchEvent count — the 1000+ trigger for deferred analytics phases."""
        result = await self._executor.execute_query(
            "MATCH (e:SearchEvent) RETURN count(e) AS total",
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        return Result.ok(int(rows[0]["total"]) if rows else 0)
