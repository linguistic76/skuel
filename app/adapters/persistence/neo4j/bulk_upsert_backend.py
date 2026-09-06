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

from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
from adapters.persistence.neo4j.cypher_executor import CypherExecutor, CypherTemplate
from adapters.persistence.neo4j.timed_driver import neo4j_query_timeout
from core.ingestion.ingestion_types import IngestionResult, RelationshipConfig
from core.models.enums.neo_labels import NeoLabel
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession

logger = get_logger("skuel.adapters.bulk_upsert")

# Bulk ingestion gets a 10-minute server-side tx timeout (vs. the 120s default)
# — large vector-bearing entity batches + multi-MERGE relationship transactions
# need headroom but should still be bounded.
_BULK_INGESTION_TIMEOUT_SECONDS: float = 600.0

# Carries MERGE's create/match signal from the ON CREATE / ON MATCH branches to
# the property write, which can no longer live in those branches: the node's
# PRIOR status has to be read between the MERGE and the write that overwrites it
# (ADR-087 — the prior is read under the node's write-lock, never before the
# statement). The marker is removed in the same transaction and is never
# committed; the created branch's ``SET n = props`` already drops it, so the
# REMOVE is the matched branch's cleanup. Named once because Cypher reads an
# unknown property as null rather than erroring, which would silently turn the
# flag into a constant. (Same device as ``IngestionWriteBackend``'s edge-writer
# marker.)
_CREATE_MARKER = "_ingest_new"


def _label_clause(entity_label: str, base_label: str | None) -> str:
    """Neo4j label clause for MERGE/CREATE, e.g. 'Entity:Task' or just 'Group'."""
    if base_label and base_label != entity_label:
        return f"{base_label}:{entity_label}"
    return entity_label


def _prior_statuses(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    """Map ``uid`` → the status each node held BEFORE this upsert wrote to it.

    Reads the node template's rows (see :func:`build_node_upsert_template`).
    Rows without a ``uid`` key are skipped rather than assumed: ``execute_batch``
    is shared with the relationship template, whose single ``count(n)`` row has a
    different shape.
    """
    prior: dict[str, str | None] = {}
    for row in rows:
        uid = row.get("uid")
        if uid is None:
            continue
        status = row.get("prior_status")
        prior[str(uid)] = None if status is None else str(status)
    return prior


def build_node_upsert_template(
    entity_label: str,
    base_label: str | None,
) -> CypherTemplate:
    """
    Build the node-only upsert template (phase 1 of the two-phase ingest).

    Uses pre-filtered ``item._node_props`` for node storage — connection keys
    are excluded in Python (``batch_preparer``) so relationship sources never
    leak onto the node as properties.

    Returns one row per item carrying ``uid`` and the node's **prior status** —
    the status the node held before this ingest overwrote it, read between the
    ``MERGE`` and the property write and therefore under the node's write-lock
    (ADR-087: a status transition is decided BY the write, never before it).
    That prior is what lets the vault door tell a genuine completion from a
    ``--force`` re-ingest of an already-completed file, and a reopen from an
    ordinary edit. ``null`` for a node this batch created — a create has no
    prior status.

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
    Group ownership is popped to ``owner_uid`` before this template runs —
    a Group's ``:OWNS`` edge is the single-file door's second statement,
    whose MERGE count fails the file on an unknown owner (ADR-086 § 1 door 5).
    """
    label_clause = _label_clause(entity_label, base_label)
    owns_clause = ""
    if base_label == "Entity":
        owns_clause = """
// Owner edge — user_uid property implies :OWNS, single owner (edge props
// mirror the CRUD create door's :OWNS edge shape — ADR-086; timestamps are
// Python-side ISO strings, matching the existing OWNS edge storage format).
// The stale-owner DELETE enforces the single-owner invariant on re-ingest:
// when the resolved owner changes (or an out-of-band edge exists), the
// former owner must not keep access through a leftover :OWNS edge.
WITH item, props, n, prior_status
CALL (n, props) {
  WITH n, props.user_uid AS _owner_uid
  WHERE _owner_uid IS NOT NULL
  OPTIONAL MATCH (_stale:User)-[_stale_owns:OWNS]->(n)
  WHERE _stale.uid <> _owner_uid
  DELETE _stale_owns
}
CALL (n, props) {
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
  ON CREATE SET n.{_CREATE_MARKER} = true
  ON MATCH SET n.{_CREATE_MARKER} = false
// The prior status is read here — after the MERGE took the node's write-lock,
// before the property write overwrites it (ADR-087). The create/match branches
// therefore move out of MERGE and into the FOREACHes below, which preserve
// their semantics exactly: `n = props` REPLACES, `n += props` MERGES.
WITH item, props, n, n.status AS prior_status, n.{_CREATE_MARKER} AS created
FOREACH (_ IN CASE WHEN created THEN [1] ELSE [] END |
  SET n = props,
      n.created_at = coalesce(props.created_at, toString(datetime())))
FOREACH (_ IN CASE WHEN created THEN [] ELSE [1] END |
  SET n += props,
      n.updated_at = datetime())
REMOVE n.{_CREATE_MARKER}
{owns_clause}
RETURN item.uid AS uid, prior_status
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
CALL (n, item) {{
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
CALL (n, item) {{
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

    async def upsert_nodes(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, Any]],
        relationship_config: dict[str, RelationshipConfig],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        """Node-only upsert (phase 1) — connection fields filtered off the node.

        Refuses the whole batch when an owner it names has no ``:User`` node —
        see :meth:`_refuse_unknown_owners` (ADR-086 door 2 hardening).
        """
        template = build_node_upsert_template(entity_label, base_label)

        with neo4j_query_timeout(_BULK_INGESTION_TIMEOUT_SECONDS):
            async with self._driver.session() as session:
                executor = CypherExecutor(session, dict)
                items = prepare_batch_items(entities, rel_config=relationship_config)

                refusal = await self._refuse_unknown_owners(session, base_label, items)
                if refusal is not None:
                    return refusal

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
                        prior_status_by_uid=_prior_statuses(stats.get("rows", [])),
                    )
                )

    async def _refuse_unknown_owners(
        self,
        session: "AsyncSession",
        base_label: str | None,
        # boundary: prepared batch items are genuinely heterogeneous — a uid
        # string, the nested ``_node_props`` map, and one flattened list per
        # connection key. This is the type ``prepare_batch_items`` returns and
        # ``upsert_nodes``/``execute_batch`` already declare; narrowing it here
        # alone would be a cast asserting a shape nothing produces.
        items: list[dict[str, Any]],
    ) -> Result[IngestionResult] | None:
        """Refuse the batch when an owner it names has no ``:User`` node.

        The invariant every write door owes is ``user_uid`` property ==
        ``:OWNS`` owner (ADR-086). The upsert template holds it for a KNOWN
        owner, but its owner ``MATCH`` sits in a row-preserving unit subquery
        *after* the node persists — so an unknown owner used to yield a
        property-only node while the ingest reported success. That orphan is
        invisible to every ``:OWNS``-traversing read (MEGA-QUERY,
        ``get_user_entities``, the GDPR cascade) and the only signal was an
        integration test.

        This is the loud half of the no-stub choice: the door still never
        ``MERGE``s a ``:User`` — it refuses instead of inventing one. The
        batch's owner set is normally a single descriptor-resolved owner, so a
        miss means the whole batch would land orphaned; refusing all of it is
        the honest verdict, and it names the owner so the cause (a deleted
        user, a stale vault descriptor, a mistyped ``SKUEL_DEFAULT_USER_UID``)
        is diagnosable from the error alone.

        Scoped to ``:Entity`` batches keyed on ``_node_props.user_uid`` —
        exactly what the template's owns clause reads, so the check cannot
        drift from the write it guards. Group's ``owner_uid`` is popped before
        this template runs (its owner is checked by the Group door's own edge
        write — the MERGE count, ADR-086 § 1 door 5) and ownerless curriculum
        names no owner at all; both yield an empty owner set and skip the
        query entirely.

        The check is a pre-flight, not a lock: a user deleted between it and the
        upsert still yields the old property-only node. Closing that window
        would mean gating the node write on the owner ``MATCH``, which drops
        the row from the stream instead — a silent under-write, worse than the
        shape it replaces. The residual window is covered where it always was,
        from the other side: the June-2026 repair migration and
        ``tests/integration/test_owner_only_ownership_invariant.py``.

        The refusal is a DATABASE-category error on purpose, matching door 1's
        unknown-owner refusal (``_crud_mixin._create_node``, "owner ... must be
        an existing User"): the ingestion report files VALIDATION-category
        failures under *ignored-with-reason*, and a refused batch is a failure
        the sync must show, not a file it chose to skip.

        Returns:
            A failed Result to return from the caller, or None to proceed.
        """
        if base_label != "Entity":
            return None

        owner_uids = sorted(
            {
                str(owner)
                for item in items
                if (owner := item.get("_node_props", item).get("user_uid"))
            }
        )
        if not owner_uids:
            return None

        # This lookup runs on the raw session, outside CypherExecutor — which is
        # what converts NEO4J_EXCEPTIONS into a Result for the batch write below.
        # Without this guard a driver timeout or disconnect would raise straight
        # out of a method whose signature promises a Result, and ingest_directory
        # branches on ``result.is_ok`` with no try/except around the call. The
        # conversion is also fail-CLOSED by construction: an owner set we could
        # not verify returns a failure, so the batch never runs.
        try:
            result = await session.run(
                f"""
                UNWIND $owner_uids AS owner_uid
                OPTIONAL MATCH (u:{NeoLabel.USER.value} {{uid: owner_uid}})
                WITH owner_uid, u
                WHERE u IS NULL
                RETURN collect(owner_uid) AS missing
                """,
                {"owner_uids": owner_uids},
            )
            record = await result.single()
        except NEO4J_EXCEPTIONS as e:
            self.logger.error(f"Owner pre-flight failed, refusing the batch: {e}")
            return Result.fail(
                Errors.database(
                    "upsert_nodes",
                    f"Could not verify the batch's owner(s) {owner_uids} against the "
                    f"graph ({e}); refusing rather than persisting entities whose "
                    "ownership edge may never be written (ADR-086).",
                )
            )
        missing = list(record["missing"]) if record else []
        if not missing:
            return None

        self.logger.error(
            f"Ingestion refused: {len(missing)} owner(s) named by this batch have no "
            f"User node — {missing}"
        )
        return Result.fail(
            Errors.database(
                "upsert_nodes",
                f"Ingestion refused — owner(s) {missing} have no :User node, so the "
                f"{len(items)} entities in this batch would persist with a user_uid "
                "nobody owns (ADR-086: user_uid property == :OWNS owner). Create the "
                "user, or correct the vault descriptor / SKUEL_DEFAULT_USER_UID that "
                "named it.",
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
                # The prior statuses belong to phase 1; phase 2 writes only edges.
                prior_status_by_uid=nodes.prior_status_by_uid,
            )
        )
