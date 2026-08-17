"""
Unified Query Builder — the fluent front door to the ``cypher/`` builders
========================================================================

A thin fluent facade over the ``cypher/`` ``build_*`` functions. It holds
filter/limit/offset/order state and renders it into a query, so callers
compose a read declaratively instead of hand-writing Cypher.

**Architecture:**

::

    UnifiedQueryBuilder  ← YOU ARE HERE
    └── ModelQueryBuilder  → cypher/ build_* functions (list/search/count)

**Usage:**

```python
from adapters.persistence.neo4j.query import UnifiedQueryBuilder

tasks = await (
    UnifiedQueryBuilder(executor)
    .for_model(Task)
    .filter(priority="high", status="active")
    .order_by("due_date", desc=True)
    .limit(50)
    .execute()
)
```

Live callers reach it through ``UniversalNeo4jBackend.query_builder``
(``_crud_mixin`` list reads, ``_search_mixin`` filtered search + count).

The template/optimization/validation bridge that once hung off this class was
deleted with the ``query_builders/`` package it fronted (2026-08-17) — it had
had no production invocations since 2026-05-12. Text search is served by
``SearchRouter``'s rungs, not by a builder-level ``.fulltext()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from adapters.persistence.neo4j.query.cypher import (
    build_count_query,
    build_list_query,
    build_search_query,
)
from adapters.persistence.neo4j.query.graph_traversal import build_graph_context_query
from core.models.query_types import QueryIntent
from core.utils.logging import get_logger
from core.utils.validation_helpers import validate_field_name

T = TypeVar("T")
logger = get_logger(__name__)


@dataclass
class QueryResult[T]:
    """Result of query execution with metadata."""

    data: list[T]
    cypher: str
    parameters: dict[str, Any]
    strategy: str  # "cypher"
    estimated_cost: int | None = None


class ModelQueryBuilder[T]:
    """
    Fluent builder for model-based queries.

    Routes to the cypher/ build_* functions internally.
    """

    def __init__(self, model: type[T], executor: Any = None, label: str | None = None) -> None:
        self.model = model
        self.executor = executor
        self.label = label  # Neo4j label (e.g., "Report" instead of Python class name)
        self._filters: dict[str, Any] = {}
        self._limit_val: int | None = None
        self._offset_val: int = 0
        self._order_by_field: str | None = None
        self._order_desc: bool = False

    def filter(self, **filters: Any) -> ModelQueryBuilder[T]:
        """
        Add filters to query.

        Supports operators via double underscore:
        - eq (default): .filter(priority='high')
        - gt, lt, gte, lte: .filter(due_date__gte=date.today())
        - contains: .filter(title__contains='urgent')
        - in: .filter(priority__in=['high', 'urgent'])

        Keys are validated as safe Cypher identifiers before being recorded
        (matches the `order_by` policy). Invalid keys are silently dropped
        with a warning rather than raising, so a typo doesn't abort the
        whole query chain. Today's callers all pass trusted keys; this is
        defense-in-depth against future user-driven callers.
        """
        for key, value in filters.items():
            if not validate_field_name(key):
                logger.warning(f"Invalid filter key ignored: {key!r}")
                continue
            self._filters[key] = value
        return self

    def limit(self, limit: int) -> ModelQueryBuilder[T]:
        """Limit number of results."""
        self._limit_val = limit
        return self

    def offset(self, offset: int) -> ModelQueryBuilder[T]:
        """Skip first N results."""
        self._offset_val = offset
        return self

    def order_by(self, field: str, desc: bool = False) -> ModelQueryBuilder[T]:
        """Order results by field."""
        if not validate_field_name(field):
            logger.warning(f"Invalid order_by field ignored: {field!r}")
            return self
        self._order_by_field = field
        self._order_desc = desc
        return self

    def build(self) -> tuple[str, dict[str, Any]]:
        """
        Build query without executing.

        Returns:
            Tuple of (cypher_query, parameters)
        """
        # Filter-based search
        if self._filters:
            # Search query with filters
            query, params = build_search_query(self.model, self._filters, label=self.label)

            # Build query clauses in correct Cypher order: RETURN ... ORDER BY ... SKIP ... LIMIT
            return_clause = "RETURN n"

            # Add ordering if specified
            if self._order_by_field:
                direction = "DESC" if self._order_desc else "ASC"
                return_clause += f" ORDER BY n.{self._order_by_field} {direction}"

            # Add pagination (SKIP must come before LIMIT)
            if self._offset_val > 0:
                return_clause += " SKIP $skip"
                params["skip"] = self._offset_val

            if self._limit_val:
                return_clause += " LIMIT $limit"
                params["limit"] = self._limit_val

            # Replace the RETURN n with our complete clause
            query = query.replace("RETURN n", return_clause)

            return query, params

        # List query (no filters)
        else:
            query, params = build_list_query(
                self.model,
                label=self.label,
                limit=self._limit_val or 100,
                skip=self._offset_val,
                order_by=self._order_by_field,
                order_desc=self._order_desc,
            )
            return query, params

    async def execute(self) -> QueryResult[T]:
        """
        Execute query and return results.

        Requires executor to be set during initialization.
        """
        if not self.executor:
            raise ValueError(
                "Executor is required for execution. Use .build() to get query without executing."
            )

        query, params = self.build()

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            raise ValueError(f"Query execution failed: {result.expect_error().message}")

        # Convert Neo4j records to model instances using generic mapper
        data = [from_neo4j_node(dict(r["n"]), self.model) for r in result.value]

        return QueryResult(data=data, cypher=query, parameters=params, strategy="cypher")

    async def count(self) -> int:
        """
        Count matching records without retrieving them.

        More efficient than execute() + len().
        """
        query, params = build_count_query(
            self.model, self._filters if self._filters else None, label=self.label
        )

        if not self.executor:
            raise ValueError("Executor is required for execution")

        result = await self.executor.execute_query(query, params)
        if result.is_error:
            raise ValueError(f"Count query failed: {result.expect_error().message}")

        return result.value[0]["count"] if result.value else 0


class UnifiedQueryBuilder:
    """
    Entry point for fluent query building in SKUEL.

    **Pure Cypher architecture - no APOC dependencies.**

    Usage:
        # Model queries
        await UnifiedQueryBuilder(executor).for_model(Task).filter(status='active').execute()

        # Graph context
        query = UnifiedQueryBuilder().graph_context("task.123", QueryIntent.HIERARCHICAL)
    """

    def __init__(self, executor: Any = None) -> None:
        """
        Initialize unified query builder.

        Args:
            executor: QueryExecutor for query execution
        """
        self.executor = executor

    def for_model(self, model: type[T], label: str | None = None) -> ModelQueryBuilder[T]:
        """
        Start building query for specific model.

        Routes to the cypher/ build_* functions internally.

        Args:
            model: Domain model class
            label: Optional Neo4j label (defaults to model.__name__ if not provided)

        Example:
            tasks = await (builder
                .for_model(Task, label="Task") # Explicit label
                .filter(priority='high', status='in_progress')
                .order_by('due_date', desc=True)
                .limit(50)
                .execute())
        """
        return ModelQueryBuilder(model, self.executor, label=label)

    def graph_context(self, uid: str, intent: QueryIntent, depth: int = 2) -> str:
        """
        Build pure Cypher graph context query (convenience method).

        Routes to build_graph_context_query(), which uses variable-length
        patterns rather than APOC path procedures.

        Example:
            query = builder.graph_context(
                uid="task.123",
                intent=QueryIntent.HIERARCHICAL,
                GraphDepth.NEIGHBORHOOD
            )
        """
        return build_graph_context_query(uid, intent, depth)


# Convenience factory function
def query(executor: Any = None) -> UnifiedQueryBuilder:
    """
    Create unified query builder instance.

    Shorthand for UnifiedQueryBuilder(executor).

    Usage:
        from core.models.query import query

        tasks = await query(executor).for_model(Task).filter(status='active').execute()
    """
    return UnifiedQueryBuilder(executor)
