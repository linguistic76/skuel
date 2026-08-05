"""Real-Neo4j guard for Convergence Phase 2: direction-aware bucketing.

The intent-traversal reader (``query_with_intent`` → ``GraphContext``) now runs the SAME
incident-edge-attributed producer (``build_domain_context_with_paths``) as the bucketed
cross-domain-context reader, instead of a parallel flat Cypher query. This test pins the
NET-NEW behaviour that the fold adds and the retired flat builder never had:

* **2-hop incident attribution** — a node two hops out is attributed by the edge INCIDENT
  to it (its last hop), not the first hop that merely left the origin, and carries its real
  ``distance_from_origin`` (the flat builder defaulted every node to distance 1).
* **Strongest-path de-dup** — a node reachable by several paths appears ONCE in
  ``all_nodes``, keeping the strongest entry (fewest hops, then highest path strength).
* **Node properties carried** — ``node.properties`` holds the real DB property map (e.g.
  ``status``), the contract the ``get_entity_context`` consumers
  (``intelligence_queries`` / ``activity_knowledge_intelligence_service``) depend on.
* **Negative control** — an edge outside the registry vocabulary never surfaces.

Cross-domain breadth (all 9 domains through the folded path) is covered by
``test_intent_traversal_registry_source`` + the ``test_convergence_*`` suite; this file
focuses on the bucketing mechanics. Runs in CI (``integration_tests``) and locally via ``./dev test-integration``.
See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.graph_context import GraphContext, GraphNode
from core.models.relationship_registry import TASKS_CONFIG
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

P = "dab_"  # uid prefix for this module's fixture graph

TASK = P + "task"  # center
DEP = P + "dep"  # task -[:DEPENDS_ON]-> dep            (registry, 1 hop)
KU = P + "ku"  # task -[:APPLIES_KNOWLEDGE]-> ku        (registry, 1 hop)
GOAL = P + "goal"  # reachable BOTH directly AND via dep (de-dup target)
GOAL2 = P + "goal2"  # dep -[:CONTRIBUTES_TO_GOAL]-> goal2 (registry, 2 hops, incident attr.)
NOISE = P + "noise"  # task -[:NOISE_LINK]-> noise          (non-registry → must NOT surface)


def _node(gc: GraphContext, uid: str) -> GraphNode:
    node = next((n for n in gc.all_nodes if n.uid == uid), None)
    assert node is not None, f"{uid} expected in context"
    return node


def _uids(gc: GraphContext) -> list[str]:
    return [n.uid for n in gc.all_nodes]


@pytest.fixture
def graph_intel(neo4j_driver):
    """A real GraphIntelligenceService over a real CrossDomainBackend (the engine path)."""
    backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))
    return GraphIntelligenceService(backend)


@pytest.mark.asyncio
async def test_direction_aware_bucketing_2hop_dedup_and_properties(
    neo4j_driver, graph_intel, clean_neo4j
):
    """2-hop incident attribution + strongest-path de-dup + properties + negative control."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (TASK, "Task", "task"),
            (DEP, "Task", "task"),
            (GOAL, "Goal", "goal"),
            (GOAL2, "Goal", "goal"),
            (NOISE, "Task", "task"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=KU
        )
        # 1-hop registry edges off the center.
        await s.run("MATCH (t{uid:$t}),(d{uid:$d}) CREATE (t)-[:DEPENDS_ON]->(d)", t=TASK, d=DEP)
        await s.run(
            "MATCH (t{uid:$t}),(k{uid:$k}) CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)", t=TASK, k=KU
        )
        # GOAL reachable BOTH directly (1 hop) AND via DEP (2 hops) — the de-dup target.
        await s.run(
            "MATCH (t{uid:$t}),(g{uid:$g}) CREATE (t)-[:CONTRIBUTES_TO_GOAL]->(g)", t=TASK, g=GOAL
        )
        await s.run(
            "MATCH (d{uid:$d}),(g{uid:$g}) CREATE (d)-[:CONTRIBUTES_TO_GOAL]->(g)", d=DEP, g=GOAL
        )
        # GOAL2 reachable ONLY at 2 hops, via DEP — incident edge is CONTRIBUTES_TO_GOAL,
        # NOT the first hop DEPENDS_ON.
        await s.run(
            "MATCH (d{uid:$d}),(g{uid:$g}) CREATE (d)-[:CONTRIBUTES_TO_GOAL]->(g)", d=DEP, g=GOAL2
        )
        # Noise edge outside the registry vocabulary.
        await s.run("MATCH (t{uid:$t}),(n{uid:$n}) CREATE (t)-[:NOISE_LINK]->(n)", t=TASK, n=NOISE)

    for edge in ("DEPENDS_ON", "CONTRIBUTES_TO_GOAL", "APPLIES_KNOWLEDGE"):
        assert edge in TASKS_CONFIG.cross_domain_relationship_types

    res = await graph_intel.query_with_intent(
        domain=None,
        node_uid=TASK,
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert res.is_ok, res
    gc = res.value
    uids = _uids(gc)

    # --- All registry neighbours surface; noise + self do not ---
    assert DEP in uids and KU in uids and GOAL in uids and GOAL2 in uids
    assert NOISE not in uids, "non-registry edge must be filtered out (negative control)"
    assert TASK not in uids, "origin must not leak into its own context"

    # --- Strongest-path de-dup: GOAL reached by 1-hop AND 2-hop paths appears ONCE,
    # keeping the closest (distance 1) ---
    assert uids.count(GOAL) == 1, "a multi-path node must be de-duped to a single entry"
    assert _node(gc, GOAL).distance_from_origin == 1, (
        "de-dup must keep the strongest (closest) path"
    )

    # --- 2-hop incident attribution: GOAL2 is attributed by its LAST hop
    # (CONTRIBUTES_TO_GOAL), not the first hop (DEPENDS_ON), and carries distance 2 ---
    goal2 = _node(gc, GOAL2)
    assert goal2.distance_from_origin == 2, "a 2-hop node must carry its real distance"
    assert goal2.relationship_to_origin == "CONTRIBUTES_TO_GOAL", (
        "node must be attributed by the edge INCIDENT to it (last hop), not the first hop"
    )

    # --- Node properties carried (the get_entity_context consumer contract) ---
    assert _node(gc, GOAL).properties.get("status") == "active", (
        "node.properties must carry the real DB property map, not just the title"
    )


@pytest.mark.asyncio
async def test_edge_less_node_yields_empty_not_notfound(neo4j_driver, graph_intel, clean_neo4j):
    """A present node with no matching edges → empty context, not a NOT_FOUND error.

    Regression guard: the shared producer keeps the center row when the OPTIONAL MATCH finds
    nothing, so an unconnected-but-present node still produces a record. Zero records is
    reserved for a genuinely absent node (which ``query_with_intent`` reports as NOT_FOUND).
    """
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=P + "lonely",
        )

    res = await graph_intel.query_with_intent(
        domain=None,
        node_uid=P + "lonely",
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert res.is_ok, "present-but-unconnected node must return an (empty) context, not NOT_FOUND"
    assert res.value.all_nodes == [], "an edge-less node's context must be empty"

    # A genuinely absent node is still NOT_FOUND.
    missing = await graph_intel.query_with_intent(
        domain=None,
        node_uid=P + "does_not_exist",
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert missing.is_error, "an absent node must report NOT_FOUND"
