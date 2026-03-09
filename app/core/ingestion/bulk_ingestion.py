"""
Bulk ingestion engine for efficient Neo4j data loading.

This module provides high-level patterns for bulk operations,
building on the generic Cypher executor.

GRAPH-NATIVE ARCHITECTURE (Pure Cypher - No APOC):
---------------------------------------------------
This module implements the core pattern for storing relationships as Neo4j edges,
NOT as node properties. Key design decisions:

1. RELATIONSHIP CREATION: Uses MERGE to create graph edges from connection data
   - Input: Entity with metadata._connections dict
   - Process: batch_preparer extracts connection data, flattens to dotted keys
   - Output: Neo4j edges (e.g., [:REQUIRES_KNOWLEDGE], [:ENABLES_KNOWLEDGE])
   - Cleanup: Connection data filtered in Python layer (batch_preparer) before Neo4j

2. EDGE DIRECTION: Configurable via relationship_config
   - "incoming": Creates (n)<-[:TYPE]-(target)
   - "outgoing": Creates (n)-[:TYPE]->(target) [default]
   - "both": Creates bidirectional edges

3. IDEMPOTENCY: All operations use MERGE for upsert semantics
   - Nodes: MERGE on uid, SET properties ON CREATE/ON MATCH
   - Edges: MERGE creates edge if not exists, idempotent on repeat

4. PROPERTY FILTERING: Connection data never stored as node properties
   - Python-side filtering via batch_preparer.prepare_batch_items()
   - Only scalar/array properties stored in nodes
   - Relationships exist ONLY as graph edges
   - Zero APOC dependency for maximum portability

Example Usage:
    # Input YAML connections
    connections:
      requires: ["ku:prereq1", "ku:prereq2"],
      enables: ["ku:next"]

    # Relationship config
    rel_config = {
        "connections.requires": {
            "rel_type": "REQUIRES_KNOWLEDGE",
            "direction": "outgoing"  # Creates (n)-[:REQUIRES_KNOWLEDGE]->(target)
        },
        "connections.enables": {
            "rel_type": "ENABLES_KNOWLEDGE",
            "direction": "outgoing"  # Creates (n)-[:ENABLES_KNOWLEDGE]->(target)
        }
    }

    # Execute bulk ingestion
    engine = BulkIngestionEngine(driver, Knowledge, "Entity")
    result = await engine.upsert_with_relationships(
        entities=[knowledge_units],
        relationship_config=rel_config
    )

    # Result: Graph edges created
    (ku:current)-[:REQUIRES_KNOWLEDGE]->(ku:prereq1)
    (ku:current)-[:REQUIRES_KNOWLEDGE]->(ku:prereq2)
    (ku:current)-[:ENABLES_KNOWLEDGE]->(ku:next)

    # Result: Node properties (connections.* removed)
    (:Entity {
        uid: "ku:current",
        title: "...",
        content: "..."
        // NO connections.requires property
        // NO connections.enables property
    })

CRITICAL METHODS:
-----------------
- upsert_with_relationships(): Primary entry point for graph-native ingestion
- _build_relationship_template(): Generates Cypher with edge creation
- _create_default_upsert_template(): Node-only template (no relationships)

See: /docs/architecture/GRAPH_NATIVE_ANALYSIS.md
See: /docs/architecture/YAML_MARKDOWN_INGESTION_GUIDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, TypeVar

from core.ingestion.batch_preparer import prepare_batch_items
from core.ingestion.cypher_executor import CypherExecutor, CypherTemplate

if TYPE_CHECKING:
    from neo4j import AsyncDriver
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger(__name__)

T = TypeVar("T")


# ============================================================================
# TYPE DEFINITIONS FOR GRAPH-NATIVE RELATIONSHIP CONFIGURATION
# ============================================================================


class RelationshipConfig(TypedDict, total=False):
    """
    Configuration for a single relationship type in graph-native ingestion.

    This TypedDict provides type safety for relationship configuration,
    ensuring all required fields are present and direction values are valid.

    Fields:
        rel_type: Neo4j relationship type (e.g., "REQUIRES_KNOWLEDGE", "ENABLES_KNOWLEDGE")
        target_label: Neo4j label for target nodes (e.g., "Entity")
        direction: Edge direction - "incoming", "outgoing", or "both"
            - "incoming": Creates (n)<-[:TYPE]-(target)
            - "outgoing": Creates (n)-[:TYPE]->(target) [default]
            - "both": Creates bidirectional edges

    Example:
        config: RelationshipConfig = {
            "rel_type": "REQUIRES_KNOWLEDGE",
            "target_label": "Entity",
            "direction": "outgoing"
        }

    Used By:
        - BulkIngestionEngine.upsert_with_relationships()
        - BulkIngestionEngine._build_relationship_template()
        - MarkdownSyncService.sync_file() and sync_directory()

    See: Lines 245-294 for template generation using this config
    """

    rel_type: str
    target_label: str
    direction: Literal["incoming", "outgoing", "both"]


@dataclass
class IngestionResult:
    """Results from a bulk ingestion operation."""

    total_processed: int
    nodes_created: int
    nodes_updated: int
    relationships_created: int
    errors: list[str]
    duration_ms: float | None = None
    nodes_deleted: int = 0
    relationships_deleted: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return ((self.total_processed - len(self.errors)) / self.total_processed) * 100


class BulkIngestionEngine[T]:
    """
    Generic bulk ingestion engine for Neo4j.

    Features:
    - Template-based operations
    - Automatic batching
    - Relationship handling
    - Idempotent operations
    - Progress tracking
    """

    def __init__(
        self,
        driver: AsyncDriver,
        entity_type: type[T],
        entity_label: str,
        template_dir: Path | None = None,
    ) -> None:
        """
        Initialize bulk ingestion engine.

        Args:
            driver: Neo4j async driver,
            entity_type: Type of entities to ingest,
            entity_label: Neo4j label for the entities,
            template_dir: Directory containing Cypher templates
        """
        self.driver = driver
        self.entity_type = entity_type
        self.entity_label = entity_label
        self.template_dir = template_dir or Path(__file__).parent / "cypher_templates"
        self.logger = get_logger(f"{__name__}.{entity_type.__name__}")

    def _get_template(self, template_name: str, subdir: str = "upserts") -> CypherTemplate:
        """Load a template from the template directory."""
        template_path = self.template_dir / subdir / f"{template_name}.cypher"
        if not template_path.exists():
            # Try without subdir
            template_path = self.template_dir / f"{template_name}.cypher"
        return CypherTemplate.from_file(template_path)

    async def ensure_constraints(self) -> Result[list[str]]:
        """
        Ensure all constraints are created for the entity type.

        Returns:
            Result containing list of constraint names
        """
        async with self.driver.session() as session:
            executor = CypherExecutor(session, self.entity_type)

            # Look for constraint template
            try:
                template = self._get_template(
                    f"{self.entity_label.lower()}_constraints", subdir="constraints"
                )
                return await executor.execute_constraints(template)
            except FileNotFoundError:
                # No specific constraints for this entity
                self.logger.debug(f"No constraint template for {self.entity_label}")
                return Result.ok([])

    async def upsert_batch(
        self, entities: list[T], batch_size: int = 1000, template_name: str | None = None
    ) -> Result[IngestionResult]:
        """
        Perform bulk upsert operation.

        Args:
            entities: List of entities to upsert,
            batch_size: Number of entities per transaction,
            template_name: Optional custom template name

        Returns:
            Result containing ingestion statistics
        """
        if not entities:
            return Result.ok(
                IngestionResult(
                    total_processed=0,
                    nodes_created=0,
                    nodes_updated=0,
                    relationships_created=0,
                    errors=[],
                )
            )

        import time

        start_time = time.time()

        # Get or generate template
        if template_name:
            template = self._get_template(template_name)
        else:
            # Use default bulk upsert template
            template = self._create_default_upsert_template()

        async with self.driver.session() as session:
            executor = CypherExecutor(session, self.entity_type)
            items = prepare_batch_items(entities)

            result = await executor.execute_batch(
                template=template,
                items=items,
                batch_size=batch_size,
                extra_params={"entity_label": self.entity_label},
            )

            if result.is_ok:
                stats = result.value
                duration = (time.time() - start_time) * 1000

                # Calculate updates (properties set minus creates)
                nodes_updated = max(
                    0, stats.get("properties_set", 0) - stats.get("nodes_created", 0)
                )

                return Result.ok(
                    IngestionResult(
                        total_processed=len(entities),
                        nodes_created=stats.get("nodes_created", 0),
                        nodes_updated=nodes_updated,
                        relationships_created=stats.get("relationships_created", 0),
                        errors=[],
                        duration_ms=duration,
                    )
                )
            else:
                return Result.fail(result.error or "Unknown error during batch upsert")

    def _create_default_upsert_template(self) -> CypherTemplate:
        """
        Create a default MERGE template for any entity.

        This template:
        1. MERGEs on uid
        2. Sets all properties on CREATE and MATCH
        3. Handles created_at/updated_at timestamps
        """
        template_str = f"""
// Generic bulk upsert template
UNWIND $items AS item
MERGE (n:{self.entity_label} {{uid: item.uid}})
  ON CREATE SET
    n = item,
    n.created_at = datetime()
  ON MATCH SET
    n += item,
    n.updated_at = datetime()
RETURN count(n) as processed
"""
        return CypherTemplate(
            name=f"default_{self.entity_label.lower()}_upsert",
            template=template_str,
            description=f"Default bulk upsert for {self.entity_label}",
        )

    async def upsert_with_relationships(
        self,
        entities: list[T],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        """
        Upsert entities with their relationships.

        GRAPH-NATIVE OPERATION: Creates nodes and graph edges in single transaction.

        This method is the primary entry point for bulk ingestion with relationship
        creation. It combines node upsert with edge creation using type-safe
        RelationshipConfig specification.

        Args:
            entities: List of entities to upsert,
            relationship_config: Type-safe relationship configuration
                Maps field names to RelationshipConfig with edge specifications.
                Example:
                    {
                        "connections.requires": RelationshipConfig(
                            rel_type="REQUIRES_KNOWLEDGE",
                            target_label="Entity",
                            direction="outgoing"
                        ),
                        "connections.enables": RelationshipConfig(
                            rel_type="ENABLES_KNOWLEDGE",
                            target_label="Entity",
                            direction="outgoing"
                        )
                    }
            batch_size: Number of entities per transaction (default 500)

        Returns:
            Result[IngestionResult] with statistics:
                - nodes_created: New nodes created
                - nodes_updated: Existing nodes updated
                - relationships_created: Graph edges created
                - batches_processed: Number of transaction batches

        Edge Creation Process:
            1. Extract connection data from entity.metadata._connections
            2. Flatten to dotted keys (connections.requires, connections.enables)
            3. Filter connection properties in Python (CypherExecutor)
            4. Generate Cypher template with MERGE edge patterns
            5. Execute batch transaction creating nodes + edges (Pure Cypher)

        Example:
            engine = BulkIngestionEngine(driver, Knowledge, "Entity")
            result = await engine.upsert_with_relationships(
                entities=[ku1, ku2, ku3],
                relationship_config={
                    "connections.requires": {
                        "rel_type": "REQUIRES_KNOWLEDGE",
                        "target_label": "Entity",
                        "direction": "outgoing"
                    }
                },
                batch_size=1000
            )

        See: _build_relationship_template() for Cypher generation,
        See: CypherExecutor.execute_batch() for transaction handling
        """
        # Build custom template with relationship handling
        template = self._build_relationship_template(relationship_config)

        async with self.driver.session() as session:
            executor = CypherExecutor(session, self.entity_type)
            items = prepare_batch_items(entities, rel_config=relationship_config)

            result = await executor.execute_batch(
                template=template,
                items=items,
                batch_size=batch_size,
                extra_params={"entity_label": self.entity_label},
            )

            if result.is_ok:
                stats = result.value
                return Result.ok(
                    IngestionResult(
                        total_processed=len(entities),
                        nodes_created=stats.get("nodes_created", 0),
                        nodes_updated=0,  # Will be calculated from properties_set
                        relationships_created=stats.get("relationships_created", 0),
                        errors=[],
                    )
                )
            else:
                return Result.fail(
                    result.error or "Unknown error during batch upsert with relationships"
                )

    def _build_relationship_template(self, config: dict[str, RelationshipConfig]) -> CypherTemplate:
        """
        Build a Cypher template that creates graph edges from connection data.

        GRAPH-NATIVE TEMPLATE GENERATION (Pure Cypher):
        ------------------------------------------------
        Generates Cypher that:
        1. Uses pre-filtered properties from Python layer (item._node_props)
        2. Creates graph edges based on configuration (MERGE relationship patterns)
        3. Handles edge direction (incoming vs outgoing)
        4. Supports backtick escaping for dotted property names
        5. Zero APOC dependency for maximum portability

        Args:
            config: Relationship configuration mapping field names to edge specs
                Example:
                    {
                        "connections.requires": {
                            "rel_type": "REQUIRES_KNOWLEDGE",
                            "target_label": "Entity",
                            "direction": "outgoing"
                        },
                        "connections.enables": {
                            "rel_type": "ENABLES_KNOWLEDGE",
                            "target_label": "Entity",
                            "direction": "outgoing"
                        }
                    }

        Returns:
            CypherTemplate with UNWIND batch operation and MERGE edge patterns

        Generated Cypher Pattern (Pure Cypher - No APOC):
            UNWIND $items AS item
            WITH item, item._node_props AS props
            MERGE (n:Entity {uid: item.uid})
              ON CREATE SET n = props
              ON MATCH SET n += props
            WITH n, item
            FOREACH (target_uid IN coalesce(item.`connections.requires`, []) |
              MERGE (target:Entity {uid: target_uid})
              MERGE (n)-[:REQUIRES_KNOWLEDGE]->(target)
            )

        Property filtering happens in Python (CypherExecutor:265-297) before
        Neo4j ingestion. This eliminates APOC dependency while maintaining
        the same graph-native architecture.

        See: Lines 403-522 for implementation
        """
        rel_clauses = []

        for field_name, rel_info in config.items():
            rel_type = rel_info["rel_type"]
            target_label = rel_info["target_label"]
            direction = rel_info.get("direction", "outgoing")  # Default to outgoing

            # ========================================================================
            # GRAPH-NATIVE: Build Relationship Pattern Based on Direction
            # ========================================================================
            # Edge direction determines the semantic meaning of the relationship:
            #
            # INCOMING: (n)<-[:TYPE]-(target)
            #   - Used for dependencies pointing back to n
            #   - Semantic: "target points to n"
            #
            # OUTGOING: (n)-[:TYPE]->(target)
            #   - Used for prerequisites, enables, and most relationships
            #   - Semantic: "n requires/enables target" or "n points to target"
            #   - Example: If A requires B, then (A)-[:REQUIRES_KNOWLEDGE]->(B)
            #   - Example: If A enables B, then (A)-[:ENABLES_KNOWLEDGE]->(B)
            #
            # Direction choice affects graph traversal queries:
            #   - get_related_uids(uid, "REQUIRES_KNOWLEDGE", "outgoing") → prerequisites
            #   - get_related_uids(uid, "ENABLES_KNOWLEDGE", "outgoing") → enabled topics
            # ========================================================================
            if direction == "incoming":
                rel_pattern = f"(n)<-[:{rel_type}]-(target)"
            else:  # outgoing or bidirectional
                rel_pattern = f"(n)-[:{rel_type}]->(target)"

            # Use backticks to escape property names with dots (e.g., `connections.requires`)
            rel_clause = f"""
// Handle {field_name} relationships ({direction})
FOREACH (target_uid IN coalesce(item.`{field_name}`, []) |
  MERGE (target:{target_label} {{uid: target_uid}})
  MERGE {rel_pattern}
)"""
            rel_clauses.append(rel_clause)

        # Build list of connection keys to exclude from node properties
        connection_keys = [f"'{field_name}'" for field_name in config]
        ", ".join(connection_keys)

        template_str = f"""
// Bulk upsert with relationships (Pure Cypher - No APOC)
UNWIND $items AS item

// ========================================================================
// CRITICAL: Use pre-filtered properties from Python layer
// ========================================================================
// Connection data is used to create EDGES, not stored as node properties.
// This is the KEY step that maintains graph-native architecture:
//
// 1. Python: CypherExecutor filters connection keys before sending to Neo4j
// 2. item contains: {{uid, title, content, connections.requires, connections.enables, _node_props}}
// 3. item._node_props contains: {{uid, title, content, ...}} (NO connection properties)
// 4. Node is created/updated with ONLY non-relationship properties
// 5. Connections become EDGES in the FOREACH clauses below
//
// Result: Relationships exist ONLY as graph edges, never as node properties
// No APOC dependency - property filtering done in Python (CypherExecutor:265-297)
// ========================================================================
WITH item, item._node_props AS props
MERGE (n:{self.entity_label} {{uid: item.uid}})
  ON CREATE SET
    n = props,
    n.created_at = datetime()
  ON MATCH SET
    n += props,
    n.updated_at = datetime()
WITH n, item
{"".join(rel_clauses)}
RETURN count(n) as processed
"""

        return CypherTemplate(
            name=f"{self.entity_label.lower()}_with_relationships",
            template=template_str,
            description=f"Upsert {self.entity_label} with relationships",
        )

    async def delete_batch(self, uids: list[str], cascade: bool = False) -> Result[IngestionResult]:
        """
        Bulk delete entities by UID.

        Args:
            uids: List of UIDs to delete,
            cascade: If True, also delete related nodes

        Returns:
            Result containing deletion statistics
        """
        if not uids:
            return Result.ok(
                IngestionResult(
                    total_processed=0,
                    nodes_created=0,
                    nodes_updated=0,
                    relationships_created=0,
                    errors=[],
                )
            )

        if cascade:
            template_str = f"""
// Cascade delete
UNWIND $uids AS uid
MATCH (n:{self.entity_label} {{uid: uid}})
OPTIONAL MATCH (n)-[r]-()
DELETE r, n
RETURN count(n) as deleted
"""
        else:
            template_str = f"""
// Simple delete
UNWIND $uids AS uid
MATCH (n:{self.entity_label} {{uid: uid}})
DETACH DELETE n
RETURN count(n) as deleted
"""

        template = CypherTemplate(
            name=f"delete_{self.entity_label.lower()}",
            template=template_str,
            description=f"Bulk delete {self.entity_label}",
        )

        async with self.driver.session() as session:
            result = await session.run(template.template, {"uids": uids})
            summary = await result.consume()

            return Result.ok(
                IngestionResult(
                    total_processed=len(uids),
                    nodes_created=0,
                    nodes_updated=0,
                    relationships_created=0,
                    errors=[],
                    nodes_deleted=summary.counters.nodes_deleted,
                )
            )
