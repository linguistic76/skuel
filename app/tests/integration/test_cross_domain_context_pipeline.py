"""Real-Neo4j round-trip for the cross-domain-context analytics pipeline.

End-to-end guard for the two-layer fix in the goals/habits/principles dashboards:

1. ``_analyze_entity_with_context`` now calls the generic, config-driven
   ``UnifiedRelationshipService.get_cross_domain_context`` directly (was a
   getattr-by-name on a per-domain method that resolved to ``None``).
2. ``*CrossContext.from_dict`` now reads the config ``context_field_name`` buckets
   the response actually carries (was reading generic keys that never appeared, so
   the typed context — and every dashboard metric — came back empty).

These tests seed a real graph, run the same ``get_cross_domain_context`` →
``from_dict`` → ``calculate_*_metrics`` path the dashboards use, and assert the
seeded relationships surface. The negative control (an entity with no edges)
proves the result reflects the graph rather than a hard-coded value — and would
have *passed even while the pipeline was fully broken*, which is exactly why the
positive assertions are the ones that lock in the fix.

Mocked unit tests cannot catch this (the key mismatch is a silent empty list); the
guard must run against real Cypher.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.goal.goal_dto import GoalDTO
from core.models.relationship_registry import (
    GOAPS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
)
from core.services.intelligence.cross_domain_contexts import (
    GoalCrossContext,
    HabitCrossContext,
    PrincipleCrossContext,
)
from core.services.intelligence.metrics_calculators import calculate_goal_metrics
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

P = "xdctx_"  # uid prefix for this module's fixture graph
GOAL = P + "goal"
GOAL_BARE = P + "goal_bare"  # negative control: no cross-domain edges
HABIT = P + "habit"
KU = P + "ku"
PRINCIPLE = P + "principle"


@pytest.fixture
def rel_backend(neo4j_driver):
    """Generic Entity backend — the same shape injected as a domain's relationships backend."""
    return UniversalNeo4jBackend[GoalDTO](neo4j_driver, "Entity", GoalDTO)


@pytest.mark.asyncio
async def test_cross_domain_context_pipeline_round_trip(neo4j_driver, rel_backend, clean_neo4j):
    """The seeded cross-domain edges surface through from_dict and into the metrics."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (GOAL, "Goal", "goal"),
            (GOAL_BARE, "Goal", "goal"),
            (HABIT, "Habit", "habit"),
            (PRINCIPLE, "Principle", "principle"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run("CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=KU)
        # Clean depth-1 edges (no cycles → no depth-2 over-inclusion).
        await s.run(
            "MATCH (h{uid:$h}),(g{uid:$g}) CREATE (h)-[:SUPPORTS_GOAL {confidence:0.95}]->(g)",
            h=HABIT,
            g=GOAL,
        )
        await s.run(
            "MATCH (g{uid:$g}),(k{uid:$k}) CREATE (g)-[:REQUIRES_KNOWLEDGE {confidence:0.95}]->(k)",
            g=GOAL,
            k=KU,
        )
        await s.run(
            "MATCH (p{uid:$p}),(g{uid:$g}) CREATE (p)-[:GUIDES_GOAL {confidence:0.95}]->(g)",
            p=PRINCIPLE,
            g=GOAL,
        )
        await s.run(
            "MATCH (h{uid:$h}),(p{uid:$p}) CREATE (h)-[:EMBODIES_PRINCIPLE {confidence:0.95}]->(p)",
            h=HABIT,
            p=PRINCIPLE,
        )
        await s.run(
            "MATCH (h{uid:$h}),(k{uid:$k}) CREATE (h)-[:REINFORCES_KNOWLEDGE {confidence:0.95}]->(k)",
            h=HABIT,
            k=KU,
        )

    goal_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=GOAPS_CONFIG, graph_intel=None
    )
    habit_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    prin_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=PRINCIPLES_CONFIG, graph_intel=None
    )

    # --- Goal: habit supports it, it requires a KU, a principle guides it ---
    goal_res = await goal_rel.get_cross_domain_context(GOAL, depth=1, min_confidence=0.7)
    assert goal_res.is_ok, goal_res
    goal_ctx = GoalCrossContext.from_dict(goal_res.value)
    assert HABIT in goal_ctx.supporting_habit_uids
    assert KU in goal_ctx.required_knowledge_uids
    assert PRINCIPLE in goal_ctx.guiding_principle_uids

    # The metrics layer the dashboard consumes reflects the graph (was all zeros pre-fix).
    metrics = calculate_goal_metrics(None, goal_ctx)
    assert metrics["habit_support_count"] == 1
    assert metrics["knowledge_requirement_count"] == 1
    assert metrics["has_habit_system"] is True

    # --- Habit: supports a goal, reinforces a KU, embodies a principle ---
    habit_res = await habit_rel.get_cross_domain_context(HABIT, depth=1, min_confidence=0.7)
    assert habit_res.is_ok, habit_res
    habit_ctx = HabitCrossContext.from_dict(habit_res.value)
    assert GOAL in habit_ctx.linked_goal_uids
    assert KU in habit_ctx.knowledge_reinforcement_uids
    assert PRINCIPLE in habit_ctx.aligned_principle_uids

    # --- Principle: guides a goal, is embodied by a habit ---
    prin_res = await prin_rel.get_cross_domain_context(PRINCIPLE, depth=1, min_confidence=0.7)
    assert prin_res.is_ok, prin_res
    prin_ctx = PrincipleCrossContext.from_dict(prin_res.value)
    assert GOAL in prin_ctx.guided_goal_uids
    assert HABIT in prin_ctx.aligned_habit_uids


@pytest.mark.asyncio
async def test_cross_domain_context_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an entity with no cross-domain edges yields an empty context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
            "status:'active', created_at:datetime()})",
            u=GOAL_BARE,
        )

    goal_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=GOAPS_CONFIG, graph_intel=None
    )
    res = await goal_rel.get_cross_domain_context(GOAL_BARE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = GoalCrossContext.from_dict(res.value)
    assert ctx.supporting_habit_uids == []
    assert ctx.required_knowledge_uids == []
    assert ctx.guiding_principle_uids == []
    assert calculate_goal_metrics(None, ctx)["habit_support_count"] == 0
