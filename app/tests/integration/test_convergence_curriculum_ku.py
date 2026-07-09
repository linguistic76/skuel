"""Real-Neo4j guard for the curriculum convergence: Ku onto mechanism B.

The curriculum-convergence teardown collapsed the per-domain ``get_with_context``
overrides into the shared ``_CoreIntelligenceMixin`` and deleted the old model-suggested
loader (mechanism A). Curriculum intelligence services (Ku/Ps/Lp) inherited mechanism A
via that shared base; they now inherit **mechanism B** —
``UnifiedRelationshipService.get_with_context``, registry-sourced from
``KU_CONFIG.cross_domain_relationship_types``.

Ku's ``default_context_intent`` is EXPLORATORY, whose hard-coded clause is the generic
"traverse every edge type" branch. So for Ku the convergence *narrows* the context to
the registry vocabulary (``USES_KU`` / ``TRAINS_KU`` / ``CITES_RESOURCE``) instead of
returning every neighbour. Two things must hold:

1. **Wiring.** ``create_lp_sub_services`` / Ku factory pass a live
   ``relationship_service``; without it the inherited base returns an error (not a
   crash). The shared base, not a per-domain override, owns the implementation.
2. **Registry-sourced traversal (live Neo4j).** A Ku's registry edges
   (``USES_KU`` / ``TRAINS_KU``) surface through ``get_with_context``; an edge outside
   the registry (and ``ORGANIZES``, which is intentionally NOT in ``KU_CONFIG`` — Ku
   hierarchy is served by ``get_organization_depth`` / ``is_organized``) is filtered
   out. The negative control proves the bare EXPLORATORY clause does NOT filter, so the
   registry set is what excludes the non-registry edges.

See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.ku.ku import Ku
from core.models.relationship_registry import KU_CONFIG
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.ku.ku_intelligence_service import KuIntelligenceService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

P = "convku_"  # uid prefix for this module's fixture graph
KU = P + "ku"
KU_USES = P + "ku_uses"  # via USES_KU (registry edge)
KU_TRAINS = P + "ku_trains"  # via TRAINS_KU (registry edge)
KU_ORG = P + "ku_org"  # via ORGANIZES (NOT in KU_CONFIG → filtered by mechanism B)
KU_NOISE = P + "ku_noise"  # via NOISE_LINK (outside the registry → filtered)


def _uids(graph_context) -> set[str]:
    return {node.uid for node in graph_context.all_nodes}


# ============================================================================
# Delegation / wiring guard (no Neo4j)
# ============================================================================


@pytest.mark.asyncio
async def test_ku_get_with_context_delegates_to_mechanism_b():
    """Ku inherits the shared base, which routes to self.relationships (mechanism B)."""
    svc = KuIntelligenceService.__new__(KuIntelligenceService)
    svc.graph_intel = MagicMock()  # truthy → @requires_graph_intelligence does not short-circuit
    svc.logger = MagicMock()
    rel = MagicMock()
    rel.get_with_context = AsyncMock(return_value="MECHANISM_B")
    svc.relationships = rel

    assert await svc.get_with_context("ku_x", 3) == "MECHANISM_B"
    rel.get_with_context.assert_awaited_once_with("ku_x", 3)


@pytest.mark.asyncio
async def test_ku_get_with_context_errors_without_relationship_service():
    svc = KuIntelligenceService.__new__(KuIntelligenceService)
    svc.graph_intel = MagicMock()
    svc.logger = MagicMock()
    svc.relationships = None

    res = await svc.get_with_context("ku_x")
    assert res.is_error, "missing relationship_service must be an error, not a crash"


# ============================================================================
# Registry-sourced traversal through mechanism B (live Neo4j)
# ============================================================================


@pytest.fixture
def ku_intel(neo4j_driver):
    """Ku intelligence service wired to a real graph_intel — mechanism B.

    Mirrors the production Ku wiring (``create_curriculum_sub_services``): a live
    ``UnifiedRelationshipService(config=KU_CONFIG)`` passed as ``relationship_service``.
    """
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    relationships: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=backend, config=KU_CONFIG, graph_intel=graph_intel
    )
    return KuIntelligenceService(
        backend=backend, graph_intel=graph_intel, relationship_service=relationships
    )


@pytest.mark.asyncio
async def test_ku_registry_sourced_through_get_with_context(neo4j_driver, ku_intel, clean_neo4j):
    """A Ku's registry edges (USES_KU/TRAINS_KU here) surface; ORGANIZES + noise filtered."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (KU, "Ku", "ku"),
            (KU_USES, "PathStep", "path_step"),
            (KU_TRAINS, "PathStep", "path_step"),
            (KU_ORG, "Ku", "ku"),
            (KU_NOISE, "Ku", "ku"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        # (PathStep)-[:USES_KU|TRAINS_KU]->(Ku); (Ku)-[:ORGANIZES]->(child Ku).
        await s.run("MATCH (p{uid:$p}),(k{uid:$k}) CREATE (p)-[:USES_KU]->(k)", p=KU_USES, k=KU)
        await s.run("MATCH (p{uid:$p}),(k{uid:$k}) CREATE (p)-[:TRAINS_KU]->(k)", p=KU_TRAINS, k=KU)
        await s.run("MATCH (k{uid:$k}),(c{uid:$c}) CREATE (k)-[:ORGANIZES]->(c)", k=KU, c=KU_ORG)
        await s.run("MATCH (k{uid:$k}),(n{uid:$n}) CREATE (k)-[:NOISE_LINK]->(n)", k=KU, n=KU_NOISE)

    # USES_KU/TRAINS_KU/CITES_RESOURCE are the registry vocabulary (CITES_RESOURCE
    # since the Resources arc — Ku-authored ``resource_uids:``); ORGANIZES is
    # intentionally absent.
    assert set(KU_CONFIG.cross_domain_relationship_types) == {
        "USES_KU",
        "TRAINS_KU",
        "CITES_RESOURCE",
    }
    assert KU_CONFIG.default_context_intent.value == "exploratory"

    res = await ku_intel.get_with_context(KU, depth=1)
    assert res.is_ok, res
    ku, ctx = res.value
    # Focal entity stays a full Ku domain model (KU_CONFIG.model_class is Ku).
    assert isinstance(ku, Ku), f"mechanism B must preserve the Ku model, got {type(ku).__name__}"

    uids = _uids(ctx)
    assert KU_USES in uids, "USES_KU neighbour should surface registry-sourced"
    assert KU_TRAINS in uids, "TRAINS_KU neighbour should surface registry-sourced"
    assert KU_ORG not in uids, "ORGANIZES is not in KU_CONFIG → must be filtered by mechanism B"
    assert KU_NOISE not in uids, "edge outside the registry must be filtered out"
    assert KU not in uids, "origin must not leak into its own context"

    # Negative control: the bare EXPLORATORY clause is the generic "traverse everything"
    # branch — it does NOT filter, so ORGANIZES + noise both surface. This proves the
    # registry set (not the intent clause) is what excludes them under mechanism B.
    bare = await ku_intel.relationships.graph_intel.query_with_intent(
        domain=None, node_uid=KU, intent=KU_CONFIG.default_context_intent, depth=1
    )
    assert bare.is_ok, bare
    bare_uids = _uids(bare.value)
    assert KU_ORG in bare_uids, "bare EXPLORATORY should surface ORGANIZES (no edge filter)"
    assert KU_NOISE in bare_uids, "bare EXPLORATORY should surface noise (no edge filter)"
