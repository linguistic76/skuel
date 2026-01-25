"""
Graph Query Executor - Direct Driver Helper
=============================================

Generic query execution helper for Direct Driver pattern services.

**Purpose**: Eliminate 10-15 lines of boilerplate per query method

**What This Eliminates:**
- Driver availability check
- Session management (async with self.driver.session())
- Error handling try/except blocks
- Result wrapping (Result.ok/Result.fail)
- Database error conversion

**Pattern Replaced:**

```python
# BEFORE (15 lines):
async def get_items(self, uid: str) -> Result[list[str]]:
    if not self.driver:
        return Result.fail(
            Errors.system(message="Driver not available", operation="get_items")
        )

    try:
        async with self.driver.session() as session:
            result = await session.run(query, uid=uid)
            records = await result.data()
            items = [r["uid"] for r in records]
            return Result.ok(items)
    except Exception as e:
        return Result.fail(
            Errors.database(operation="get_items", message=str(e))
        )


# AFTER (3 lines):
async def get_items(self, uid: str) -> Result[list[str]]:
    return await self.execute_query(
        query="MATCH (n {uid: $uid})-[:REL]->(m) RETURN m.uid as uid",
        params={"uid": uid},
        processor=extract_uids_list,  # from core.utils.processor_functions
        operation="get_items",
    )
```

Version: 1.0.0
Date: November 15, 2025
"""

from collections.abc import Callable
from typing import Any

from neo4j import AsyncDriver

from core.utils.processor_functions import check_exists, extract_count
from core.utils.result_simplified import Errors, Result


class GraphQueryExecutor:
    """
    Generic query execution helper for Direct Driver services.

    Eliminates boilerplate for:
    - Driver availability checks
    - Session management
    - Error handling
    - Result wrapping

    Usage:
        from core.utils.processor_functions import extract_uids_list

        class MyRelationshipService:
            def __init__(self, driver: AsyncDriver):
                self.executor = GraphQueryExecutor(driver)

            async def get_items(self, uid: str) -> Result[list[str]]:
                return await self.executor.execute(
                    query="MATCH (n {uid: $uid})-[:REL]->(m) RETURN m.uid as uid",
                    params={"uid": uid},
                    processor=extract_uids_list,
                    operation="get_items"
                )
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """
        Initialize query executor.

        Args:
            driver: Neo4j AsyncDriver for query execution
        """
        self.driver = driver

    async def execute[T](
        self,
        query: str,
        params: dict[str, Any] | None = None,
        processor: Callable[[list[dict[str, Any]]], T] | None = None,
        operation: str = "query_execution",
    ) -> Result[T]:
        """
        Execute a Cypher query with automatic error handling.

        Args:
            query: Cypher query string
            params: Query parameters (optional)
            processor: Function to process records (optional, defaults to returning raw records)
            operation: Operation name for error messages

        Returns:
            Result containing processed data or error

        Example:
            from core.utils.processor_functions import extract_uids_list

            # Simple UID list extraction
            result = await executor.execute(
                query="MATCH (n)-[:REL]->(m) RETURN m.uid as uid",
                processor=extract_uids_list,
                operation="get_related_uids"
            )

            # Return raw records (no processor)
            result = await executor.execute(
                query="MATCH (n) RETURN n",
                operation="get_nodes"
            )

            # Custom processing - define a named function
            def extract_uids_and_titles(records):
                return {
                    "uids": [r["uid"] for r in records],
                    "titles": [r["title"] for r in records]
                }

            result = await executor.execute(
                query="MATCH (n) RETURN n.uid as uid, n.title as title",
                processor=extract_uids_and_titles,
                operation="get_node_data"
            )
        """
        # Check driver availability
        if not self.driver:
            return Result.fail(
                Errors.system(message="Neo4j driver not available", operation=operation)
            )

        try:
            # Execute query with session management
            async with self.driver.session() as session:
                result = await session.run(query, **(params or {}))
                records = await result.data()

                # Process records if processor provided
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
        Execute a write query (CREATE, MERGE, DETACH DELETE) with automatic error handling.

        Same as execute() but more explicit for write operations.
        Useful for code clarity when distinguishing reads vs writes.

        Args:
            query: Cypher write query (CREATE, MERGE, DETACH DELETE, SET)
            params: Query parameters (optional)
            processor: Function to process records (optional)
            operation: Operation name for error messages

        Returns:
            Result containing processed data or error

        Example:
            from core.utils.processor_functions import extract_single_value

            result = await executor.execute_write(
                query="CREATE (n:Node {uid: $uid}) RETURN n.uid as uid",
                params={"uid": new_uid},
                processor=extract_single_value("uid"),
                operation="create_node"
            )
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

        Convenience method for queries that return a count.
        Expects query to return a field named 'count'.

        Args:
            query: Cypher query returning count
            params: Query parameters (optional)
            operation: Operation name for error messages

        Returns:
            Result containing integer count

        Example:
            # Count relationships
            query = "MATCH (n:Node {uid: $uid})-[:REL]->(m) RETURN count(m) as count"
            result = await executor.execute_count(
                query=query,
                params={"uid": uid},
                operation="count_relationships"
            )
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

        Convenience method for queries that check if something exists.

        Args:
            query: Cypher query (e.g., "MATCH (n {uid: $uid}) RETURN n")
            params: Query parameters (optional)
            operation: Operation name for error messages

        Returns:
            Result containing boolean (True if records exist, False otherwise)

        Example:
            result = await executor.execute_exists(
                query="MATCH (n:Node {uid: $uid}) RETURN n",
                params={"uid": uid},
                operation="check_node_exists"
            )
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

        Batch operation using UNWIND for optimal Neo4j performance.
        This mirrors UniversalNeo4jBackend.create_relationships_batch() for consistency.

        Uses BatchOperationHelper for pure Cypher query generation.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples
            operation: Operation name for error messages

        Returns:
            Result[int] with count of relationships created

        Example:
            from core.infrastructure.batch import BatchOperationHelper
            from core.models.relationship_names import RelationshipName

            relationships = BatchOperationHelper.build_relationships_list(
                source_uid="journal:123",
                relationship_specs=[
                    (["journal:456"], RelationshipName.RELATED_TO.value, None),
                    (["goal:789"], RelationshipName.SUPPORTS_GOAL.value, None),
                ]
            )
            result = await executor.create_relationships_batch(relationships)
        """
        from core.infrastructure.batch import BatchOperationHelper

        if not relationships:
            return Result.ok(0)

        # Check driver availability
        if not self.driver:
            return Result.fail(
                Errors.system(message="Neo4j driver not available", operation=operation)
            )

        try:
            # Generate queries grouped by relationship type
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
