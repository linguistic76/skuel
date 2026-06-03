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
from neo4j import AsyncSession

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.goal.goal_dto import GoalDTO
from core.models.relationship_registry import (
    CHOICES_CONFIG,
    GOAPS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
)
from core.services.intelligence.cross_domain_contexts import (
    ChoiceCrossContext,
    GoalCrossContext,
    HabitCrossContext,
    PrincipleCrossContext,
)
from core.services.intelligence.metrics_calculators import (
    calculate_choice_metrics,
    calculate_goal_metrics,
)
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
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=KU
        )
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


# uid prefix for the depth-2 / direction-aware regression graph (the canonical
# INSPIRES_HABIT <-> EMBODIES_PRINCIPLE reciprocal pair — the natural 2-cycle).
R = "xdctx_recip_"
R_PRINCIPLE = R + "principle"
R_HABIT = R + "habit"
R_GOAL = R + "goal"


async def _seed_reciprocal_pair(session: AsyncSession) -> None:
    """principle <-> habit reciprocal pair, each also tied to one goal.

    Edges:
        principle -[INSPIRES_HABIT]->  habit       (principle's outgoing / habit's incoming)
        habit     -[EMBODIES_PRINCIPLE]-> principle (habit's outgoing / principle's incoming)
        principle -[GUIDES_GOAL]->      goal
        habit     -[SUPPORTS_GOAL]->     goal
    The two cross-domain edges between principle and habit form a 2-cycle, so a
    depth-2 traversal revisits the source — the exact shape that used to leak the
    source into its own sibling bucket.
    """
    for uid, label, etype in [
        (R_PRINCIPLE, "Principle", "principle"),
        (R_HABIT, "Habit", "habit"),
        (R_GOAL, "Goal", "goal"),
    ]:
        await session.run(
            f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
            f"status:'active', created_at:datetime()}})",
            u=uid,
            t=etype,
        )
    for a, rel, b in [
        (R_PRINCIPLE, "INSPIRES_HABIT", R_HABIT),
        (R_HABIT, "EMBODIES_PRINCIPLE", R_PRINCIPLE),
        (R_PRINCIPLE, "GUIDES_GOAL", R_GOAL),
        (R_HABIT, "SUPPORTS_GOAL", R_GOAL),
    ]:
        await session.run(
            f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
            a=a,
            b=b,
        )


@pytest.mark.asyncio
async def test_depth2_does_not_self_include_on_reciprocal_cycle(
    neo4j_driver, rel_backend, clean_neo4j
):
    """At depth=2 (the dashboard default) the source must not land in its own buckets.

    Pre-fix, ``get_cross_domain_context`` matched any path edge (not just the edge
    incident to the related node) and never excluded ``related == center``, so the
    canonical principle<->habit 2-cycle put the principle's own uid into
    ``aligned_habit_uids`` (and a :Principle node into a habit bucket, since the
    mapping's ``target_label="Entity"`` matches every node). Verified live before the
    fix; this locks the regression. depth=2 is essential — depth=1 never reproduced it.
    """
    async with neo4j_driver.session() as s:
        await _seed_reciprocal_pair(s)

    prin_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=PRINCIPLES_CONFIG, graph_intel=None
    )
    # depth=2 is the production default for the principles dashboard.
    res = await prin_rel.get_cross_domain_context(R_PRINCIPLE, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    ctx = PrincipleCrossContext.from_dict(res.value)

    # The principle's direct, distance-1 alignment is the habit — and ONLY the habit.
    assert R_HABIT in ctx.aligned_habit_uids
    assert R_PRINCIPLE not in ctx.aligned_habit_uids, "source leaked into its own bucket"
    assert ctx.aligned_habit_uids == [R_HABIT], f"over-inclusion: {ctx.aligned_habit_uids}"
    assert R_GOAL in ctx.guided_goal_uids


@pytest.mark.asyncio
async def test_habit_incoming_buckets_populate(neo4j_driver, rel_backend, clean_neo4j):
    """Habit INCOMING cross-domain buckets must populate (Step 2 of the fix).

    ``HABITS_CONFIG.bidirectional_relationships`` is empty, which formerly made
    ``get_cross_domain_context`` traverse outgoing edges only — so every incoming
    habit bucket (here ``inspiring_principles`` via the incoming INSPIRES_HABIT edge
    ``principle -> habit``) was structurally always empty. The traversal now always
    fetches both directions and categorizes per-mapping ``direction``, so the bucket
    fills and ``aligned_principle_uids`` spans both EMBODIES_PRINCIPLE (outgoing) and
    INSPIRES_HABIT (incoming), mirroring the principle side.
    """
    async with neo4j_driver.session() as s:
        await _seed_reciprocal_pair(s)

    habit_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    res = await habit_rel.get_cross_domain_context(R_HABIT, depth=2, min_confidence=0.7)
    assert res.is_ok, res

    # The incoming-only bucket now carries the principle that inspires this habit.
    inspiring = [e["uid"] for e in res.value.get("inspiring_principles") or []]
    assert R_PRINCIPLE in inspiring, f"incoming bucket still dead: {inspiring}"

    ctx = HabitCrossContext.from_dict(res.value)
    # aligned_principle_uids = embodied (outgoing) ∪ inspiring (incoming) — here both
    # resolve to the same principle, so de-dup leaves exactly one entry, no self-include.
    assert ctx.aligned_principle_uids == [R_PRINCIPLE]
    assert R_HABIT not in ctx.aligned_principle_uids
    assert R_GOAL in ctx.linked_goal_uids


# uid prefix for the label-specificity routing graph.
S = "xdctx_label_"
S_HABIT = S + "habit"
S_TASK = S + "task"
S_EVENT = S + "event"
S_OTHER_HABIT = S + "other_habit"


@pytest.mark.asyncio
async def test_incoming_buckets_route_by_specific_label(neo4j_driver, rel_backend, clean_neo4j):
    """A shared relationship must route to the label-SPECIFIC bucket, not generic Entity.

    HABITS' incoming REINFORCES_HABIT splits into reinforcing_tasks (Task),
    reinforcing_events (Event), and reinforcing_habits (Entity). Every node carries the
    :Entity label, so the generic bucket matched first under config order and swallowed
    Task/Event before their specific buckets — a latent bug the always-bidirectional
    fetch newly activated (these incoming buckets were dead under outgoing-only
    traversal). Specific-label-first sorting must send each node to its precise bucket.
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (S_HABIT, "Habit", "habit"),
            (S_TASK, "Task", "task"),
            (S_EVENT, "Event", "event"),
            (S_OTHER_HABIT, "Habit", "habit"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        # All three reinforce S_HABIT (incoming REINFORCES_HABIT edges).
        for src in (S_TASK, S_EVENT, S_OTHER_HABIT):
            await s.run(
                "MATCH (a {uid:$a}),(h {uid:$h}) "
                "CREATE (a)-[:REINFORCES_HABIT {confidence:0.95}]->(h)",
                a=src,
                h=S_HABIT,
            )

    habit_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    res = await habit_rel.get_cross_domain_context(S_HABIT, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    raw = res.value

    def _uids(bucket: str) -> set[str]:
        return {e["uid"] for e in raw.get(bucket) or []}

    # Each node lands in its own label-specific bucket — and ONLY there.
    assert _uids("reinforcing_tasks") == {S_TASK}
    assert _uids("reinforcing_events") == {S_EVENT}
    assert _uids("reinforcing_habits") == {S_OTHER_HABIT}  # generic Entity bucket: habits only


# uid prefix for the transitive-depth graph.
T = "xdctx_transitive_"
T_HABIT = T + "habit"
T_MID = T + "mid_habit"
T_NEAR_GOAL = T + "near_goal"
T_FAR_GOAL = T + "far_goal"


@pytest.mark.asyncio
async def test_depth_surfaces_transitive_node_correctly_attributed(
    neo4j_driver, rel_backend, clean_neo4j
):
    """`depth` is a real knob: a 2-hop node is attributed by the edge INCIDENT to it.

    Graph (from the source habit):
        habit -[SUPPORTS_GOAL]->      near_goal          (direct, distance 1)
        habit -[RELATED_TO]->  mid -[SUPPORTS_GOAL]-> far_goal   (transitive, distance 2)

    far_goal's incident edge is SUPPORTS_GOAL pointing INTO it, so it is correctly a
    supported goal of the habit at distance 2 — attributed by its own last hop, NOT by
    the RELATED_TO first hop that merely left the source. depth=1 sees only near_goal;
    depth=2 additionally surfaces far_goal (tagged distance=2). This is the capability
    the depth parameter exists for — and the over-inclusion fix keeps it honest.
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (T_HABIT, "Habit", "habit"),
            (T_MID, "Habit", "habit"),
            (T_NEAR_GOAL, "Goal", "goal"),
            (T_FAR_GOAL, "Goal", "goal"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        for a, rel, b in [
            (T_HABIT, "SUPPORTS_GOAL", T_NEAR_GOAL),
            (T_HABIT, "RELATED_TO", T_MID),
            (T_MID, "SUPPORTS_GOAL", T_FAR_GOAL),
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )

    habit_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )

    # depth=1: only the direct supported goal.
    d1 = await habit_rel.get_cross_domain_context(T_HABIT, depth=1, min_confidence=0.7)
    assert d1.is_ok, d1
    assert HabitCrossContext.from_dict(d1.value).linked_goal_uids == [T_NEAR_GOAL]

    # depth=2: the transitive goal is surfaced too, tagged with its true distance.
    d2 = await habit_rel.get_cross_domain_context(T_HABIT, depth=2, min_confidence=0.7)
    assert d2.is_ok, d2
    linked = set(HabitCrossContext.from_dict(d2.value).linked_goal_uids)
    assert linked == {T_NEAR_GOAL, T_FAR_GOAL}, linked
    by_uid = {e["uid"]: e["distance"] for e in d2.value["supported_goals"]}
    assert by_uid[T_NEAR_GOAL] == 1
    assert by_uid[T_FAR_GOAL] == 2


# uid prefix for the Choice cross-context graph (PR A1 — key realignment).
C = "xdctx_choice_"
C_CHOICE = C + "choice"
C_CHOICE_BARE = C + "choice_bare"  # negative control: no cross-domain edges
C_PRIN_OUT = C + "principle_out"  # choice -[INFORMED_BY_PRINCIPLE]-> (aligned_principles)
C_PRIN_IN = C + "principle_in"  # (principle) -[GUIDES_CHOICE]-> choice (guiding_principles)
C_GOAL = C + "goal"
C_KU = C + "ku"


@pytest.mark.asyncio
async def test_choice_cross_domain_context_round_trip(neo4j_driver, rel_backend, clean_neo4j):
    """Seeded choice edges surface through the realigned ChoiceCrossContext.from_dict.

    Pre-fix, ``from_dict`` read generic keys (``principles``/``supporting_goals``/
    ``conflicting_goals``/``knowledge``) that CHOICES_CONFIG never emits, so the typed
    context was empty regardless of the graph. The realignment reads the real
    ``context_field_name`` buckets: informing principles span BOTH the outgoing
    INFORMED_BY_PRINCIPLE (``aligned_principles``) and incoming GUIDES_CHOICE
    (``guiding_principles``) edges; goals come from the single AFFECTS_GOAL
    (``affected_goals``); knowledge from INFORMED_BY_KNOWLEDGE
    (``informed_by_knowledge``). There is no conflicting-goal edge, so that field
    was dropped rather than wired to a bucket nothing emits.
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (C_CHOICE, "Choice", "choice"),
            (C_PRIN_OUT, "Principle", "principle"),
            (C_PRIN_IN, "Principle", "principle"),
            (C_GOAL, "Goal", "goal"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=C_KU
        )
        for a, rel, b in [
            (C_CHOICE, "INFORMED_BY_PRINCIPLE", C_PRIN_OUT),  # outgoing -> aligned_principles
            (C_PRIN_IN, "GUIDES_CHOICE", C_CHOICE),  # incoming -> guiding_principles
            (C_CHOICE, "AFFECTS_GOAL", C_GOAL),  # -> affected_goals
            (C_CHOICE, "INFORMED_BY_KNOWLEDGE", C_KU),  # -> informed_by_knowledge
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )

    choice_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=CHOICES_CONFIG, graph_intel=None
    )
    res = await choice_rel.get_cross_domain_context(C_CHOICE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = ChoiceCrossContext.from_dict(res.value)

    # Informing principles UNION both directions (outgoing INFORMED_BY_PRINCIPLE +
    # incoming GUIDES_CHOICE) — the bug that left this empty is exactly the dead
    # incoming bucket now activated by the always-bidirectional traversal.
    assert set(ctx.informing_principle_uids) == {C_PRIN_OUT, C_PRIN_IN}
    assert ctx.affected_goal_uids == [C_GOAL]
    assert ctx.required_knowledge_uids == [C_KU]

    metrics = calculate_choice_metrics(None, ctx)
    assert metrics["principle_guidance_count"] == 2
    assert metrics["affected_goal_count"] == 1
    assert metrics["knowledge_grounding_count"] == 1
    assert metrics["is_principled"] is True
    assert metrics["affects_goals"] is True
    assert metrics["decision_clarity_score"] == 1.0  # principled AND knowledge-grounded


@pytest.mark.asyncio
async def test_choice_cross_domain_context_empty_when_no_edges(
    neo4j_driver, rel_backend, clean_neo4j
):
    """Negative control: a choice with no cross-domain edges yields an empty context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Choice {uid:$u, entity_type:'choice', title:$u, "
            "status:'active', created_at:datetime()})",
            u=C_CHOICE_BARE,
        )

    choice_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=CHOICES_CONFIG, graph_intel=None
    )
    res = await choice_rel.get_cross_domain_context(C_CHOICE_BARE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = ChoiceCrossContext.from_dict(res.value)
    assert ctx.informing_principle_uids == []
    assert ctx.affected_goal_uids == []
    assert ctx.required_knowledge_uids == []
    assert calculate_choice_metrics(None, ctx)["affected_goal_count"] == 0
