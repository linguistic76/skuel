"""Guard: PS/LP context routes serve mechanism B; the bespoke readers are gone.

Convergence Phase 3 deleted four production-DEAD bespoke PS/LP graph-context readers
(``ps.core.get_with_context`` → ``backend.get_step_with_context``,
``ps.graph.get_step_with_context``, ``lp.core.get_with_context`` →
``backend.get_path_with_graph_context``, ``lp.intelligence.get_path_with_context`` →
``backend.get_path_with_context``) that returned curated/user-scoped shapes outside
mechanism B. The B1 audit proved — and the live check below re-proves — that
``/api/{path-steps,pathways}/context`` bind to ``.intelligence.get_with_context``
(inherited ``_CoreIntelligenceMixin``, mechanism B), a *different* function from the
deleted ``.core`` readers. So the deletion cannot change what those routes return.

This file pins that contract two ways:

* **Structural (no Neo4j)** — the route-serving reader IS the shared mechanism-B base,
  the bespoke ``.core`` overrides are gone, and the dead facade / backend methods +
  the ``PsStepWithContextRow`` TypedDict no longer resolve. A regression that re-adds a
  bespoke ``.core.get_with_context`` override or re-wires a route to ``.core`` fails here.
* **Live Neo4j** — the wired ``PsIntelligenceService.get_with_context`` returns the
  mechanism-B ``(entity, GraphContext)`` shape, surfaces a registry edge, and filters a
  non-registry edge (negative control).

CI runs no pytest — run on local Docker Neo4j.
See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend, PsBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.models.relationship_registry import PS_CONFIG
from core.ports import query_types
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.lp.lp_core_service import LpCoreService
from core.services.lp.lp_intelligence_service import LpIntelligenceService
from core.services.lp_service import LpService
from core.services.ps.ps_core_service import PsCoreService
from core.services.ps.ps_intelligence_service import PsIntelligenceService
from core.services.ps_service import PsService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

P = "ctxguard_"
PS = P + "ps"  # center PathStep
TASK = P + "task"  # (PS)-[:ASSIGNS_TASK]->(Task)   registry edge → must surface
NOISE = P + "noise"  # (PS)-[:NOISE_LINK]->(noise)     non-registry → must NOT surface


# ============================================================================
# Structural guard (no Neo4j) — route binds to mechanism B; dead readers gone
# ============================================================================


def test_context_route_reader_is_mechanism_b_not_bespoke_core():
    """The reader behind ``/api/{path-steps,pathways}/context`` is the shared base.

    ``domain_route_factory`` wires the context route with
    ``intelligence_service=primary_service.intelligence``, so the route calls
    ``.intelligence.get_with_context`` — which must be the inherited mechanism-B reader,
    NOT a bespoke override.
    """
    assert PsIntelligenceService.get_with_context is _CoreIntelligenceMixin.get_with_context
    assert LpIntelligenceService.get_with_context is _CoreIntelligenceMixin.get_with_context


def test_bespoke_core_get_with_context_overrides_deleted():
    """The PS/LP ``.core.get_with_context`` rich-context overrides are removed.

    With them gone, ``.core.get_with_context`` resolves to the generic BaseService mixin —
    not a PS/LP-specific override that ran hand-written curated Cypher.
    """
    assert "get_with_context" not in PsCoreService.__dict__
    assert "get_with_context" not in LpCoreService.__dict__


def test_dead_facade_and_backend_readers_gone():
    """Every bespoke reader method + its result TypedDict no longer resolves."""
    # Facade passthroughs.
    assert getattr(PsService, "get_step_with_context", None) is None
    assert getattr(LpService, "get_path_with_context", None) is None
    # Intelligence-layer user-scoped reader.
    assert getattr(LpIntelligenceService, "get_path_with_context", None) is None
    # Backend Cypher.
    assert getattr(PsBackend, "get_step_with_context", None) is None
    assert getattr(LpBackend, "get_path_with_graph_context", None) is None
    assert getattr(LpBackend, "get_path_with_context", None) is None
    # Orphan return-shape TypedDicts (PsStepWithKnowledgeRow deleted in Tier 6 —
    # get_step_with_knowledge now returns typed PathStep models).
    assert getattr(query_types, "PsStepWithContextRow", None) is None
    assert getattr(query_types, "PsStepWithKnowledgeRow", None) is None


# ============================================================================
# Live Neo4j — the wired PS context reader returns mechanism-B output
# ============================================================================


@pytest.fixture
def ps_intel(neo4j_driver):
    """PsIntelligenceService wired exactly like production (mechanism B)."""
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend, config=PS_CONFIG, graph_intel=graph_intel
    )
    return PsIntelligenceService(
        backend=backend, graph_intel=graph_intel, relationship_service=relationships
    )


@pytest.mark.asyncio
async def test_path_step_context_route_serves_mechanism_b(neo4j_driver, ps_intel, clean_neo4j):
    """The reader bound to ``/api/path-steps/context`` returns mechanism-B output.

    Registry edge (ASSIGNS_TASK) surfaces; a non-registry edge (NOISE_LINK) does not.
    Proves the route is unaffected by deleting the bespoke ``.core`` reader.
    """
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:PathStep {uid:$u, entity_type:'path_step', title:$u, "
            "status:'active', created_at:datetime()})",
            u=PS,
        )
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=TASK,
        )
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=NOISE,
        )
        await s.run("MATCH (p{uid:$p}),(t{uid:$t}) CREATE (p)-[:ASSIGNS_TASK]->(t)", p=PS, t=TASK)
        await s.run("MATCH (p{uid:$p}),(n{uid:$n}) CREATE (p)-[:NOISE_LINK]->(n)", p=PS, n=NOISE)

    assert "ASSIGNS_TASK" in PS_CONFIG.cross_domain_relationship_types
    assert "NOISE_LINK" not in PS_CONFIG.cross_domain_relationship_types

    res = await ps_intel.get_with_context(PS, depth=1)
    assert res.is_ok, res

    # Mechanism-B shape: (entity, GraphContext), NOT a single PathStep with a bespoke
    # metadata["graph_context"] dict.
    entity, ctx = res.value
    assert entity.uid == PS
    assert "graph_context" not in (getattr(entity, "metadata", {}) or {}), (
        "mechanism B returns the GraphContext alongside the entity, "
        "not a bespoke metadata['graph_context'] payload"
    )

    uids = {n.uid for n in ctx.all_nodes}
    assert TASK in uids, "registry edge (ASSIGNS_TASK) must surface through mechanism B"
    assert NOISE not in uids, "non-registry edge (NOISE_LINK) must be filtered (negative control)"
    assert PS not in uids, "origin must not leak into its own context"
