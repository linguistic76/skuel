"""
Generic Cypher template executor for Neo4j operations.

This module provides a generic pattern for executing Cypher templates with any entity type.
Handles transaction management, batching, and statistics aggregation.

Data transformation (entity→dict conversion, connection flattening) lives in
batch_preparer.py — this module is purely about database execution.

See: /docs/architecture/YAML_MARKDOWN_INGESTION_GUIDE.md for complete flow
See: /docs/architecture/GRAPH_NATIVE_ANALYSIS.md for architecture details
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from neo4j import AsyncSession
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CypherTemplate:
    """A reusable Cypher query template."""

    name: str
    template: str
    description: str


class CypherExecutor[T]:
    """
    Generic executor for Cypher templates with automatic type conversion.

    This class provides:
    - Type-safe execution of Cypher templates
    - Automatic entity → Neo4j property conversion
    - Batch operations support
    - Transaction management
    """

    def __init__(self, session: AsyncSession, entity_type: type[T]) -> None:
        """
        Initialize with Neo4j session and entity type.

        Args:
            session: Neo4j async session
            entity_type: The type of entities being processed
        """
        self.session = session
        self.entity_type = entity_type
        self.logger = get_logger(f"{__name__}.{entity_type.__name__}")

    async def execute_single(
        self, template: CypherTemplate, entity: T, extra_params: dict[str, Any] | None = None
    ) -> Result[dict[str, Any]]:
        """
        Execute template for a single entity.

        Args:
            template: The Cypher template to execute,
            entity: The entity to process,
            extra_params: Additional parameters for the query

        Returns:
            Result containing query statistics
        """
        from adapters.persistence.neo4j.neo4j_mapper import to_neo4j_node

        try:
            params = {"item": to_neo4j_node(entity)}
            if extra_params:
                params.update(extra_params)

            result = await self.session.run(template.template, params)
            summary = await result.consume()

            stats = {
                "nodes_created": summary.counters.nodes_created,
                "nodes_deleted": summary.counters.nodes_deleted,
                "relationships_created": summary.counters.relationships_created,
                "relationships_deleted": summary.counters.relationships_deleted,
                "properties_set": summary.counters.properties_set,
            }

            self.logger.debug(f"Executed {template.name}: {stats}")
            return Result.ok(stats)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Cypher execution failed: {e}")
            return Result.fail(
                Errors.database(
                    operation=template.name, message=str(e), entity=self.entity_type.__name__
                )
            )

    async def execute_batch(
        self,
        template: CypherTemplate,
        items: list[dict[str, Any]],
        batch_size: int = 1000,
        extra_params: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Execute template for a batch of pre-shaped item dicts.

        Data transformation (entity conversion, connection flattening) is handled
        by batch_preparer.prepare_batch_items() before calling this method.

        Args:
            template: The Cypher template to execute,
            items: Pre-shaped dicts ready for Neo4j (from prepare_batch_items),
            batch_size: Number of items per transaction,
            extra_params: Additional parameters for the query

        Returns:
            Result containing aggregated statistics
        """
        if not items:
            return Result.ok(
                {"nodes_created": 0, "relationships_created": 0, "batches_processed": 0}
            )

        try:
            total_stats = {
                "nodes_created": 0,
                "nodes_deleted": 0,
                "relationships_created": 0,
                "relationships_deleted": 0,
                "properties_set": 0,
                "batches_processed": 0,
            }

            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]

                params: dict[str, Any] = {"items": batch}
                if extra_params:
                    params.update(extra_params)

                tx = await self.session.begin_transaction()
                try:
                    result = await tx.run(template.template, params)
                    summary = await result.consume()

                    total_stats["nodes_created"] += summary.counters.nodes_created
                    total_stats["nodes_deleted"] += summary.counters.nodes_deleted
                    total_stats["relationships_created"] += summary.counters.relationships_created
                    total_stats["relationships_deleted"] += summary.counters.relationships_deleted
                    total_stats["properties_set"] += summary.counters.properties_set
                    total_stats["batches_processed"] += 1

                    await tx.commit()
                except NEO4J_EXCEPTIONS:
                    await tx.rollback()
                    raise

                self.logger.info(f"Processed batch {i // batch_size + 1}: {len(batch)} items")

            self.logger.info(
                f"Batch execution complete: {len(items)} items in "
                f"{total_stats['batches_processed']} batches"
            )
            return Result.ok(total_stats)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Batch execution failed: {e}")
            return Result.fail(
                Errors.database(
                    operation=f"batch_{template.name}",
                    message=str(e),
                    entity=self.entity_type.__name__,
                )
            )

    async def execute_query(
        self, template: CypherTemplate, params: dict[str, Any] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """
        Execute a query template and return results.

        Args:
            template: The Cypher template to execute,
            params: Query parameters

        Returns:
            Result containing list of records as dictionaries
        """
        try:
            result = await self.session.run(template.template, params or {})
            records = [dict(record) async for record in result]

            self.logger.debug(f"Query {template.name} returned {len(records)} records")
            return Result.ok(records)

        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Query execution failed: {e}")
            return Result.fail(Errors.database(operation=f"query_{template.name}", message=str(e)))
