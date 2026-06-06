"""Real-Neo4j guard for Convergence: registry-sourced intent traversal.

The intent-traversal engine (``query_with_intent`` over the shared
``build_domain_context_with_paths`` producer) sources its edge vocabulary from the registry
(``DomainRelationshipConfig.cross_domain_relationship_types``, the single source of truth)
when ``relationship_types`` is supplied, rather than a narrow per-intent slice that drifts.

Each test seeds a real graph and runs ``GraphIntelligenceService.query_with_intent`` twice:

* **registry-sourced** (``relationship_types=<config>.cross_domain_relationship_types``):
  the domain's real cross-domain neighbours surface, and a noise edge outside the registry
  is excluded.
* **negative control** (``relationship_types=None`` → the intent's narrow edge slice from
  ``_INTENT_EDGE_SETS``): a neighbour reachable only via a registry edge that the intent
  slice omits is *missed* — proving the registry source genuinely changes behaviour, not a
  no-op.

Mocked unit tests cannot catch this (the filter lives in Cypher); the guard must run against
real Neo4j. See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.relationship_registry import EVENTS_CONFIG, TASKS_CONFIG
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService

P = "intsrc_"  # uid prefix for this module's fixture graph

# --- Tasks fixture graph ---
TASK = P + "task"
TASK_DEP = P + "task_dep"  # via DEPENDS_ON (registry edge, NOT in the PREREQUISITE clause)
GOAL = P + "goal"  # via CONTRIBUTES_TO_GOAL (registry edge)
KU = P + "ku"  # via APPLIES_KNOWLEDGE (registry edge)
NOISE = P + "noise"  # via NOISE_LINK (NOT in any config → must be filtered out)

# --- Events fixture graph ---
EVENT = P + "event"
EVT_GOAL = P + "evt_goal"  # via CONTRIBUTES_TO_GOAL (registry edge, NOT in PRACTICE clause)
EVT_HABIT = P + "evt_habit"  # via REINFORCES_HABIT (registry edge, NOT in PRACTICE clause)

# --- depth-2 fixture graph (registry-sourced ALL-edges guarantee) ---
D2_TASK = P + "d2_task"
D2_DEP = P + "d2_dep"  # task -[:DEPENDS_ON]-> dep   (all-registry 1-hop)
D2_GOAL = P + "d2_goal"  # dep  -[:CONTRIBUTES_TO_GOAL]-> goal (all-registry 2-hop, must surface)
D2_NOISE = P + "d2_noise"  # dep  -[:NOISE_LINK]-> noise  (non-registry tail, must NOT surface)


def _uids(graph_context) -> set[str]:
    return {node.uid for node in graph_context.all_nodes}


@pytest.fixture
def graph_intel(neo4j_driver):
    """A real GraphIntelligenceService over a real CrossDomainBackend (the engine path)."""
    backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))
    return GraphIntelligenceService(backend)


@pytest.mark.asyncio
async def test_tasks_registry_sourced_traversal(neo4j_driver, graph_intel, clean_neo4j):
    """A task's registry edges surface (and noise is filtered); the bare clause misses them."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (TASK, "Task", "task"),
            (TASK_DEP, "Task", "task"),
            (GOAL, "Goal", "goal"),
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
        await s.run(
            "MATCH (t{uid:$t}),(d{uid:$d}) CREATE (t)-[:DEPENDS_ON]->(d)", t=TASK, d=TASK_DEP
        )
        await s.run(
            "MATCH (t{uid:$t}),(g{uid:$g}) CREATE (t)-[:CONTRIBUTES_TO_GOAL]->(g)", t=TASK, g=GOAL
        )
        await s.run(
            "MATCH (t{uid:$t}),(k{uid:$k}) CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)", t=TASK, k=KU
        )
        # Noise edge OUTSIDE the registry vocabulary — must never surface registry-sourced.
        await s.run("MATCH (t{uid:$t}),(n{uid:$n}) CREATE (t)-[:NOISE_LINK]->(n)", t=TASK, n=NOISE)

    # DEPENDS_ON is a registry edge but NOT in the hard-coded PREREQUISITE clause — the
    # clean discriminator between the two paths.
    assert "DEPENDS_ON" in TASKS_CONFIG.cross_domain_relationship_types
    assert TASKS_CONFIG.default_context_intent.value == "prerequisite"

    # --- Registry-sourced (mechanism B): real edges in, noise out ---
    reg = await graph_intel.query_with_intent(
        domain=None,
        node_uid=TASK,
        intent=TASKS_CONFIG.default_context_intent,
        depth=1,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert reg.is_ok, reg
    reg_uids = _uids(reg.value)
    assert TASK_DEP in reg_uids, "DEPENDS_ON neighbour should surface registry-sourced"
    assert GOAL in reg_uids, "CONTRIBUTES_TO_GOAL neighbour should surface registry-sourced"
    assert KU in reg_uids, "APPLIES_KNOWLEDGE neighbour should surface registry-sourced"
    assert NOISE not in reg_uids, "edge outside the registry must be filtered out"
    assert TASK not in reg_uids, "origin must not leak into its own context (self-exclusion)"
    # All three registry edges are counted — not just the first matched path's (the rels
    # are flattened across every matched path, deduped). NOISE_LINK is excluded.
    assert reg.value.total_relationships == 3, (
        "every matched registry edge must be counted, not only the first path's"
    )

    # --- Negative control: bare default-intent clause misses the DEPENDS_ON neighbour ---
    bare = await graph_intel.query_with_intent(
        domain=None,
        node_uid=TASK,
        intent=TASKS_CONFIG.default_context_intent,
        depth=1,
    )
    assert bare.is_ok, bare
    assert TASK_DEP not in _uids(bare.value), (
        "DEPENDS_ON is absent from the hard-coded PREREQUISITE clause — the bare path must "
        "miss it, which is exactly what registry-sourcing fixes"
    )


@pytest.mark.asyncio
async def test_events_registry_sourced_traversal(neo4j_driver, graph_intel, clean_neo4j):
    """An event's registry edges surface; the bare PRACTICE clause misses goal/habit links."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (EVENT, "Event", "event"),
            (EVT_GOAL, "Goal", "goal"),
            (EVT_HABIT, "Habit", "habit"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (e{uid:$e}),(g{uid:$g}) CREATE (e)-[:CONTRIBUTES_TO_GOAL]->(g)",
            e=EVENT,
            g=EVT_GOAL,
        )
        await s.run(
            "MATCH (e{uid:$e}),(h{uid:$h}) CREATE (e)-[:REINFORCES_HABIT]->(h)",
            e=EVENT,
            h=EVT_HABIT,
        )

    # CONTRIBUTES_TO_GOAL / REINFORCES_HABIT are registry edges absent from the PRACTICE clause.
    assert "CONTRIBUTES_TO_GOAL" in EVENTS_CONFIG.cross_domain_relationship_types
    assert "REINFORCES_HABIT" in EVENTS_CONFIG.cross_domain_relationship_types
    assert EVENTS_CONFIG.default_context_intent.value == "practice"

    # --- Registry-sourced (mechanism B): real edges surface ---
    reg = await graph_intel.query_with_intent(
        domain=None,
        node_uid=EVENT,
        intent=EVENTS_CONFIG.default_context_intent,
        depth=1,
        relationship_types=EVENTS_CONFIG.cross_domain_relationship_types,
    )
    assert reg.is_ok, reg
    reg_uids = _uids(reg.value)
    assert EVT_GOAL in reg_uids, "CONTRIBUTES_TO_GOAL neighbour should surface registry-sourced"
    assert EVT_HABIT in reg_uids, "REINFORCES_HABIT neighbour should surface registry-sourced"

    # --- Negative control: bare PRACTICE clause misses the goal link ---
    bare = await graph_intel.query_with_intent(
        domain=None,
        node_uid=EVENT,
        intent=EVENTS_CONFIG.default_context_intent,
        depth=1,
    )
    assert bare.is_ok, bare
    assert EVT_GOAL not in _uids(bare.value), (
        "CONTRIBUTES_TO_GOAL is absent from the hard-coded PRACTICE clause — the bare path "
        "must miss it"
    )


@pytest.mark.asyncio
async def test_registry_sourced_excludes_non_registry_tail_at_depth_2(
    neo4j_driver, graph_intel, clean_neo4j
):
    """At depth>1 a non-registry tail edge must NOT leak its node (the `all` guarantee).

    Path shapes from D2_TASK at depth 2:
      D2_TASK -[:DEPENDS_ON]->        D2_DEP                (all registry → D2_DEP surfaces)
      D2_TASK -[:DEPENDS_ON]->D2_DEP -[:CONTRIBUTES_TO_GOAL]-> D2_GOAL (all registry → surfaces)
      D2_TASK -[:DEPENDS_ON]->D2_DEP -[:NOISE_LINK]->        D2_NOISE  (mixed → must NOT surface)

    An `any`-based predicate would wrongly collect D2_NOISE here (the path contains the
    registry DEPENDS_ON edge); `all` rejects the mixed path. This is the regression Codex
    flagged — the original tests only covered depth 1.
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (D2_TASK, "Task", "task"),
            (D2_DEP, "Task", "task"),
            (D2_GOAL, "Goal", "goal"),
            (D2_NOISE, "Task", "task"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (t{uid:$t}),(d{uid:$d}) CREATE (t)-[:DEPENDS_ON]->(d)", t=D2_TASK, d=D2_DEP
        )
        await s.run(
            "MATCH (d{uid:$d}),(g{uid:$g}) CREATE (d)-[:CONTRIBUTES_TO_GOAL]->(g)",
            d=D2_DEP,
            g=D2_GOAL,
        )
        await s.run(
            "MATCH (d{uid:$d}),(n{uid:$n}) CREATE (d)-[:NOISE_LINK]->(n)", d=D2_DEP, n=D2_NOISE
        )

    res = await graph_intel.query_with_intent(
        domain=None,
        node_uid=D2_TASK,
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert res.is_ok, res
    uids = _uids(res.value)
    assert D2_DEP in uids, "1-hop all-registry neighbour should surface"
    assert D2_GOAL in uids, "2-hop all-registry transitive neighbour should surface"
    assert D2_NOISE not in uids, (
        "node reachable only via a non-registry tail edge must NOT surface at depth 2 "
        "(the `all` guarantee — `any` would have leaked it)"
    )
    assert D2_TASK not in uids, "origin must not leak into its own context (self-exclusion)"


@pytest.mark.asyncio
async def test_registry_sourced_no_edges_yields_empty_context(
    neo4j_driver, graph_intel, clean_neo4j
):
    """An entity with no registry edges yields an is_ok EMPTY context, not a not-found.

    The `LIMIT` cap is applied before the `collect` aggregation; the
    `OPTIONAL MATCH ... WHERE related <> origin` predicate must still keep the origin row
    alive (related = null) so the aggregation emits one record with empty nodes rather
    than zero records (which `query_with_intent` would turn into a not-found error).
    """
    bare = P + "isolated_task"
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=bare,
        )

    res = await graph_intel.query_with_intent(
        domain=None,
        node_uid=bare,
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert res.is_ok, res
    assert res.value.total_nodes == 0, "isolated entity should yield an empty context"
