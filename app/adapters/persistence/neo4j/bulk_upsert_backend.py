"""
Bulk Upsert Backend
===================

Bulk node upsert / constraint / delete Cypher for the ingestion pipeline, below
the hexagonal boundary (ADR-044). Relocated from ``core/ingestion/bulk_ingestion.py``
so that all graph writes — and the Cypher that generates them — live in the
adapter layer; the ingestion service orchestrates and calls this backend.

Like ``IngestionWriteBackend`` (its edge-write sibling), this backend uses the
raw ``AsyncDriver``/session API with **exception-based** error flow, because the
ingestion service and batch helpers already handle failures via
``try/except NEO4J_EXCEPTIONS``. It is intentionally STATELESS with respect to the
entity label: the label/base-label are passed per call (sourced from
``ENTITY_CONFIGS`` — trusted, never user input), so a single backend instance
serves every entity type and the per-label "constraints ensured once" bookkeeping
stays in the service.

GRAPH-NATIVE ARCHITECTURE (Pure Cypher — No APOC):
- Connection data becomes graph EDGES, never node properties. Property filtering
  happens in Python (``core.ingestion.batch_preparer.prepare_batch_items``) before
  the Cypher runs.
- Relationship targets are matched (``MATCH``), not merged, so missing targets are
  silently skipped instead of creating stub nodes; the edge is created on a later
  re-ingest once both endpoints exist.

See: core/ports/ingestion_protocols.py (BulkUpsertOperations),
     /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.cypher_executor import CypherExecutor, CypherTemplate
from core.ingestion.batch_preparer import prepare_batch_items
from core.ingestion.ingestion_types import IngestionResult, RelationshipConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = get_logger("skuel.adapters.bulk_upsert")

# Templates were relocated alongside this backend (ADR-044).
_TEMPLATE_DIR = Path(__file__).parent / "cypher_templates"


def _label_clause(entity_label: str, base_label: str | None) -> str:
    """Neo4j label clause for MERGE/CREATE, e.g. 'Entity:Task' or just 'Expense'."""
    if base_label and base_label != entity_label:
        return f"{base_label}:{entity_label}"
    return entity_label


def _get_template(template_name: str, subdir: str = "upserts") -> CypherTemplate:
    """Load a relocated ``.cypher`` template by name."""
    template_path = _TEMPLATE_DIR / subdir / f"{template_name}.cypher"
    if not template_path.exists():
        template_path = _TEMPLATE_DIR / f"{template_name}.cypher"
    return CypherTemplate.from_file(template_path)


def _create_default_upsert_template(entity_label: str, base_label: str | None) -> CypherTemplate:
    """Default MERGE-on-uid template for node-only upserts."""
    label_clause = _label_clause(entity_label, base_label)
    template_str = f"""
// Generic bulk upsert template
UNWIND $items AS item
MERGE (n:{label_clause} {{uid: item.uid}})
  ON CREATE SET
    n = item,
    n.created_at = datetime()
  ON MATCH SET
    n += item,
    n.updated_at = datetime()
RETURN count(n) as processed
"""
    return CypherTemplate(
        name=f"default_{entity_label.lower()}_upsert",
        template=template_str,
        description=f"Default bulk upsert for {entity_label}",
    )


def build_relationship_template(
    entity_label: str,
    base_label: str | None,
    config: dict[str, RelationshipConfig],
) -> CypherTemplate:
    """
    Build a Cypher template that creates graph edges from connection data.

    Uses pre-filtered ``item._node_props`` for node storage (connection keys
    excluded in Python) and a unit ``CALL`` subquery per relationship field that
    ``MATCH``es existing targets and ``MERGE``s the edge. ``MATCH`` (not ``MERGE``)
    on targets avoids stub nodes with incomplete labels; missing targets are
    skipped and linked on a later re-ingest. Zero APOC dependency.
    """
    rel_clauses = []

    for field_name, rel_info in config.items():
        rel_type = rel_info["rel_type"]
        target_label = rel_info["target_label"]
        direction = rel_info.get("direction", "outgoing")  # Default to outgoing

        # Edge direction determines the semantic meaning of the relationship.
        # OUTGOING (n)-[:TYPE]->(target) is the default (prerequisites, enables);
        # INCOMING (n)<-[:TYPE]-(target) points back to n.
        if direction == "incoming":
            rel_pattern = f"(n)<-[:{rel_type}]-(target)"
        else:  # outgoing or bidirectional
            rel_pattern = f"(n)-[:{rel_type}]->(target)"

        # Unit subquery (no RETURN) preserves outer rows regardless of inner row
        # count, so the main entity upsert is unaffected when a target is missing.
        rel_clause = f"""
// Handle {field_name} relationships ({direction})
CALL {{
  WITH n, item
  WITH n, coalesce(item.`{field_name}`, []) AS _target_uids
  UNWIND _target_uids AS _target_uid
  MATCH (target:{target_label} {{uid: _target_uid}})
  MERGE {rel_pattern}
}}"""
        rel_clauses.append(rel_clause)

    label_clause = _label_clause(entity_label, base_label)
    template_str = f"""
// Bulk upsert with relationships (Pure Cypher - No APOC)
UNWIND $items AS item
// Connection data is used to create EDGES, not stored as node properties.
// item._node_props is pre-filtered in Python (batch_preparer) to exclude the
// connection keys, so the node carries only non-relationship properties.
WITH item, item._node_props AS props
MERGE (n:{label_clause} {{uid: item.uid}})
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
        name=f"{entity_label.lower()}_with_relationships",
        template=template_str,
        description=f"Upsert {entity_label} with relationships",
    )


class BulkUpsertBackend:
    """Raw-driver bulk node upsert / constraint / delete Cypher (ADR-044).

    Stateless w.r.t. entity label — label/base-label are passed per call, so one
    instance serves all entity types. Implements ``BulkUpsertOperations``.
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver
        self.logger = logger

    async def ensure_constraints(self, entity_label: str) -> Result[list[str]]:
        """Run the constraint template for ``entity_label`` (no-op if none exists)."""
        async with self._driver.session() as session:
            executor = CypherExecutor(session, dict)
            try:
                template = _get_template(
                    f"{entity_label.lower()}_constraints", subdir="constraints"
                )
                return await executor.execute_constraints(template)
            except FileNotFoundError:
                self.logger.debug(f"No constraint template for {entity_label}")
                return Result.ok([])

    async def upsert_batch(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        batch_size: int = 1000,
        template_name: str | None = None,
    ) -> Result[IngestionResult]:
        """Node-only bulk upsert (default template or a named ``.cypher`` file)."""
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

        start_time = time.time()

        if template_name:
            template = _get_template(template_name)
        else:
            template = _create_default_upsert_template(entity_label, base_label)

        async with self._driver.session() as session:
            executor = CypherExecutor(session, dict)
            items = prepare_batch_items(entities)

            result = await executor.execute_batch(
                template=template,
                items=items,
                batch_size=batch_size,
                extra_params={"entity_label": entity_label},
            )

            if result.is_error:
                return Result.fail(result)

            stats = result.value
            duration = (time.time() - start_time) * 1000
            # Updates = properties set minus creates.
            nodes_updated = max(0, stats.get("properties_set", 0) - stats.get("nodes_created", 0))

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

    async def upsert_with_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        """Upsert entities and create their graph edges in one batched transaction."""
        template = build_relationship_template(entity_label, base_label, relationship_config)

        async with self._driver.session() as session:
            executor = CypherExecutor(session, dict)
            items = prepare_batch_items(entities, rel_config=relationship_config)

            result = await executor.execute_batch(
                template=template,
                items=items,
                batch_size=batch_size,
                extra_params={"entity_label": entity_label},
            )

            if result.is_error:
                return Result.fail(result)

            stats = result.value
            return Result.ok(
                IngestionResult(
                    total_processed=len(entities),
                    nodes_created=stats.get("nodes_created", 0),
                    nodes_updated=0,  # Calculated from properties_set when needed
                    relationships_created=stats.get("relationships_created", 0),
                    errors=[],
                )
            )

    async def delete_batch(
        self, entity_label: str, uids: list[str], cascade: bool = False
    ) -> Result[IngestionResult]:
        """Bulk delete entities by uid (``DETACH DELETE`` or cascade)."""
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
MATCH (n:{entity_label} {{uid: uid}})
OPTIONAL MATCH (n)-[r]-()
DELETE r, n
RETURN count(n) as deleted
"""
        else:
            template_str = f"""
// Simple delete
UNWIND $uids AS uid
MATCH (n:{entity_label} {{uid: uid}})
DETACH DELETE n
RETURN count(n) as deleted
"""

        async with self._driver.session() as session:
            result = await session.run(template_str, {"uids": uids})
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
