"""
Temporal Mixin
==============

Temporal query operations (April 2026) — date-range and due-date queries
for any entity type.

Provides:
    user_activity_range_raw: User entities within a date range
    upcoming_raw: Entities upcoming within N days
    overdue_raw: Entities past their due date
    active_raw: User's non-terminal entities

Requires on concrete class:
    driver, label
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.models.type_hints import UserUID
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    from datetime import date

    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


class _TemporalMixin[T: DomainModelProtocol]:
    """
    Temporal query operations.

    Requires on concrete class:
        driver: AsyncDriver
        label: NeoLabel
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel

    @safe_backend_operation("user_activity_range_raw")
    async def user_activity_range_raw(
        self,
        user_uid: UserUID,
        date_field: str | builtins.list[str],
        start_date: date,
        end_date: date,
        exclude_statuses: builtins.list[str] | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query user entities within a date range.

        Args:
            user_uid: User identifier
            date_field: Date field name(s) for range filter — a list matches
                entities where ANY of the fields falls inside the range
            start_date: Range start
            end_date: Range end
            exclude_statuses: Status values to exclude

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query import build_user_activity_query

        cypher_query, params = build_user_activity_query(
            user_uid=user_uid,
            node_label=self.label,
            date_field=date_field,
            start_date=start_date,
            end_date=end_date,
            exclude_statuses=exclude_statuses or [],
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            # Builders RETURN n; result.data() wraps each node under "n" — unwrap to
            # flat property dicts so _to_domain_models can deserialize (matches the
            # record["e"] idiom in get_events_in_range). Without this, every field is
            # None and user-owned conversion raises "user_uid is None".
            return Result.ok([row["n"] for row in await result.data()])

    @safe_backend_operation("upcoming_raw")
    async def upcoming_raw(
        self,
        date_field: str,
        days_ahead: int = 7,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query entities upcoming within N days.

        Args:
            date_field: Date field for comparison
            days_ahead: Days ahead to look
            exclude_statuses: Status values to exclude
            user_uid: Optional user scope
            limit: Maximum results
            secondary_sort_field: Optional secondary sort

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_due_soon_query

        cypher_query, params = build_due_soon_query(
            node_label=self.label,
            date_field=date_field,
            days_ahead=days_ahead,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=secondary_sort_field,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            # Builders RETURN n; result.data() wraps each node under "n" — unwrap to
            # flat property dicts so _to_domain_models can deserialize (matches the
            # record["e"] idiom in get_events_in_range). Without this, every field is
            # None and user-owned conversion raises "user_uid is None".
            return Result.ok([row["n"] for row in await result.data()])

    @safe_backend_operation("active_raw")
    async def active_raw(
        self,
        user_uid: UserUID,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query user's active (non-terminal) entities.

        Args:
            user_uid: User scope (required — active is always user-scoped)
            exclude_statuses: Terminal statuses to exclude (e.g., completed/failed/cancelled/archived)
            limit: Maximum results

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_active_query

        cypher_query, params = build_active_query(
            node_label=self.label,
            user_uid=user_uid,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            limit=limit,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            # Builders RETURN n; result.data() wraps each node under "n" — unwrap to
            # flat property dicts so _to_domain_models can deserialize (matches the
            # record["e"] idiom in get_events_in_range). Without this, every field is
            # None and user-owned conversion raises "user_uid is None".
            return Result.ok([row["n"] for row in await result.data()])

    @safe_backend_operation("overdue_raw")
    async def overdue_raw(
        self,
        date_field: str,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Query entities past their due date.

        Args:
            date_field: Date field for comparison
            exclude_statuses: Status values to exclude
            user_uid: Optional user scope
            limit: Maximum results
            secondary_sort_field: Optional secondary sort

        Returns:
            Result[list[dict]]: Raw Neo4j records
        """
        from adapters.persistence.neo4j.query.cypher import build_overdue_query

        cypher_query, params = build_overdue_query(
            node_label=self.label,
            date_field=date_field,
            exclude_statuses=exclude_statuses if exclude_statuses else None,
            user_uid=user_uid,
            limit=limit,
            secondary_sort_field=secondary_sort_field,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            # Builders RETURN n; result.data() wraps each node under "n" — unwrap to
            # flat property dicts so _to_domain_models can deserialize (matches the
            # record["e"] idiom in get_events_in_range). Without this, every field is
            # None and user-owned conversion raises "user_uid is None".
            return Result.ok([row["n"] for row in await result.data()])
