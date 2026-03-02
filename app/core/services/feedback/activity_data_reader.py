"""
ActivityDataReader
==================

Single source of truth for reading user activity data over a time window.

Replaces two independent queries:
    _ACTIVITY_QUERY  (ProgressFeedbackGenerator) — 6 domains, rich fields
    _SNAPSHOT_QUERY  (ActivityReportService)     — 4 domains, simple fields

_ACTIVITY_QUERY is a strict superset of _SNAPSHOT_QUERY. One query,
two consumers that format the results differently for their purposes.

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports import QueryExecutor

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.services.feedback.activity_data_reader")

# Single combined query — three CALL {} subqueries in one round-trip.
#
# Fetches tasks/goals/habits/principles, events, and choices together.
# Each CALL {} block returns an empty list when no entities match, so the
# outer RETURN always produces one row.
#
# Parameters:
#   $user_uid     — user whose activity to read
#   $entity_types — list of entity type strings for the main block
#   $start/$end   — datetime ISO strings (main block + choices)
#   $start_date/$end_date — date ISO strings (events block)
_ACTIVITY_QUERY: str = """
MATCH (u:User {uid: $user_uid})

CALL {
    WITH u
    OPTIONAL MATCH (u)-[:OWNS]->(e:Entity)
    WHERE e.entity_type IN $entity_types
      AND e.updated_at >= datetime($start) AND e.updated_at <= datetime($end)
    OPTIONAL MATCH (e)-[:FULFILLS_GOAL]->(g:Goal)
    OPTIONAL MATCH (e)-[:APPLIES_KNOWLEDGE]->(ku:Entity)
    WITH e, collect(DISTINCT g.title) AS goal_titles, collect(DISTINCT ku.title) AS ku_titles
    RETURN collect(CASE WHEN e IS NOT NULL THEN {
        entity_type: e.entity_type,
        uid: e.uid,
        title: e.title,
        status: e.status,
        progress: e.progress,
        streak: e.streak_count,
        alignment: e.current_alignment,
        strength: e.strength,
        category: e.principle_category,
        priority: e.priority,
        goal_titles: goal_titles,
        ku_titles: ku_titles
    } ELSE null END) AS main_records
}

CALL {
    WITH u
    OPTIONAL MATCH (u)-[:OWNS]->(e:Event)
    WHERE e.event_date >= date($start_date) AND e.event_date <= date($end_date)
    RETURN collect(CASE WHEN e IS NOT NULL THEN {
        uid: e.uid,
        title: e.title,
        status: e.status,
        event_type: e.event_type,
        is_milestone: coalesce(e.is_milestone_event, false)
    } ELSE null END) AS event_records
}

CALL {
    WITH u
    OPTIONAL MATCH (u)-[:OWNS]->(c:Choice)
    WHERE c.created_at >= datetime($start) AND c.created_at <= datetime($end)
    OPTIONAL MATCH (c)-[:INFORMED_BY_PRINCIPLE]->(p:Principle)
    WITH c, collect(DISTINCT p.title) AS principle_titles
    RETURN collect(CASE WHEN c IS NOT NULL THEN {
        uid: c.uid,
        title: c.title,
        principle_titles: principle_titles
    } ELSE null END) AS choice_records
}

RETURN main_records, event_records, choice_records
"""

_MAIN_DOMAIN_ENTITY_TYPES: dict[str, str] = {
    "tasks": "task",
    "goals": "goal",
    "habits": "habit",
    "principles": "principle",
}


@dataclass(frozen=True)
class ActivityData:
    """Raw activity records from a single database round-trip.

    Typed container returned by ActivityDataReader.read().
    Consumers (ProgressFeedbackGenerator, ActivityReportService) format
    this into their domain-specific output shapes.
    """

    main_records: list[dict[str, Any]] = field(default_factory=list)
    event_records: list[dict[str, Any]] = field(default_factory=list)
    choice_records: list[dict[str, Any]] = field(default_factory=list)


class ActivityDataReader:
    """
    Read-only query layer for user activity data over a time window.

    Single source of truth for the Cypher query that fetches activity
    data. Used by ProgressFeedbackGenerator and ActivityReportService
    to avoid issuing independent queries for the same underlying data.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        self.executor = executor

    async def read(
        self,
        user_uid: str,
        start_date: datetime,
        end_date: datetime,
        domains: list[str] | None = None,
    ) -> Result[ActivityData]:
        """
        Fetch user activity data in a single round-trip.

        Args:
            user_uid: User whose activity to read
            start_date: Window start (inclusive)
            end_date: Window end (inclusive)
            domains: Which activity domains to include (None = all 6)

        Returns:
            Result[ActivityData] — raw records, unformatted
        """
        include_all = domains is None
        entity_types = [
            v
            for k, v in _MAIN_DOMAIN_ENTITY_TYPES.items()
            if include_all or k in (domains or [])
        ]

        result = await self.executor.execute_query(
            _ACTIVITY_QUERY,
            {
                "user_uid": user_uid,
                "entity_types": entity_types,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat(),
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        rows = result.value or []
        if not rows:
            return Result.ok(ActivityData())

        row = rows[0]
        return Result.ok(
            ActivityData(
                main_records=[r for r in (row.get("main_records") or []) if r],
                event_records=[r for r in (row.get("event_records") or []) if r],
                choice_records=[r for r in (row.get("choice_records") or []) if r],
            )
        )
