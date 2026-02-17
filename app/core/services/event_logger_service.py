"""
Event Logger Service
====================

Provides event logging, auditing, and replay capabilities for SKUEL's event-driven architecture.

Features:
- Persistent event logging to database
- Event replay for debugging and recovery
- Event filtering and search
- Analytics and audit trails
- Event stream export

Version: 1.0.0
Date: 2025-10-16
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.events.base import BaseEvent
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import QueryExecutor


@dataclass
class EventLogEntry:
    """
    Persistent log entry for a domain event.

    Stored in database for audit trail and replay.
    """

    log_id: str
    event_type: str
    event_data: dict[str, Any]
    occurred_at: datetime

    # Metadata
    user_uid: str | None = None
    aggregate_id: str | None = None  # Entity UID affected (task_uid, goal_uid, etc.)
    aggregate_type: str | None = None  # "Task", "Goal", "Habit", etc.

    # Audit context
    source_service: str | None = None
    correlation_id: str | None = None  # For tracking related events

    # Replay metadata
    replayed: bool = False
    replay_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "log_id": self.log_id,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "occurred_at": self.occurred_at.isoformat(),
            "user_uid": self.user_uid,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "source_service": self.source_service,
            "correlation_id": self.correlation_id,
            "replayed": self.replayed,
            "replay_count": self.replay_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventLogEntry":
        """Create from dictionary."""
        return cls(
            log_id=data["log_id"],
            event_type=data["event_type"],
            event_data=data["event_data"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            user_uid=data.get("user_uid"),
            aggregate_id=data.get("aggregate_id"),
            aggregate_type=data.get("aggregate_type"),
            source_service=data.get("source_service"),
            correlation_id=data.get("correlation_id"),
            replayed=data.get("replayed", False),
            replay_count=data.get("replay_count", 0),
        )


class EventLoggerService:
    """
    Event logging service for audit trails and event replay.

    Responsibilities:
    - Log all domain events to persistent storage
    - Provide event search and filtering
    - Enable event replay for debugging
    - Generate audit reports
    - Export event streams

    Usage:
        # Subscribe to all events for logging
        event_bus.subscribe_all(event_logger.log_event)

        # Query events
        events = await event_logger.get_events_by_user(user_uid, days_back=7)

        # Replay events for debugging
        await event_logger.replay_events(
            filters={'event_type': 'task.completed'},
            handler=debug_handler
        )

    Semantic Types Used:
    - This is an infrastructure service that does not create semantic relationships
    - Logs events from other services but does not interpret semantic relationships
    - No semantic relationship types used (event logging and audit only)

    Source Tag: N/A
    - This service does not create semantic relationships
    - Only logs and retrieves events for audit and replay

    Confidence Scoring: N/A
    - No confidence scoring (event logging infrastructure only)
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize event logger service.

        Args:
            executor: QueryExecutor for persistent storage
        """
        self.executor = executor
        self.logger = get_logger("skuel.services.event_logger")

    # ========================================================================
    # EVENT LOGGING
    # ========================================================================

    @with_error_handling("log_event", error_type="database")
    async def log_event(self, event: BaseEvent) -> Result[EventLogEntry]:
        """
        Log a domain event to persistent storage.

        This method should be subscribed to ALL events via event_bus.subscribe_all().

        Args:
            event: Domain event to log

        Returns:
            Result containing the log entry
        """
        import uuid

        # Extract metadata from event
        log_entry = EventLogEntry(
            log_id=f"log-{uuid.uuid4().hex[:12]}",
            event_type=event.event_type,
            event_data=event.__dict__,
            occurred_at=event.occurred_at,
            user_uid=getattr(event, "user_uid", None),
            aggregate_id=self._extract_aggregate_id(event),
            aggregate_type=self._extract_aggregate_type(event),
            source_service=self._extract_source_service(event),
        )

        # Persist to Neo4j
        query = """
        CREATE (log:EventLog {
            log_id: $log_id
            event_type: $event_type
            event_data: $event_data
            occurred_at: datetime($occurred_at)
            user_uid: $user_uid
            aggregate_id: $aggregate_id
            aggregate_type: $aggregate_type
            source_service: $source_service
            replayed: false
            replay_count: 0
        })
        RETURN log
        """

        result = await self.executor.execute_query(
            query,
            {
                "log_id": log_entry.log_id,
                "event_type": log_entry.event_type,
                "event_data": str(log_entry.event_data),  # Store as JSON string
                "occurred_at": log_entry.occurred_at.isoformat(),
                "user_uid": log_entry.user_uid,
                "aggregate_id": log_entry.aggregate_id,
                "aggregate_type": log_entry.aggregate_type,
                "source_service": log_entry.source_service,
            },
        )
        if result.is_error:
            self.logger.warning(f"Failed to log event: {result.error}")

        self.logger.debug(f"Logged event: {log_entry.event_type} ({log_entry.log_id})")
        return Result.ok(log_entry)

    # ========================================================================
    # EVENT QUERYING
    # ========================================================================

    @with_error_handling("get_events_by_user", error_type="database")
    async def get_events_by_user(
        self, user_uid: str, days_back: int = 7, event_types: list[str] | None = None
    ) -> Result[list[EventLogEntry]]:
        """
        Get events for a specific user.

        Args:
            user_uid: UID of the user,
            days_back: Number of days to look back,
            event_types: Optional list of event types to filter

        Returns:
            Result containing list of event log entries
        """
        start_date = datetime.now() - timedelta(days=days_back)

        # Build query
        type_filter = ""
        if event_types:
            type_list = "', '".join(event_types)
            type_filter = f"AND log.event_type IN ['{type_list}']"

        query = f"""
        MATCH (log:EventLog {{user_uid: $user_uid}})
        WHERE datetime(log.occurred_at) >= datetime($start_date)
        {type_filter}
        RETURN log
        ORDER BY log.occurred_at DESC
        LIMIT 1000
        """

        result = await self.executor.execute_query(
            query, {"user_uid": user_uid, "start_date": start_date.isoformat()}
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        # Convert to EventLogEntry objects
        entries = []
        for record in records:
            log_data = record["log"]
            entry = EventLogEntry(
                log_id=log_data["log_id"],
                event_type=log_data["event_type"],
                event_data=eval(log_data["event_data"]),  # Parse JSON string
                occurred_at=datetime.fromisoformat(log_data["occurred_at"]),
                user_uid=log_data.get("user_uid"),
                aggregate_id=log_data.get("aggregate_id"),
                aggregate_type=log_data.get("aggregate_type"),
                source_service=log_data.get("source_service"),
                replayed=log_data.get("replayed", False),
                replay_count=log_data.get("replay_count", 0),
            )
            entries.append(entry)

        self.logger.info(f"Retrieved {len(entries)} events for user {user_uid}")
        return Result.ok(entries)

    @with_error_handling("get_events_by_aggregate", error_type="database")
    async def get_events_by_aggregate(
        self, aggregate_id: str, aggregate_type: str | None = None
    ) -> Result[list[EventLogEntry]]:
        """
        Get all events for a specific aggregate (entity).

        Useful for debugging: "Show me all events that affected this task"

        Args:
            aggregate_id: UID of the aggregate (task_uid, goal_uid, etc.),
            aggregate_type: Optional type filter ("Task", "Goal", etc.)

        Returns:
            Result containing list of event log entries
        """
        type_filter = ""
        if aggregate_type:
            type_filter = "AND log.aggregate_type = $aggregate_type"

        query = f"""
        MATCH (log:EventLog {{aggregate_id: $aggregate_id}})
        {type_filter}
        RETURN log
        ORDER BY log.occurred_at ASC
        """

        params: dict[str, Any] = {"aggregate_id": aggregate_id}
        if aggregate_type:
            params["aggregate_type"] = aggregate_type

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        # Convert to EventLogEntry objects
        entries = [
            EventLogEntry(
                log_id=r["log"]["log_id"],
                event_type=r["log"]["event_type"],
                event_data=eval(r["log"]["event_data"]),
                occurred_at=datetime.fromisoformat(r["log"]["occurred_at"]),
                user_uid=r["log"].get("user_uid"),
                aggregate_id=r["log"].get("aggregate_id"),
                aggregate_type=r["log"].get("aggregate_type"),
                source_service=r["log"].get("source_service"),
                replayed=r["log"].get("replayed", False),
                replay_count=r["log"].get("replay_count", 0),
            )
            for r in records
        ]

        self.logger.info(f"Retrieved {len(entries)} events for aggregate {aggregate_id}")
        return Result.ok(entries)

    # ========================================================================
    # EVENT REPLAY
    # ========================================================================

    @with_error_handling("replay_events", error_type="system")
    async def replay_events(
        self, filters: dict[str, Any], handler: Any, dry_run: bool = False
    ) -> Result[int]:
        """
        Replay events matching filters through a handler.

        Useful for:
        - Debugging: Replay events to reproduce a bug
        - Recovery: Replay events to rebuild state after data loss
        - Migration: Replay events to populate new data structures

        Args:
            filters: Event filters (event_type, user_uid, date_range, etc.),
            handler: Async function to handle each event,
            dry_run: If True, don't mark events as replayed

        Returns:
            Result containing count of replayed events
        """
        from core.events import get_event_class

        # Build filter query
        where_clauses = []
        params = {}

        if "event_type" in filters:
            where_clauses.append("log.event_type = $event_type")
            params["event_type"] = filters["event_type"]

        if "user_uid" in filters:
            where_clauses.append("log.user_uid = $user_uid")
            params["user_uid"] = filters["user_uid"]

        if "start_date" in filters:
            where_clauses.append("datetime(log.occurred_at) >= datetime($start_date)")
            params["start_date"] = filters["start_date"].isoformat()

        if "end_date" in filters:
            where_clauses.append("datetime(log.occurred_at) <= datetime($end_date)")
            params["end_date"] = filters["end_date"].isoformat()

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
        MATCH (log:EventLog)
        WHERE {where_clause}
        RETURN log
        ORDER BY log.occurred_at ASC
        """

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        # Replay each event
        replayed_count = 0
        for record in records:
            log_data = record["log"]

            # Reconstruct event from log
            event_class = get_event_class(log_data["event_type"])
            if not event_class:
                self.logger.warning(f"Unknown event type: {log_data['event_type']}")
                continue

            event_data = eval(log_data["event_data"])
            event = event_class(**event_data)

            # Call handler
            await handler(event)

            # Mark as replayed (unless dry run)
            if not dry_run:
                await self._mark_replayed(log_data["log_id"])

            replayed_count += 1

        self.logger.info(f"Replayed {replayed_count} events (dry_run={dry_run})")
        return Result.ok(replayed_count)

    async def _mark_replayed(self, log_id: str) -> None:
        """Mark an event log entry as replayed."""
        query = """
        MATCH (log:EventLog {log_id: $log_id})
        SET log.replayed = true,
            log.replay_count = coalesce(log.replay_count, 0) + 1
        """

        try:
            result = await self.executor.execute_query(query, {"log_id": log_id})
            if result.is_error:
                self.logger.warning(f"Failed to mark replayed: {result.error}")
        except Exception as e:
            self.logger.warning(f"Failed to mark replayed: {e}")

    # ========================================================================
    # ANALYTICS & AUDIT
    # ========================================================================

    @with_error_handling("get_event_statistics", error_type="database")
    async def get_event_statistics(
        self, user_uid: str | None = None, days_back: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get event statistics for analytics and auditing.

        Args:
            user_uid: Optional user filter,
            days_back: Number of days to analyze

        Returns:
            Result containing statistics dictionary
        """
        start_date = datetime.now() - timedelta(days=days_back)

        user_filter = ""
        params = {"start_date": start_date.isoformat()}

        if user_uid:
            user_filter = "AND log.user_uid = $user_uid"
            params["user_uid"] = user_uid

        query = f"""
        MATCH (log:EventLog)
        WHERE datetime(log.occurred_at) >= datetime($start_date)
        {user_filter}
        WITH log.event_type as event_type, count(*) as count
        RETURN event_type, count
        ORDER BY count DESC
        """

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []

        # Build statistics
        stats = {
            "total_events": sum(r["count"] for r in records),
            "event_counts": {r["event_type"]: r["count"] for r in records},
            "most_common_event": records[0]["event_type"] if records else None,
            "period_days": days_back,
            "user_uid": user_uid,
        }

        return Result.ok(stats)

    async def export_event_stream(
        self, filters: dict[str, Any], format: str = "json"
    ) -> Result[str]:
        """
        Export event stream for external analysis.

        Args:
            filters: Event filters,
            format: Export format ("json", "csv", "ndjson")

        Returns:
            Result containing exported data as string
        """
        # Get events
        result = await self.get_events_by_user(
            user_uid=filters.get("user_uid", ""),
            days_back=filters.get("days_back", 30),
            event_types=filters.get("event_types"),
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        entries = result.value

        # Format export
        if format == "json":
            import json

            data = [entry.to_dict() for entry in entries]
            return Result.ok(json.dumps(data, indent=2))

        elif format == "ndjson":
            import json

            lines = [json.dumps(entry.to_dict()) for entry in entries]
            return Result.ok("\n".join(lines))

        elif format == "csv":
            # CSV format (simplified)
            lines = ["log_id,event_type,occurred_at,user_uid,aggregate_id"]
            for entry in entries:
                lines.append(
                    f"{entry.log_id},{entry.event_type},"
                    f"{entry.occurred_at.isoformat()},{entry.user_uid},"
                    f"{entry.aggregate_id}"
                )
            return Result.ok("\n".join(lines))

        else:
            return Result.fail(
                Errors.validation(message=f"Unsupported export format: {format}", field="format")
            )

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    def _extract_aggregate_id(self, event: BaseEvent) -> str | None:
        """Extract aggregate ID from event."""
        # Try common field names using getattr with default (more Pythonic than hasattr)
        for field in [
            "task_uid",
            "goal_uid",
            "habit_uid",
            "ku_uid",
            "path_uid",
            "event_uid",
            "principle_uid",
            "choice_uid",
            "expense_uid",
            "journal_uid",
        ]:
            uid = getattr(event, field, None)
            if uid is not None:
                return uid
        return None

    def _extract_aggregate_type(self, event: BaseEvent) -> str | None:
        """Extract aggregate type from event type."""
        event_type = event.event_type

        if event_type.startswith("task."):
            return "Task"
        elif event_type.startswith("goal."):
            return "Goal"
        elif event_type.startswith("habit."):
            return "Habit"
        elif event_type.startswith("knowledge."):
            return "Ku"
        elif event_type.startswith("learning_path."):
            return "Lp"
        elif event_type.startswith("calendar_event."):
            return "Event"
        elif event_type.startswith("principle."):
            return "Principle"
        elif event_type.startswith("choice."):
            return "Choice"
        elif event_type.startswith("expense."):
            return "Expense"
        elif event_type.startswith("journal."):
            return "Journal"

        return None

    def _extract_source_service(self, event: BaseEvent) -> str | None:
        """Extract source service from event type."""
        event_type = event.event_type
        return event_type.split(".")[0] if "." in event_type else None
