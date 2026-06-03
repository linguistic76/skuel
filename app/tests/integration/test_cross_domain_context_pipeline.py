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
    EVENTS_CONFIG,
    GOAPS_CONFIG,
    HABITS_CONFIG,
    KU_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
)
from core.services.intelligence.cross_domain_contexts import (
    ChoiceCrossContext,
    EventCrossContext,
    GoalCrossContext,
    HabitCrossContext,
    KnowledgeCrossContext,
    PrincipleCrossContext,
    TaskCrossContext,
)
from core.services.intelligence.metrics_calculators import (
    calculate_choice_metrics,
    calculate_event_metrics,
    calculate_goal_metrics,
    calculate_knowledge_metrics,
    calculate_task_metrics,
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


# uid prefix for the Event cross-context graph (key realignment).
EV = "xdctx_event_"
EV_EVENT = EV + "event"
EV_EVENT_BARE = EV + "event_bare"  # negative control: no cross-domain edges
EV_GOAL_SUP = EV + "goal_supported"  # event -[CONTRIBUTES_TO_GOAL]-> (supported_goals)
EV_GOAL_CEL = EV + "goal_celebrated"  # event -[CELEBRATES_GOAL]-> (celebrated_goals)
EV_HABIT_REIN = EV + "habit_reinforced"  # event -[REINFORCES_HABIT]-> (reinforced_habits)
EV_HABIT_PRAC = EV + "habit_practiced"  # (habit) -[PRACTICED_AT_EVENT]-> event (practiced_habits)
EV_KU = EV + "ku"


@pytest.mark.asyncio
async def test_event_cross_domain_context_round_trip(neo4j_driver, rel_backend, clean_neo4j):
    """Seeded event edges surface through the realigned EventCrossContext.from_dict.

    Pre-fix, ``from_dict`` read generic keys (``goals``/``habits``/``knowledge``) that
    EVENTS_CONFIG never emits, so the typed context was empty regardless of the graph.
    The realignment reads the real ``context_field_name`` buckets and UNIONs the two
    typed-equivalent buckets per field: supporting goals span CONTRIBUTES_TO_GOAL
    (``supported_goals``) and the milestone CELEBRATES_GOAL (``celebrated_goals``);
    reinforcing habits span the outgoing REINFORCES_HABIT (``reinforced_habits``) and
    the incoming PRACTICED_AT_EVENT (``practiced_habits``); practiced knowledge is
    APPLIES_KNOWLEDGE (``applied_knowledge``).
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (EV_EVENT, "Event", "event"),
            (EV_GOAL_SUP, "Goal", "goal"),
            (EV_GOAL_CEL, "Goal", "goal"),
            (EV_HABIT_REIN, "Habit", "habit"),
            (EV_HABIT_PRAC, "Habit", "habit"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=EV_KU
        )
        for a, rel, b in [
            (EV_EVENT, "CONTRIBUTES_TO_GOAL", EV_GOAL_SUP),  # -> supported_goals
            (EV_EVENT, "CELEBRATES_GOAL", EV_GOAL_CEL),  # -> celebrated_goals
            (EV_EVENT, "REINFORCES_HABIT", EV_HABIT_REIN),  # outgoing -> reinforced_habits
            (EV_HABIT_PRAC, "PRACTICED_AT_EVENT", EV_EVENT),  # incoming -> practiced_habits
            (EV_EVENT, "APPLIES_KNOWLEDGE", EV_KU),  # -> applied_knowledge
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )

    event_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=EVENTS_CONFIG, graph_intel=None
    )
    res = await event_rel.get_cross_domain_context(EV_EVENT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = EventCrossContext.from_dict(res.value)

    # Each field UNIONs its two typed-equivalent buckets.
    assert set(ctx.supporting_goal_uids) == {EV_GOAL_SUP, EV_GOAL_CEL}
    assert set(ctx.reinforcing_habit_uids) == {EV_HABIT_REIN, EV_HABIT_PRAC}
    assert ctx.practicing_knowledge_uids == [EV_KU]

    metrics = calculate_event_metrics(None, ctx)
    assert metrics["goal_support_count"] == 2
    assert metrics["habit_reinforcement_count"] == 2
    assert metrics["knowledge_practice_count"] == 1
    assert metrics["has_learning_component"] is True
    assert metrics["has_purpose"] is True


@pytest.mark.asyncio
async def test_event_cross_domain_context_empty_when_no_edges(
    neo4j_driver, rel_backend, clean_neo4j
):
    """Negative control: an event with no cross-domain edges yields an empty context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Event {uid:$u, entity_type:'event', title:$u, "
            "status:'active', created_at:datetime()})",
            u=EV_EVENT_BARE,
        )

    event_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=EVENTS_CONFIG, graph_intel=None
    )
    res = await event_rel.get_cross_domain_context(EV_EVENT_BARE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = EventCrossContext.from_dict(res.value)
    assert ctx.supporting_goal_uids == []
    assert ctx.reinforcing_habit_uids == []
    assert ctx.practicing_knowledge_uids == []
    assert calculate_event_metrics(None, ctx)["goal_support_count"] == 0


# uid prefix for the Task cross-context graph (key realignment).
TK = "xdctx_task_"
TK_TASK = TK + "task"
TK_TASK_BARE = TK + "task_bare"  # negative control: no cross-domain edges
TK_PREREQ = TK + "prereq_task"  # task -[DEPENDS_ON]-> (dependencies)
TK_DEPENDENT = TK + "dependent_task"  # (other) -[BLOCKED_BY]-> task (dependents)
TK_KU_REQ = TK + "ku_required"  # task -[REQUIRES_KNOWLEDGE]-> (required_knowledge)
TK_KU_APP = TK + "ku_applied"  # task -[APPLIES_KNOWLEDGE]-> (applied_knowledge)
TK_GOAL_CONTRIB = TK + "goal_contrib"  # task -[CONTRIBUTES_TO_GOAL]-> (contributing_goals)
TK_GOAL_FULFILL = TK + "goal_fulfill"  # task -[FULFILLS_GOAL]-> (goal_context)
TK_PRINCIPLE = TK + "principle"  # task -[ALIGNED_WITH_PRINCIPLE]-> (aligned_principles)


@pytest.mark.asyncio
async def test_task_cross_domain_context_round_trip(neo4j_driver, rel_backend, clean_neo4j):
    """Seeded task edges surface through the realigned TaskCrossContext.from_dict.

    Pre-fix, ``from_dict`` read generic keys (``prerequisite_tasks``/``dependent_tasks``/
    ``goals``/``principles``) that TASKS_CONFIG never emits, so those fields were empty.
    The realignment reads the real ``context_field_name`` buckets: prerequisite tasks are
    DEPENDS_ON (``dependencies``); dependent tasks are the incoming BLOCKED_BY
    (``dependents``); contributing goals span CONTRIBUTES_TO_GOAL (``contributing_goals``)
    and the single FULFILLS_GOAL (``goal_context``); aligned principles are
    ALIGNED_WITH_PRINCIPLE (``aligned_principles``); knowledge spans REQUIRES_KNOWLEDGE
    (``required_knowledge``) and APPLIES_KNOWLEDGE (``applied_knowledge``).
    """
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (TK_TASK, "Task", "task"),
            (TK_PREREQ, "Task", "task"),
            (TK_DEPENDENT, "Task", "task"),
            (TK_GOAL_CONTRIB, "Goal", "goal"),
            (TK_GOAL_FULFILL, "Goal", "goal"),
            (TK_PRINCIPLE, "Principle", "principle"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        for uid in (TK_KU_REQ, TK_KU_APP):
            await s.run(
                "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
                u=uid,
            )
        for a, rel, b in [
            (TK_TASK, "DEPENDS_ON", TK_PREREQ),  # -> dependencies
            (TK_DEPENDENT, "BLOCKED_BY", TK_TASK),  # incoming -> dependents
            (TK_TASK, "REQUIRES_KNOWLEDGE", TK_KU_REQ),  # -> required_knowledge
            (TK_TASK, "APPLIES_KNOWLEDGE", TK_KU_APP),  # -> applied_knowledge
            (TK_TASK, "CONTRIBUTES_TO_GOAL", TK_GOAL_CONTRIB),  # -> contributing_goals
            (TK_TASK, "FULFILLS_GOAL", TK_GOAL_FULFILL),  # -> goal_context
            (TK_TASK, "ALIGNED_WITH_PRINCIPLE", TK_PRINCIPLE),  # -> aligned_principles
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )

    task_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=TASKS_CONFIG, graph_intel=None
    )
    res = await task_rel.get_cross_domain_context(TK_TASK, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = TaskCrossContext.from_dict(res.value)

    assert ctx.prerequisite_task_uids == [TK_PREREQ]
    assert ctx.dependent_task_uids == [TK_DEPENDENT]
    assert ctx.required_knowledge_uids == [TK_KU_REQ]
    assert ctx.applied_knowledge_uids == [TK_KU_APP]
    # contributing goals UNION CONTRIBUTES_TO_GOAL + the single FULFILLS_GOAL.
    assert set(ctx.contributing_goal_uids) == {TK_GOAL_CONTRIB, TK_GOAL_FULFILL}
    assert ctx.aligned_principle_uids == [TK_PRINCIPLE]

    metrics = calculate_task_metrics(None, ctx)
    assert metrics["prerequisite_count"] == 1
    assert metrics["dependent_count"] == 1
    assert metrics["required_knowledge_count"] == 1
    assert metrics["applied_knowledge_count"] == 1
    assert metrics["goal_support_count"] == 2
    assert metrics["principle_alignment_count"] == 1
    assert metrics["has_dependencies"] is True


@pytest.mark.asyncio
async def test_task_cross_domain_context_empty_when_no_edges(
    neo4j_driver, rel_backend, clean_neo4j
):
    """Negative control: a task with no cross-domain edges yields an empty context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=TK_TASK_BARE,
        )

    task_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=TASKS_CONFIG, graph_intel=None
    )
    res = await task_rel.get_cross_domain_context(TK_TASK_BARE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = TaskCrossContext.from_dict(res.value)
    assert ctx.prerequisite_task_uids == []
    assert ctx.dependent_task_uids == []
    assert ctx.contributing_goal_uids == []
    assert ctx.aligned_principle_uids == []
    assert calculate_task_metrics(None, ctx)["prerequisite_count"] == 0


# uid prefix for the Knowledge (Ku) cross-context graph (key realignment, Option A).
KW = "xdctx_knowledge_"
KW_KU = KW + "ku"
KW_KU_BARE = KW + "ku_bare"  # negative control: no cross-domain edges
KW_PS_USES = KW + "ps_uses"  # (PathStep) -[USES_KU]-> ku (used_by_steps)
KW_PS_TRAINS = KW + "ps_trains"  # (PathStep) -[TRAINS_KU]-> ku (trained_by_steps)


@pytest.mark.asyncio
async def test_knowledge_cross_domain_context_round_trip(neo4j_driver, rel_backend, clean_neo4j):
    """Seeded Ku edges surface through the realigned KnowledgeCrossContext.from_dict.

    Pre-fix, ``from_dict`` read generic keys (``prerequisites``/``dependents``/``tasks``/
    ``path_steps``/``goals``) that KU_CONFIG never emits. A Ku is the atomic ontology
    node: in the graph, Activity domains attach knowledge edges to PathSteps, never to a
    ``:Ku``, and KU_CONFIG traverses only USES_KU/TRAINS_KU — so a Ku's only cross-domain
    reach is the PathSteps composing (USES_KU, ``used_by_steps``) or training (TRAINS_KU,
    ``trained_by_steps``) it. The other four fields had no usable bucket and were dropped.
    """
    async with neo4j_driver.session() as s:
        # Ku nodes carry the :Ku label (KU_CONFIG matches MATCH (center:Ku {uid})).
        await s.run(
            "CREATE (:Ku:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
            u=KW_KU,
        )
        for uid in (KW_PS_USES, KW_PS_TRAINS):
            await s.run(
                f"CREATE (:Entity:PathStep {{uid:$u, entity_type:'path_step', title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
            )
        for ps, rel in [(KW_PS_USES, "USES_KU"), (KW_PS_TRAINS, "TRAINS_KU")]:
            await s.run(
                f"MATCH (p {{uid:$p}}),(k {{uid:$k}}) CREATE (p)-[:{rel} {{confidence:0.95}}]->(k)",
                p=ps,
                k=KW_KU,
            )

    ku_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=KU_CONFIG, graph_intel=None
    )
    res = await ku_rel.get_cross_domain_context(KW_KU, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = KnowledgeCrossContext.from_dict(res.value)

    # path_step_uids UNIONs the composing (USES_KU) and training (TRAINS_KU) steps.
    assert set(ctx.path_step_uids) == {KW_PS_USES, KW_PS_TRAINS}

    metrics = calculate_knowledge_metrics(None, ctx)
    assert metrics["path_step_count"] == 2
    assert metrics["is_curriculum_integrated"] is True


@pytest.mark.asyncio
async def test_knowledge_cross_domain_context_empty_when_no_edges(
    neo4j_driver, rel_backend, clean_neo4j
):
    """Negative control: a Ku with no cross-domain edges yields an empty context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Ku:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
            u=KW_KU_BARE,
        )

    ku_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=KU_CONFIG, graph_intel=None
    )
    res = await ku_rel.get_cross_domain_context(KW_KU_BARE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    ctx = KnowledgeCrossContext.from_dict(res.value)
    assert ctx.path_step_uids == []
    assert calculate_knowledge_metrics(None, ctx)["path_step_count"] == 0
