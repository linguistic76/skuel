"""
Generic Cypher template executor for Neo4j operations.

This module provides a generic pattern for executing Cypher templates with any entity type,
using type introspection to automatically handle conversions.

GRAPH-NATIVE INTEGRATION:
-------------------------
CypherExecutor handles the critical step of preserving connection data during batch
operations while ensuring it doesn't pollute node properties.

CONNECTION DATA FLOW (Phase 3):
    1. YAML frontmatter → MarkdownSyncService stores in metadata._connections
    2. Here: Extract and flatten to dotted keys (Neo4j can't store nested maps)
    3. BulkIngestionEngine: Uses apoc.map.removeKeys() to exclude from node props
    4. Cypher template: Creates graph edges via FOREACH + MERGE
    5. Result: Edges exist in graph, properties don't exist in nodes

Key Method: execute_batch() (lines 119-219)
    - Processes entities in configurable batch sizes (default 1000)
    - Extracts and flattens connection data for each entity (lines 161-177)
    - Executes Cypher template with transaction management
    - Returns aggregated statistics across all batches

Example Flow:
    # Input: Entity with metadata
    entity = Ku(
        uid="ku:test",
        title="Test",
        metadata={"_connections": {"requires": ["ku:A"], "enables": ["ku:B"]}}
    )

    # Step 1: Convert to Neo4j node (automatic via to_neo4j_node)
    item = {
        "uid": "ku:test",
        "title": "Test",
        "metadata": {...}  # Contains _connections
    }

    # Step 2: Extract connections from metadata (lines 169-177)
    # Flattened output:
    item["connections.requires"] = ["ku:A"]
    item["connections.enables"] = ["ku:B"]

    # Step 3: BulkIngestionEngine template filters connections.* from node props
    # Step 4: Cypher FOREACH creates edges:
    #   MERGE (n)-[:REQUIRES_KNOWLEDGE]->(target {uid: "ku:A"})
    #   MERGE (n)-[:ENABLES_KNOWLEDGE]->(target {uid: "ku:B"})

    # Final Result:
    # - Node: (:Ku {uid: "ku:test", title: "Test"})
    # - Edges: (ku:test)-[:REQUIRES_KNOWLEDGE]->(ku:A)
    #          (ku:test)-[:ENABLES_KNOWLEDGE]->(ku:B)

Type Safety:
    - Generic[T] parameter ensures type-safe entity processing
    - Automatic conversion via to_neo4j_node() handles all field types
    - No manual type casting needed by callers

Critical Section: Lines 161-177 (Connection Extraction)
    See inline comments for detailed explanation of flattening logic.

See: /docs/architecture/YAML_MARKDOWN_INGESTION_GUIDE.md for complete flow
See: /docs/architecture/GRAPH_NATIVE_ANALYSIS.md for architecture details
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from neo4j import AsyncSession
from core.utils.neo4j_mapper import to_neo4j_node
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class CypherTemplate:
    """A reusable Cypher query template."""

    name: str
    template: str
    description: str

    @classmethod
    def from_file(cls, path: Path) -> "CypherTemplate":
        """Load template from a .cypher file."""
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        content = path.read_text()
        # Extract description from first comment line if present
        lines = content.split("\n")
        description = ""
        if lines and lines[0].startswith("//"):
            description = lines[0][2:].strip()
            content = "\n".join(lines[1:])

        return cls(name=path.stem, template=content.strip(), description=description)


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
        try:
            # Convert entity to Neo4j properties using generic mapper
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

        except Exception as e:
            self.logger.error(f"Cypher execution failed: {e}")
            return Result.fail(
                Errors.database(
                    operation=template.name, message=str(e), entity=self.entity_type.__name__
                )
            )

    async def execute_batch(
        self,
        template: CypherTemplate,
        entities: list[T],
        batch_size: int = 1000,
        extra_params: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Execute template for a batch of entities.

        Uses UNWIND for efficient bulk operations.

        Args:
            template: The Cypher template to execute,
            entities: List of entities to process,
            batch_size: Number of entities per transaction,
            extra_params: Additional parameters for the query

        Returns:
            Result containing aggregated statistics
        """
        if not entities:
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

            # Process in batches for memory efficiency
            for i in range(0, len(entities), batch_size):
                batch = entities[i : i + batch_size]

                # Convert batch to Neo4j properties
                items = []
                for entity in batch:
                    item = to_neo4j_node(entity)

                    # ========================================================================
                    # PHASE 3 GRAPH-NATIVE: Critical Connection Data Extraction
                    # ========================================================================
                    # Connection data flow:
                    #   1. YAML frontmatter → MarkdownSyncService stores in metadata._connections
                    #   2. HERE: Extract and flatten to dotted keys (Neo4j can't store nested maps)
                    #   3. BulkIngestionEngine: Uses apoc.map.removeKeys() to exclude from node props
                    #   4. Cypher template: Creates graph edges via FOREACH + MERGE
                    #   5. Result: Edges exist in graph, properties don't exist in nodes
                    #
                    # Why flatten?
                    #   Neo4j properties cannot store nested dictionaries, but CAN use them
                    #   in Cypher queries. By flattening {"requires": ["ku:A"]} to
                    #   {"connections.requires": ["ku:A"]}, we make it accessible in Cypher
                    #   via backtick escaping: item.`connections.requires`
                    #
                    # Example transformation:
                    #   Input:  metadata._connections = {"requires": ["ku:A"], "enables": ["ku:B"]}
                    #   Output: item["connections.requires"] = ["ku:A"]
                    #           item["connections.enables"] = ["ku:B"]
                    #
                    # Later in BulkIngestionEngine:
                    #   - apoc.map.removeKeys() filters out "connections.requires", "connections.enables"
                    #   - FOREACH creates edges: MERGE (n)-[:REQUIRES_KNOWLEDGE]->(target {uid: "ku:A"})
                    #   - Result: Node has NO connection properties, ONLY graph edges exist
                    # ========================================================================
                    metadata = getattr(entity, "metadata", None)
                    if isinstance(metadata, dict):
                        connections = metadata.get("_connections")
                        if connections and isinstance(connections, dict):
                            # Flatten connections dict to individual properties with dotted keys
                            # This allows Cypher to access them via backticks while keeping
                            # them separate from regular node properties for filtering
                            for key, value in connections.items():
                                if value:  # Only add non-empty lists
                                    item[f"connections.{key}"] = value

                    items.append(item)

                # ========================================================================
                # PURE CYPHER: Filter connection properties before sending to Neo4j
                # ========================================================================
                # Instead of using apoc.map.removeKeys() in Cypher, we filter connection
                # properties in Python before sending to Neo4j. This eliminates APOC
                # dependency while maintaining graph-native architecture.
                #
                # Connection keys (e.g., "connections.requires", "connections.enables")
                # are extracted from extra_params['rel_config'] if available.
                # ========================================================================
                if extra_params and "rel_config" in extra_params:
                    # Get list of connection keys from relationship configuration
                    connection_keys = set(extra_params["rel_config"].keys())

                    # Filter out connection properties from each item
                    # Keep original items with connections for FOREACH clauses
                    # Create separate props dict with connections removed
                    filtered_items = []
                    for item_dict in items:
                        # Create a copy with connection keys removed for node properties
                        props = {k: v for k, v in item_dict.items() if k not in connection_keys}

                        # Add both filtered props and original item (for FOREACH access)
                        filtered_item = {
                            **item_dict,  # Keep connections for FOREACH clauses
                            "_node_props": props,  # Filtered properties for node storage
                        }
                        filtered_items.append(filtered_item)

                    params = {"items": filtered_items}
                else:
                    # No relationship config - use items as-is
                    params = {"items": items}
                if extra_params:
                    params.update(extra_params)

                # Begin transaction (must await to get the transaction object)
                tx = await self.session.begin_transaction()
                try:
                    result = await tx.run(template.template, params)
                    summary = await result.consume()

                    # Aggregate statistics
                    total_stats["nodes_created"] += summary.counters.nodes_created
                    total_stats["nodes_deleted"] += summary.counters.nodes_deleted
                    total_stats["relationships_created"] += summary.counters.relationships_created
                    total_stats["relationships_deleted"] += summary.counters.relationships_deleted
                    total_stats["properties_set"] += summary.counters.properties_set
                    total_stats["batches_processed"] += 1

                    await tx.commit()
                except Exception:
                    await tx.rollback()
                    raise

                self.logger.info(f"Processed batch {i // batch_size + 1}: {len(batch)} entities")

            self.logger.info(
                f"Batch execution complete: {len(entities)} entities in "
                f"{total_stats['batches_processed']} batches"
            )
            return Result.ok(total_stats)

        except Exception as e:
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

        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return Result.fail(Errors.database(operation=f"query_{template.name}", message=str(e)))

    async def execute_constraints(self, template: CypherTemplate) -> Result[list[str]]:
        """
        Execute constraint creation template.

        Constraints are idempotent with IF NOT EXISTS clause.

        Args:
            template: The constraint template to execute

        Returns:
            Result containing list of created constraint names
        """
        try:
            # Split template into individual constraint statements
            statements = [stmt.strip() for stmt in template.template.split(";") if stmt.strip()]

            created = []
            for statement in statements:
                if not statement:
                    continue

                try:
                    await self.session.run(statement)
                    # Extract constraint name from statement
                    if "CONSTRAINT" in statement and "IF NOT EXISTS" in statement:
                        # Parse constraint name
                        parts = statement.split()
                        idx = parts.index("CONSTRAINT")
                        if idx + 1 < len(parts):
                            name = parts[idx + 1]
                            created.append(name)
                            self.logger.info(f"Constraint ensured: {name}")
                except Exception as e:
                    # Constraint might already exist (older Neo4j versions)
                    if "already exists" in str(e).lower():
                        (self.logger.debug(f"Constraint already exists: {statement[:50]}..."),)
                    else:
                        raise

            return Result.ok(created)

        except Exception as e:
            self.logger.error(f"Constraint creation failed: {e}")
            return Result.fail(Errors.database(operation="create_constraints", message=str(e)))
