"""Real-Neo4j round-trip for the cross-domain-context traversal + analytics pipeline.

End-to-end guards for the config-driven cross-domain reader that powers every domain
dashboard. Two layers are exercised:

1. ``UnifiedRelationshipService.get_cross_domain_context`` — the generic, config-driven
   traversal that categorizes incident edges into the registry ``context_field_name``
   buckets (direction-aware, depth-aware, label-specific, de-duplicated).
2. The CANONICAL typed reader path behind ``/api/choices/insights`` — the choices
   ``_core_intelligence_mixin`` builds ``ChoiceImpactAnalysis`` / ``DecisionIntelligence``
   over ``BaseAnalyticsService._analyze_entity_with_typed_context`` (path-aware context).

These tests seed a real graph and assert the seeded relationships surface in the raw
buckets and through the live mixin methods. Negative controls (entities with no edges)
prove the result reflects the graph rather than a hard-coded value.

Mocked unit tests cannot catch this (the key mismatch is a silent empty list); the
guard must run against real Cypher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.goal.goal_dto import GoalDTO
from core.models.relationship_registry import (
    CHOICES_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
)
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.choices._core_intelligence_mixin import (
    _CoreIntelligenceMixin as ChoiceCoreIntelMixin,
)
from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncSession


def _bucket_uids(raw: dict[str, Any], *names: str) -> set[str]:
    """Collect entity UIDs across one or more raw cross-domain-context buckets."""
    out: set[str] = set()
    for name in names:
        for entity in raw.get(name) or []:
            uid = entity.get("uid") if isinstance(entity, dict) else entity
            if uid:
                out.add(uid)
    return out


@pytest.fixture
def rel_backend(neo4j_driver):
    """Generic Entity backend — the same shape injected as a domain's relationships backend."""
    return UniversalNeo4jBackend[GoalDTO](neo4j_driver, "Entity", GoalDTO)


# ---------------------------------------------------------------------------
# Traversal mechanics: direction-aware bucketing on the canonical reciprocal pair.
# ---------------------------------------------------------------------------

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
    canonical principle<->habit 2-cycle put the principle's own uid into the aligned-habit
    buckets (and a :Principle node into a habit bucket, since the mapping's
    ``target_label="Entity"`` matches every node). Verified live before the fix; this
    locks the regression. depth=2 is essential — depth=1 never reproduced it.
    """
    async with neo4j_driver.session() as s:
        await _seed_reciprocal_pair(s)

    prin_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=PRINCIPLES_CONFIG, graph_intel=None
    )
    # depth=2 is the production default for the principles dashboard.
    res = await prin_rel.get_cross_domain_context(R_PRINCIPLE, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    raw = res.value

    # The principle's direct, distance-1 alignment is the habit — and ONLY the habit
    # (aligned habits span INSPIRES_HABIT outgoing + EMBODIES_PRINCIPLE incoming).
    aligned_habits = _bucket_uids(raw, "inspired_habits", "embodying_habits")
    assert R_HABIT in aligned_habits
    assert R_PRINCIPLE not in aligned_habits, "source leaked into its own bucket"
    assert aligned_habits == {R_HABIT}, f"over-inclusion: {aligned_habits}"
    assert R_GOAL in _bucket_uids(raw, "guided_goals")


@pytest.mark.asyncio
async def test_habit_incoming_buckets_populate(neo4j_driver, rel_backend, clean_neo4j):
    """Habit INCOMING cross-domain buckets must populate (direction-aware traversal).

    ``HABITS_CONFIG.bidirectional_relationships`` is empty, which formerly made
    ``get_cross_domain_context`` traverse outgoing edges only — so every incoming
    habit bucket (here ``inspiring_principles`` via the incoming INSPIRES_HABIT edge
    ``principle -> habit``) was structurally always empty. The traversal now always
    fetches both directions and categorizes per-mapping ``direction``, so the bucket
    fills and aligned principles span both EMBODIES_PRINCIPLE (outgoing) and
    INSPIRES_HABIT (incoming), mirroring the principle side.
    """
    async with neo4j_driver.session() as s:
        await _seed_reciprocal_pair(s)

    habit_rel: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    res = await habit_rel.get_cross_domain_context(R_HABIT, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    raw = res.value

    # The incoming-only bucket now carries the principle that inspires this habit.
    inspiring = [e["uid"] for e in raw.get("inspiring_principles") or []]
    assert R_PRINCIPLE in inspiring, f"incoming bucket still dead: {inspiring}"

    # aligned principles = embodied (outgoing) union inspiring (incoming) — here both
    # resolve to the same principle, so de-dup leaves exactly one, no self-include.
    aligned_principles = _bucket_uids(raw, "embodied_principles", "inspiring_principles")
    assert aligned_principles == {R_PRINCIPLE}
    assert R_HABIT not in aligned_principles
    assert R_GOAL in _bucket_uids(raw, "supported_goals")


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

    # Each node lands in its own label-specific bucket — and ONLY there.
    assert _bucket_uids(raw, "reinforcing_tasks") == {S_TASK}
    assert _bucket_uids(raw, "reinforcing_events") == {S_EVENT}
    assert _bucket_uids(raw, "reinforcing_habits") == {S_OTHER_HABIT}  # generic Entity bucket


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
    assert _bucket_uids(d1.value, "supported_goals") == {T_NEAR_GOAL}

    # depth=2: the transitive goal is surfaced too, tagged with its true distance.
    d2 = await habit_rel.get_cross_domain_context(T_HABIT, depth=2, min_confidence=0.7)
    assert d2.is_ok, d2
    linked = _bucket_uids(d2.value, "supported_goals")
    assert linked == {T_NEAR_GOAL, T_FAR_GOAL}, linked
    by_uid = {e["uid"]: e["distance"] for e in d2.value["supported_goals"]}
    assert by_uid[T_NEAR_GOAL] == 1
    assert by_uid[T_FAR_GOAL] == 2


# ---------------------------------------------------------------------------
# The genuinely-LIVE pipeline behind /api/choices/insights.
#
# choices/_core_intelligence_mixin.py builds ChoiceImpactAnalysis / DecisionIntelligence
# over BaseAnalyticsService._analyze_entity_with_typed_context (the CANONICAL typed
# reader → path-aware ChoiceCrossContext). These tests exercise the REAL mixin methods
# against a seeded graph.
# ---------------------------------------------------------------------------

FB = "xdctx_fb_"  # uid prefix for the live-mixin graph
FB_CHOICE = FB + "choice"
FB_CHOICE_BARE = FB + "choice_bare"
FB_PRIN_OUT = FB + "principle_out"  # choice -[INFORMED_BY_PRINCIPLE]-> (aligned_principles)
FB_PRIN_IN = FB + "principle_in"  # (principle) -[GUIDES_CHOICE]-> choice (guiding_principles)
FB_GOAL = FB + "goal"
FB_KU = FB + "ku"


class _FakeChoiceBackend:
    """Minimal backend exposing the single ``.get`` the mixin calls — returns a real Choice."""

    def __init__(self, choice: Choice) -> None:
        self._choice = choice

    async def get(self, _uid: str) -> Result[Choice]:
        return Result.ok(self._choice)


class _ChoiceIntelHarness(ChoiceCoreIntelMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the thin-lens
    analyzers can reach ``_analyze_entity_with_typed_context``. Wires the attributes those
    methods read; ``graph_intel`` only needs to be truthy (the
    ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: _FakeChoiceBackend, relationships: Any) -> None:
        self.backend = backend
        self.relationships = relationships
        self.path_helper = PathAwareAnalyzer()
        self.graph_intel = object()


async def _seed_choice_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (FB_CHOICE, "Choice", "choice"),
            (FB_PRIN_OUT, "Principle", "principle"),
            (FB_PRIN_IN, "Principle", "principle"),
            (FB_GOAL, "Goal", "goal"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=FB_KU
        )
        for a, rel, b in [
            (FB_CHOICE, "INFORMED_BY_PRINCIPLE", FB_PRIN_OUT),
            (FB_PRIN_IN, "GUIDES_CHOICE", FB_CHOICE),
            (FB_CHOICE, "AFFECTS_GOAL", FB_GOAL),
            (FB_CHOICE, "INFORMED_BY_KNOWLEDGE", FB_KU),
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


def _harness(neo4j_driver, rel_backend, choice_uid: str) -> _ChoiceIntelHarness:
    choice = Choice(uid=choice_uid, title="Decide", user_uid="xdctx_user")
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=CHOICES_CONFIG, graph_intel=None
    )
    return _ChoiceIntelHarness(_FakeChoiceBackend(choice), rels)


@pytest.mark.asyncio
async def test_analyze_choice_impact_populates_from_graph(neo4j_driver, rel_backend, clean_neo4j):
    """analyze_choice_impact surfaces seeded goals + principles (the /api/choices/insights path)."""
    await _seed_choice_graph(neo4j_driver)
    svc = _harness(neo4j_driver, rel_backend, FB_CHOICE)

    res = await svc.analyze_choice_impact(FB_CHOICE, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    analysis = res.value

    # AFFECTS_GOAL is polarity-free → the single goal lands in the affected set.
    assert analysis.domain_impact.goals.count == 1
    # Principles union both directions (INFORMED_BY_PRINCIPLE out + GUIDES_CHOICE in).
    assert analysis.domain_impact.principles.count == 2
    assert "goals" in analysis.impact_summary.domains_affected
    assert "principles" in analysis.impact_summary.domains_affected
    assert analysis.impact_summary.total_entities_affected == 3  # 1 goal + 2 principles


@pytest.mark.asyncio
async def test_get_decision_intelligence_populates_from_graph(
    neo4j_driver, rel_backend, clean_neo4j
):
    """get_decision_intelligence surfaces seeded goals, principles AND knowledge."""
    await _seed_choice_graph(neo4j_driver)
    svc = _harness(neo4j_driver, rel_backend, FB_CHOICE)

    res = await svc.get_decision_intelligence(FB_CHOICE, min_confidence=0.7, depth=1)
    assert res.is_ok, res
    intel = res.value

    assert [g.uid for g in intel.context.goals] == [FB_GOAL]
    assert {p.uid for p in intel.context.principles} == {FB_PRIN_OUT, FB_PRIN_IN}
    assert [k.uid for k in intel.context.knowledge] == [FB_KU]


@pytest.mark.asyncio
async def test_choice_intelligence_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: a choice with no cross-domain edges yields empty impact/context."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Choice {uid:$u, entity_type:'choice', title:$u, "
            "status:'active', created_at:datetime()})",
            u=FB_CHOICE_BARE,
        )
    svc = _harness(neo4j_driver, rel_backend, FB_CHOICE_BARE)

    impact = await svc.analyze_choice_impact(FB_CHOICE_BARE, depth=1, min_confidence=0.7)
    assert impact.is_ok, impact
    assert impact.value.domain_impact.goals.count == 0
    assert impact.value.domain_impact.principles.count == 0
    assert impact.value.impact_summary.total_entities_affected == 0

    intel = await svc.get_decision_intelligence(FB_CHOICE_BARE, min_confidence=0.7, depth=1)
    assert intel.is_ok, intel
    assert intel.value.context.goals == []
    assert intel.value.context.principles == []
    assert intel.value.context.knowledge == []


# Multi-path graph: the choice reaches FB_DUP_GOAL by TWO distinct AFFECTS_GOAL paths.
FB_DUP_CHOICE = FB + "dup_choice"
FB_DUP_MID = FB + "dup_mid"  # choice -[AFFECTS_GOAL]-> mid -[AFFECTS_GOAL]-> goal (2-hop)
FB_DUP_GOAL = FB + "dup_goal"  # also choice -[AFFECTS_GOAL]-> goal (1-hop) → reached twice


@pytest.mark.asyncio
async def test_choice_impact_dedupes_multipath_goals_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A goal reachable via two distinct paths must count once (Codex #218 P2).

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at
    depth=2 FB_DUP_GOAL surfaces twice (direct AFFECTS_GOAL, distance 1; and via
    FB_DUP_MID, distance 2). Both entries are incident-AFFECTS_GOAL → both land in the
    ``affected_goals`` bucket. _union_buckets de-dupes by uid, so the affected set is the
    two DISTINCT goals (FB_DUP_GOAL once + FB_DUP_MID), not three — otherwise goal count,
    stake level, impact score and cascade impact all inflate.
    """
    async with neo4j_driver.session() as s:
        for uid in (FB_DUP_CHOICE, FB_DUP_MID, FB_DUP_GOAL):
            label = "Choice" if uid == FB_DUP_CHOICE else "Goal"
            etype = "choice" if uid == FB_DUP_CHOICE else "goal"
            await s.run(
                f"CREATE (:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        for a, b in [
            (FB_DUP_CHOICE, FB_DUP_GOAL),  # 1-hop
            (FB_DUP_CHOICE, FB_DUP_MID),  # 1-hop (FB_DUP_MID also affected)
            (FB_DUP_MID, FB_DUP_GOAL),  # 2-hop path to FB_DUP_GOAL
        ]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) CREATE (a)-[:AFFECTS_GOAL {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(neo4j_driver, rel_backend, FB_DUP_CHOICE)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None  # harness always wires the relationship service
    raw = await svc.relationships.get_cross_domain_context(
        FB_DUP_CHOICE, depth=2, min_confidence=0.7
    )
    assert raw.is_ok, raw
    dup_count = sum(1 for g in raw.value["affected_goals"] if g["uid"] == FB_DUP_GOAL)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.analyze_choice_impact(FB_DUP_CHOICE, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    intel = await svc.get_decision_intelligence(FB_DUP_CHOICE, min_confidence=0.7, depth=2)
    assert intel.is_ok, intel

    goals = intel.value.context.goals
    goal_uids = [g.uid for g in goals]
    assert sorted(goal_uids) == [FB_DUP_GOAL, FB_DUP_MID]  # each once, no inflation
    assert res.value.domain_impact.goals.count == 2

    # The STRONGEST path is kept, not the first raw occurrence: FB_DUP_GOAL is directly
    # reachable (distance 1) AND via FB_DUP_MID (distance 2), so its retained entry must
    # be the direct one — otherwise distance / direct-connection counts misreport.
    dup_goal = next(g for g in goals if g.uid == FB_DUP_GOAL)
    assert dup_goal.distance == 1
