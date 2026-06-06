"""Real-Neo4j round-trip for the Habit cross-domain-context analytics pipeline.

End-to-end guard for the Habit→typed-reader migration (PR1 of the typed-reader
convergence phase). The three behavioral-signals methods
(``analyze_habit_performance`` / ``get_habit_knowledge_reinforcement`` /
``get_habit_goal_support``) now run over the CANONICAL typed reader
(``get_cross_domain_context_typed`` → path-aware ``HabitCrossContext``) via
``BaseAnalyticsService._analyze_entity_with_typed_context``, instead of the legacy
UID-family ``from_dict`` path.

These tests seed a real graph, run the migrated methods against it, and assert:
  * the path-aware context populates from the seeded edges (positive lock-in);
  * the rich metric blocks (cascade_impact / path_aware_context) are non-empty;
  * an edge-less habit yields an OK empty context, NOT a failure (negative control);
  * a goal reachable via two distinct paths counts once (multipath dedup guard);
  * the returned payloads are JSON-serializable (no PathAware* dataclass leaks —
    the regression that 500'd /api/choices/insights in #246).

Mirrors the Choice family-B tests in test_cross_domain_context_pipeline.py.
Mocked unit tests cannot catch the key/shape mismatch (a silent empty list); the
guard must run against real Cypher.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.habit import Habit
from core.models.relationship_registry import HABITS_CONFIG
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.habits._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

HB = "hbctx_"  # uid prefix for this module's fixture graph
HB_HABIT = HB + "habit"
HB_HABIT_BARE = HB + "habit_bare"  # negative control: no cross-domain edges
HB_GOAL = HB + "goal"  # habit -[SUPPORTS_GOAL]-> (supported_goals)
HB_KU = HB + "ku"  # habit -[REINFORCES_KNOWLEDGE]-> (reinforced_knowledge)
HB_PRIN_OUT = HB + "principle_out"  # habit -[EMBODIES_PRINCIPLE]-> (embodied_principles)
HB_PRIN_IN = HB + "principle_in"  # (principle) -[INSPIRES_HABIT]-> habit (inspiring_principles)
HB_PREREQ = HB + "prereq"  # habit -[REQUIRES_PREREQUISITE]-> (prerequisite_habits)


@pytest.fixture
def rel_backend(neo4j_driver):
    """Multi-label Entity backend — registry edge validation requires the domain label
    alongside :Entity, so the single-:Entity form is not used."""
    return UniversalNeo4jBackend[Habit](
        neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY
    )


class _FakeHabitBackend:
    """Minimal backend exposing the single ``.get`` the mixin calls — returns a real Habit."""

    def __init__(self, habit: Habit) -> None:
        self._habit = habit

    async def get(self, _uid: str) -> Result[Habit]:
        return Result.ok(self._habit)


class _HabitIntelHarness(_BehavioralSignalsMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the migrated
    methods can reach ``_analyze_entity_with_typed_context``. ``graph_intel`` only needs to be
    truthy (the ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: _FakeHabitBackend, relationships: Any) -> None:
        self.backend = backend
        self.relationships = relationships
        self.path_helper = PathAwareAnalyzer()
        self.graph_intel = object()


def _harness(rel_backend, habit_uid: str) -> _HabitIntelHarness:
    habit = Habit(uid=habit_uid, title="Daily practice", user_uid="hbctx_user", current_streak=10)
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    return _HabitIntelHarness(_FakeHabitBackend(habit), rels)


async def _seed_habit_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (HB_HABIT, "Habit", "habit"),
            (HB_GOAL, "Goal", "goal"),
            (HB_PRIN_OUT, "Principle", "principle"),
            (HB_PRIN_IN, "Principle", "principle"),
            (HB_PREREQ, "Habit", "habit"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=HB_KU
        )
        for a, rel, b in [
            (HB_HABIT, "SUPPORTS_GOAL", HB_GOAL),
            (HB_HABIT, "REINFORCES_KNOWLEDGE", HB_KU),
            (HB_HABIT, "EMBODIES_PRINCIPLE", HB_PRIN_OUT),  # outgoing -> embodied_principles
            (HB_PRIN_IN, "INSPIRES_HABIT", HB_HABIT),  # incoming -> inspiring_principles
            (HB_HABIT, "REQUIRES_PREREQUISITE", HB_PREREQ),
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


@pytest.mark.asyncio
async def test_analyze_habit_performance_populates_from_graph(
    neo4j_driver, rel_backend, clean_neo4j
):
    """analyze_habit_performance surfaces seeded goals + knowledge and rich path-aware metrics."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(rel_backend, HB_HABIT)

    res = await svc.analyze_habit_performance(HB_HABIT, min_confidence=0.7)
    assert res.is_ok, res
    analysis = res.value

    perf = analysis["performance"]
    assert perf["supporting_goal_uids"] == [HB_GOAL]
    assert perf["knowledge_reinforcement_uids"] == [HB_KU]
    assert perf["total_goals_supported"] == 1
    assert perf["total_knowledge_areas"] == 1

    # Flat metric keys preserved (payload contract).
    metrics = analysis["metrics"]
    assert metrics["has_goal_connection"] is True
    assert metrics["is_knowledge_builder"] is True
    assert metrics["is_principle_aligned"] is True
    assert metrics["goal_support_count"] == 1
    assert metrics["integration_score"] == 1.0

    # Rich path-aware additions are non-empty.
    assert metrics["cascade_impact"]["total_impact"] > 0.0
    pac = metrics["path_aware_context"]
    assert pac["total_strong_connections"] >= 3
    assert pac["max_path_depth"] == 1
    assert pac["avg_path_strength"] > 0.0

    assert analysis["insights"]["knowledge_builder"] is True


@pytest.mark.asyncio
async def test_get_habit_knowledge_reinforcement_populates_from_graph(
    neo4j_driver, rel_backend, clean_neo4j
):
    """get_habit_knowledge_reinforcement surfaces the seeded REINFORCES_KNOWLEDGE edge."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(rel_backend, HB_HABIT)

    res = await svc.get_habit_knowledge_reinforcement(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    kr = res.value["knowledge_reinforcement"]
    assert kr["knowledge_reinforcement_uids"] == [HB_KU]
    assert kr["practice_effectiveness_score"] > 0.0
    assert res.value["metrics"]["cascade_impact"]["total_impact"] > 0.0


@pytest.mark.asyncio
async def test_get_habit_goal_support_populates_from_graph(neo4j_driver, rel_backend, clean_neo4j):
    """get_habit_goal_support surfaces the seeded SUPPORTS_GOAL edge + principle union."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(rel_backend, HB_HABIT)

    res = await svc.get_habit_goal_support(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    gs = res.value["goal_support"]
    assert gs["supporting_goal_uids"] == [HB_GOAL]
    assert gs["total_goals_supported"] == 1
    assert gs["primary_goal_uid"] == HB_GOAL

    # Principles union both directions (EMBODIES_PRINCIPLE out + INSPIRES_HABIT in).
    assert res.value["metrics"]["principle_alignment_count"] == 2


@pytest.mark.asyncio
async def test_habit_intelligence_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an edge-less habit yields an OK empty context, NOT a failure."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Habit {uid:$u, entity_type:'habit', title:$u, "
            "status:'active', created_at:datetime()})",
            u=HB_HABIT_BARE,
        )
    svc = _harness(rel_backend, HB_HABIT_BARE)

    perf = await svc.analyze_habit_performance(HB_HABIT_BARE, min_confidence=0.7)
    assert perf.is_ok, perf
    assert perf.value["performance"]["supporting_goal_uids"] == []
    assert perf.value["performance"]["knowledge_reinforcement_uids"] == []
    assert perf.value["metrics"]["has_goal_connection"] is False
    assert perf.value["metrics"]["integration_score"] == 0.0
    # Empty context still produces the rich blocks (zeroed), not a crash.
    assert perf.value["metrics"]["cascade_impact"]["total_impact"] == 0.0
    assert perf.value["metrics"]["path_aware_context"]["max_path_depth"] == 0

    gs = await svc.get_habit_goal_support(HB_HABIT_BARE, depth=1, min_confidence=0.7)
    assert gs.is_ok, gs
    assert gs.value["goal_support"]["supporting_goal_uids"] == []


@pytest.mark.asyncio
async def test_habit_performance_payload_is_json_serializable(
    neo4j_driver, rel_backend, clean_neo4j
):
    """The returned payload must serialize cleanly — no PathAware* dataclass leaks.

    Guards against the #246 regression where a frozen result/dataclass in the payload
    500'd the /insights route at JSON encode. The domain ``habit`` model is replaced by a
    plain dict before encoding (routes serialize it separately); everything else — metrics,
    performance, insights, recommendations, cascade_impact, path_aware_context — must
    already be primitives/dicts (NO PathAware* dataclass leaks).
    """
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(rel_backend, HB_HABIT)

    res = await svc.analyze_habit_performance(HB_HABIT, min_confidence=0.7)
    assert res.is_ok, res
    payload = res.value

    # The non-model payload sections must be PURE primitives. No json default fallback —
    # a leaked PathAware* dataclass would raise TypeError here (the #246 failure mode).
    serializable = {
        "performance": payload["performance"],
        "metrics": payload["metrics"],
        "insights": payload["insights"],
        "recommendations": payload["recommendations"],
    }
    encoded = json.dumps(serializable)
    assert HB_GOAL in encoded


@pytest.mark.asyncio
async def test_habit_goal_support_dedupes_multipath_goals_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A goal reachable via two distinct SUPPORTS_GOAL paths must count once.

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at depth=2
    a goal reached both directly (distance 1) and via an intermediary (distance 2) surfaces
    twice in the ``supported_goals`` bucket. _union_path_buckets de-dupes by uid keeping the
    STRONGEST path, so the goal set is the two DISTINCT goals, not three, and the retained
    duplicate entry is the direct (distance 1) one.
    """
    dup_habit = HB + "dup_habit"
    dup_mid = HB + "dup_mid_goal"  # habit -SUPPORTS_GOAL-> mid -SUPPORTS_GOAL-> goal
    dup_goal = HB + "dup_goal"  # also habit -SUPPORTS_GOAL-> goal (reached twice)
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Habit {uid:$u, entity_type:'habit', title:$u, "
            "status:'active', created_at:datetime()})",
            u=dup_habit,
        )
        for uid in (dup_mid, dup_goal):
            await s.run(
                "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        for a, b in [(dup_habit, dup_goal), (dup_habit, dup_mid), (dup_mid, dup_goal)]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) CREATE (a)-[:SUPPORTS_GOAL {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(rel_backend, dup_habit)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None
    raw = await svc.relationships.get_cross_domain_context(dup_habit, depth=2, min_confidence=0.7)
    assert raw.is_ok, raw
    dup_count = sum(1 for g in raw.value["supported_goals"] if g["uid"] == dup_goal)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.get_habit_goal_support(dup_habit, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    goal_uids = res.value["goal_support"]["supporting_goal_uids"]
    assert sorted(goal_uids) == [dup_goal, dup_mid]  # each once, no inflation
    assert res.value["goal_support"]["total_goals_supported"] == 2
