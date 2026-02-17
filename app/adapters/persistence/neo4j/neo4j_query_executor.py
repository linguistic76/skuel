"""
Neo4j Query Executor - Adapter for QueryExecutor Port
======================================================

Adapter implementing the QueryExecutor protocol for Neo4j.

Provides raw Cypher query execution with automatic error handling,
session management, and Result[T] wrapping. Also offers convenience
methods (execute with processor, execute_count, execute_exists,
create_relationships_batch) for common query patterns.

Architecture:
    - Implements QueryExecutor protocol (core/services/protocols/)
    - Lives in adapters layer (correct hexagonal placement)
    - Core services depend on QueryExecutor protocol, not this class

Usage:
    from core.services.protocols import QueryExecutor

    class MyService:
        def __init__(self, executor: QueryExecutor):
            self.executor = executor

        async def get_items(self, uid: str) -> Result[list[str]]:
            result = await self.executor.execute_query(
                "MATCH (n {uid: $uid})-[:REL]->(m) RETURN m.uid as uid",
                {"uid": uid},
            )
            if result.is_error:
                return result
            return Result.ok([r["uid"] for r in result.value])

See: /docs/patterns/protocol_architecture.md
"""

from collections.abc import Callable
from typing import Any

from neo4j import AsyncDriver

from core.utils.processor_functions import check_exists, extract_count
from core.utils.result_simplified import Errors, Result


class Neo4jQueryExecutor:
    """
    Neo4j adapter for the QueryExecutor protocol.

    Wraps AsyncDriver with automatic session management, error handling,
    and Result[T] wrapping. Also provides convenience methods for common
    query patterns (count, exists, batch relationships).

    Usage:
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        executor = Neo4jQueryExecutor(driver)
        result = await executor.execute_query("MATCH (n) RETURN n.uid as uid")
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """
        Initialize query executor.

        Args:
            driver: Neo4j AsyncDriver for query execution
        """
        self.driver = driver

    # ========================================================================
    # QueryExecutor protocol method
    # ========================================================================

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Execute a Cypher query, returning records as dicts wrapped in Result.

        Satisfies the QueryExecutor protocol.

        Args:
            query: Cypher query string
            params: Query parameters (optional)

        Returns:
            Result[list[dict]] with raw records as dictionaries
        """
        if not self.driver:
            return Result.fail(
                Errors.system(
                    message="Neo4j driver not available",
                    operation="execute_query",
                )
            )

        try:
            async with self.driver.session() as session:
                result = await session.run(query, **(params or {}))
                records = await result.data()
                return Result.ok(records)

        except Exception as e:
            return Result.fail(Errors.database(operation="execute_query", message=str(e)))

    # ========================================================================
    # Convenience methods (not part of QueryExecutor protocol)
    # ========================================================================

    async def execute[T](
        self,
        query: str,
        params: dict[str, Any] | None = None,
        processor: Callable[[list[dict[str, Any]]], T] | None = None,
        operation: str = "query_execution",
    ) -> Result[T]:
        """
        Execute a Cypher query with optional processor function.

        Args:
            query: Cypher query string
            params: Query parameters (optional)
            processor: Function to process records (optional, defaults to returning raw records)
            operation: Operation name for error messages

        Returns:
            Result containing processed data or error

        Example:
            from core.utils.processor_functions import extract_uids_list

            result = await executor.execute(
                query="MATCH (n)-[:REL]->(m) RETURN m.uid as uid",
                processor=extract_uids_list,
                operation="get_related_uids"
            )
        """
        if not self.driver:
            return Result.fail(
                Errors.system(message="Neo4j driver not available", operation=operation)
            )

        try:
            async with self.driver.session() as session:
                result = await session.run(query, **(params or {}))
                records = await result.data()

                if processor:
                    processed = processor(records)
                    return Result.ok(processed)
                else:
                    return Result.ok(records)

        except Exception as e:
            return Result.fail(Errors.database(operation=operation, message=str(e)))

    async def execute_write[T](
        self,
        query: str,
        params: dict[str, Any] | None = None,
        processor: Callable[[list[dict[str, Any]]], T] | None = None,
        operation: str = "write_operation",
    ) -> Result[T]:
        """
        Execute a write query with automatic error handling.

        Same as execute() but more explicit for write operations.
        """
        return await self.execute(query, params, processor, operation)

    async def execute_count(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        operation: str = "count_operation",
    ) -> Result[int]:
        """
        Execute a count query and return the count as an integer.

        Expects query to return a field named 'count'.
        """
        return await self.execute(
            query=query,
            params=params,
            processor=extract_count,
            operation=operation,
        )

    async def execute_exists(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        operation: str = "exists_check",
    ) -> Result[bool]:
        """
        Execute an existence check query.
        """
        return await self.execute(
            query=query,
            params=params,
            processor=check_exists,
            operation=operation,
        )

    async def create_relationships_batch(
        self,
        relationships: list[tuple[str, str, str, dict[str, Any] | None]],
        operation: str = "create_relationships_batch",
    ) -> Result[int]:
        """
        Create multiple relationships in a single transaction.

        Uses BatchOperationHelper for pure Cypher query generation.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples
            operation: Operation name for error messages

        Returns:
            Result[int] with count of relationships created
        """
        from core.infrastructure.batch import BatchOperationHelper

        if not relationships:
            return Result.ok(0)

        if not self.driver:
            return Result.fail(
                Errors.system(message="Neo4j driver not available", operation=operation)
            )

        try:
            queries = BatchOperationHelper.build_relationship_create_queries(relationships)

            total_created = 0
            async with self.driver.session() as session:
                for query, rels_data in queries:
                    result = await session.run(query, {"rels": rels_data})
                    record = await result.single()
                    total_created += record["created_count"] if record else 0

            return Result.ok(total_created)

        except Exception as e:
            return Result.fail(Errors.database(operation=operation, message=str(e)))
