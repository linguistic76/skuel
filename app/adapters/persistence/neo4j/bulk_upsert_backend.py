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
  happens in Python (``adapters.persistence.neo4j.batch_preparer.prepare_batch_items``) before
  the Cypher runs.
- Relationship targets are matched (``MATCH``), not merged, so missing targets are
  silently skipped instead of creating stub nodes; the edge is created on a later
  re-ingest once both endpoints exist.

See: core/ports/ingestion_protocols.py (BulkUpsertOperations),
     /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
from adapters.persistence.neo4j.cypher_executor import CypherExecutor, CypherTemplate
from adapters.persistence.neo4j.timed_driver import neo4j_query_timeout
from core.ingestion.ingestion_types import IngestionResult, RelationshipConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

logger = get_logger("skuel.adapters.bulk_upsert")

# Bulk ingestion gets a 10-minute server-side tx timeout (vs. the 120s default)
# — large vector-bearing entity batches + multi-MERGE relationship transactions
# need headroom but should still be bounded.
_BULK_INGESTION_TIMEOUT_SECONDS: float = 600.0

# Templates were relocated alongside this backend (ADR-044).
_TEMPLATE_DIR = Path(__file__).parent / "cypher_templates"


def _label_clause(entity_label: str, base_label: str | None) -> str:
    """Neo4j label clause for MERGE/CREATE, e.g. 'Entity:Task' or just 'Group'."""
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


def build_node_upsert_template(
    entity_label: str,
    base_label: str | None,
) -> CypherTemplate:
    """
    Build the node-only upsert template (phase 1 of the two-phase ingest).

    Uses pre-filtered ``item._node_props`` for node storage — connection keys
    are excluded in Python (``batch_preparer``) so relationship sources never
    leak onto the node as properties.

    For ``:Entity``-based labels the template also maintains the owner edge:
    every row persisted with a ``user_uid`` property gets its
    ``(User)-[:OWNS]->(entity)`` edge and loses any :OWNS edge from OTHER
    users (single-owner invariant — a former owner must not keep access
    after a re-ingest under a different owner), restoring the invariant the
    June-2026 migration enforces from the other side (property == :OWNS owner). The
    owner is ``MATCH``ed, not ``MERGE``d, so an unknown user is silently
    skipped — same no-stub semantics as relationship targets. Carve-outs hold
    by construction: file-ingested exercises are ownerless curriculum content
    (the validator forces ``scope: curriculum`` and no ``user_uid``), and
    Group ownership is popped to ``owner_uid`` before this template runs.
    """
    label_clause = _label_clause(entity_label, base_label)
    owns_clause = ""
    if base_label == "Entity":
        owns_clause = """
// Owner edge — user_uid property implies :OWNS, single owner (edge props
// mirror the CRUD path's create_user_relationship shape; timestamps are
// Python-side ISO strings, matching the existing OWNS edge storage format).
// The stale-owner DELETE enforces the single-owner invariant on re-ingest:
// when the resolved owner changes (or an out-of-band edge exists), the
// former owner must not keep access through a leftover :OWNS edge.
WITH n, props
CALL {
  WITH n, props
  WITH n, props.user_uid AS _owner_uid
  WHERE _owner_uid IS NOT NULL
  OPTIONAL MATCH (_stale:User)-[_stale_owns:OWNS]->(n)
  WHERE _stale.uid <> _owner_uid
  DELETE _stale_owns
}
CALL {
  WITH n, props
  WITH n, props.user_uid AS _owner_uid
  WHERE _owner_uid IS NOT NULL
  MATCH (owner:User {uid: _owner_uid})
  MERGE (owner)-[_owns:OWNS]->(n)
    ON CREATE SET
      _owns.created_at = $owns_timestamp,
      _owns.last_accessed = $owns_timestamp,
      _owns.access_count = 0,
      _owns.is_active = true
}"""
    template_str = f"""
// Bulk node upsert (Pure Cypher - No APOC) — phase 1, edges come later
UNWIND $items AS item
WITH item, item._node_props AS props
MERGE (n:{label_clause} {{uid: item.uid}})
  ON CREATE SET
    n = props,
    n.created_at = datetime()
  ON MATCH SET
    n += props,
    n.updated_at = datetime()
{owns_clause}
RETURN count(n) as processed
"""
    return CypherTemplate(
        name=f"{entity_label.lower()}_node_upsert",
        template=template_str,
        description=f"Node-only bulk upsert for {entity_label}",
    )


def build_relationship_template(
    entity_label: str,
    base_label: str | None,
    config: dict[str, RelationshipConfig],
) -> CypherTemplate:
    """
    Build the relationships-only template (phase 2 of the two-phase ingest).

    ``MATCH``es the already-upserted source node, then one unit ``CALL``
    subquery per relationship field ``MATCH``es existing targets and ``MERGE``s
    the edge. ``MATCH`` (not ``MERGE``) on targets avoids stub nodes with
    incomplete labels. Running relationships strictly AFTER every node batch
    (all entity types) means same-sync forward references resolve — under
    incremental sync there is no "later re-ingest" for an unchanged file, so
    edges dropped on first contact would otherwise be dropped forever.

    Fields with ``order_property`` persist the YAML list index onto the edge
    (0-based, refreshed on every ingest so vault reorderings propagate).
    Zero APOC dependency.
    """
    rel_clauses = []

    for field_name, rel_info in config.items():
        rel_type = rel_info["rel_type"]
        target_label = rel_info["target_label"]
        direction = rel_info.get("direction", "outgoing")  # Default to outgoing
        order_property = rel_info.get("order_property")

        # Edge direction determines the semantic meaning of the relationship.
        # OUTGOING (n)-[:TYPE]->(target) is the default (prerequisites, enables);
        # INCOMING (n)<-[:TYPE]-(target) points back to n.
        if direction == "incoming":
            rel_pattern = f"(n)<-[_r:{rel_type}]-(target)"
        else:  # outgoing or bidirectional
            rel_pattern = f"(n)-[_r:{rel_type}]->(target)"

        # Unit subquery (no RETURN) preserves outer rows regardless of inner row
        # count, so later fields are unaffected when a target is missing.
        if order_property:
            rel_clause = f"""
// Handle {field_name} relationships ({direction}, ordered by list index)
CALL {{
  WITH n, item
  WITH n, coalesce(item.`{field_name}`, []) AS _target_uids
  UNWIND range(0, size(_target_uids) - 1) AS _idx
  WITH n, _target_uids[_idx] AS _target_uid, _idx
  MATCH (target:{target_label} {{uid: _target_uid}})
  MERGE {rel_pattern}
  SET _r.`{order_property}` = _idx
}}"""
        else:
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
// Bulk relationship creation (Pure Cypher - No APOC) — phase 2, nodes exist
UNWIND $items AS item
MATCH (n:{label_clause} {{uid: item.uid}})
{"".join(rel_clauses)}
RETURN count(n) as processed
"""

    return CypherTemplate(
        name=f"{entity_label.lower()}_relationships",
        template=template_str,
        description=f"Create relationships for {entity_label}",
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
        with neo4j_query_timeout(_BULK_INGESTION_TIMEOUT_SECONDS):
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

        with neo4j_query_timeout(_BULK_INGESTION_TIMEOUT_SECONDS):
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

    async def upsert_nodes(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        """Node-only upsert (phase 1) — connection fields filtered off the node."""
        template = build_node_upsert_template(entity_label, base_label)

        with neo4j_query_timeout(_BULK_INGESTION_TIMEOUT_SECONDS):
            async with self._driver.session() as session:
                executor = CypherExecutor(session, dict)
                items = prepare_batch_items(entities, rel_config=relationship_config)

                result = await executor.execute_batch(
                    template=template,
                    items=items,
                    batch_size=batch_size,
                    extra_params={
                        "entity_label": entity_label,
                        # OWNS edge ON CREATE timestamp — iso string to match
                        # the CRUD path's edge property format (writer decides
                        # storage type; existing OWNS edges store iso strings).
                        "owns_timestamp": datetime.now().isoformat(),
                    },
                )

                if result.is_error:
                    return Result.fail(result)

                stats = result.value
                return Result.ok(
                    IngestionResult(
                        total_processed=len(entities),
                        nodes_created=stats.get("nodes_created", 0),
                        nodes_updated=0,  # Calculated from properties_set when needed
                        relationships_created=0,
                        errors=[],
                    )
                )

    async def create_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        """Relationships-only pass (phase 2) — every node batch already ran."""
        if not relationship_config:
            return Result.ok(
                IngestionResult(
                    total_processed=len(entities),
                    nodes_created=0,
                    nodes_updated=0,
                    relationships_created=0,
                    errors=[],
                )
            )

        template = build_relationship_template(entity_label, base_label, relationship_config)

        with neo4j_query_timeout(_BULK_INGESTION_TIMEOUT_SECONDS):
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
                        nodes_created=0,
                        nodes_updated=0,
                        relationships_created=stats.get("relationships_created", 0),
                        errors=[],
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
        """Upsert entities, then create their graph edges (two-phase).

        Nodes land before any edge Cypher runs, so references between entities
        of the same call resolve (the single-file door's shape). Directory
        ingest calls the two phases itself so relationships run after EVERY
        type's node batch — see ``core/services/ingestion/batch.py``.
        """
        nodes_result = await self.upsert_nodes(
            entity_label, base_label, entities, relationship_config, batch_size
        )
        if nodes_result.is_error:
            return nodes_result

        rels_result = await self.create_relationships(
            entity_label, base_label, entities, relationship_config, batch_size
        )
        if rels_result.is_error:
            return rels_result

        nodes = nodes_result.value
        return Result.ok(
            IngestionResult(
                total_processed=len(entities),
                nodes_created=nodes.nodes_created,
                nodes_updated=nodes.nodes_updated,
                relationships_created=rels_result.value.relationships_created,
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
