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
from datetime import timedelta
from typing import Any, cast
from unittest.mock import Mock

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.scheduling_enums import RecurrencePattern
from core.models.habit.habit import Habit
from core.models.relationship_registry import HABITS_CONFIG
from core.ports.domain_protocols import HabitsOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.habits._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import as_stored_clock, local_day_bounds, today_in
from core.utils.zone_context import current_zone

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
    """Minimal backend exposing the two reads the mixin makes — ``.get`` (a real Habit) and
    the adherence window (one completion on each of ``done_days_ago``), which the analyses
    hydrate the habit's rate from."""

    def __init__(self, habit: Habit, done_days_ago: list[int] | None = None) -> None:
        self._habit = habit
        self._done_days_ago = done_days_ago or []

    async def get(self, _uid: str) -> Result[Habit]:
        return Result.ok(self._habit)

    async def get_habit_window_completions(
        self, habit_uids: list[str], window_start: str, window_end: str
    ) -> Result[dict[str, list[object]]]:
        zone = current_zone()
        today = today_in(zone)
        stamps = [
            as_stored_clock(
                local_day_bounds(today - timedelta(days=n), zone)[0] + timedelta(hours=9)
            ).isoformat()
            for n in self._done_days_ago
        ]
        return Result.ok({uid: list(stamps) for uid in habit_uids})


class _HabitIntelHarness(_BehavioralSignalsMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the migrated
    methods can reach ``_analyze_entity_with_typed_context``. ``graph_intel`` only needs to be
    truthy (the ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: _FakeHabitBackend, relationships: Any) -> None:
        # Only the two reads above are reached; the rest of HabitsOperations is not.
        self.backend = cast("HabitsOperations", backend)
        self.relationships = relationships
        self.graph_intel = Mock(spec=GraphIntelligenceService)


def _harness(
    rel_backend,
    habit_uid: str,
    *,
    habit: Habit | None = None,
    done_days_ago: list[int] | None = None,
) -> _HabitIntelHarness:
    habit = habit or Habit(
        uid=habit_uid, title="Daily practice", user_uid="hbctx_user", current_streak=10
    )
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=HABITS_CONFIG, graph_intel=None
    )
    return _HabitIntelHarness(_FakeHabitBackend(habit, done_days_ago), rels)


def _measured_habit(habit_uid: str) -> Habit:
    """Older than the adherence window, so 24 kept days of the last 30 read 0.8."""
    zone = current_zone()
    return Habit(
        uid=habit_uid,
        title="Daily practice",
        user_uid="hbctx_user",
        current_streak=10,
        recurrence_pattern=RecurrencePattern.DAILY,
        created_at=as_stored_clock(local_day_bounds(today_in(zone) - timedelta(days=90), zone)[0]),
    )


def _unmeasured_habit(habit_uid: str) -> Habit:
    """A weekly habit created today: nothing due yet, so no rate (``None``, never 0.0)."""
    zone = current_zone()
    return Habit(
        uid=habit_uid,
        title="Weekly practice",
        user_uid="hbctx_user",
        current_streak=10,
        recurrence_pattern=RecurrencePattern.WEEKLY,
        created_at=as_stored_clock(local_day_bounds(today_in(zone), zone)[0]),
    )


KEPT_24_OF_30 = list(range(24))


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


# ---------------------------------------------------------------------------
# The three analyses read the habit's one consistency measure, the derived
# rate; a habit with no rate yet reads None / "unknown" there, never 0.0.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_goal_support_contribution_is_the_adherence_scaled(
    neo4j_driver, rel_backend, clean_neo4j
):
    """24 of 30 days kept (0.8): each goal gets 1.6 of 2, impact "high", alignment 1.6 of 10
    for the one goal, and the booleans read the rate."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(
        rel_backend, HB_HABIT, habit=_measured_habit(HB_HABIT), done_days_ago=KEPT_24_OF_30
    )

    res = await svc.get_habit_goal_support(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    gs = res.value["goal_support"]
    assert res.value["habit"].success_rate == pytest.approx(0.8)
    assert gs["goal_contributions"] == [
        {
            "goal_uid": HB_GOAL,
            "contribution_strength": pytest.approx(1.6),
            "estimated_impact": "high",
        }
    ]
    assert gs["alignment_score"] == pytest.approx(1.6)
    assert res.value["impact_analysis"]["consistency_matters"] is True
    assert res.value["recommendations"]["maintain_consistency"] is True
    assert res.value["recommendations"]["increase_frequency"] is False


@pytest.mark.asyncio
async def test_goal_support_with_no_rate_claims_no_contribution(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A habit with no rate yet contributes an unknown amount — None and "unknown", never a
    0.0 "low" — and no rate-derived boolean fires."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(rel_backend, HB_HABIT, habit=_unmeasured_habit(HB_HABIT), done_days_ago=[0])

    res = await svc.get_habit_goal_support(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    gs = res.value["goal_support"]
    assert res.value["habit"].success_rate is None
    assert gs["goal_contributions"] == [
        {"goal_uid": HB_GOAL, "contribution_strength": None, "estimated_impact": "unknown"}
    ]
    assert gs["alignment_score"] is None
    assert res.value["impact_analysis"]["high_impact"] is False
    assert res.value["impact_analysis"]["consistency_matters"] is False
    assert res.value["recommendations"]["increase_frequency"] is False
    assert res.value["recommendations"]["maintain_consistency"] is False


@pytest.mark.asyncio
async def test_performance_effectiveness_is_breadth_times_adherence(
    neo4j_driver, rel_backend, clean_neo4j
):
    """One reinforced Ku at 0.8 adherence: effectiveness 0.8, the rate reported under its own
    name, and "maintain consistency" advised below 0.7 only."""
    await _seed_habit_graph(neo4j_driver)
    svc = _harness(
        rel_backend, HB_HABIT, habit=_measured_habit(HB_HABIT), done_days_ago=KEPT_24_OF_30
    )

    res = await svc.analyze_habit_performance(HB_HABIT, min_confidence=0.7)
    assert res.is_ok, res
    perf = res.value["performance"]
    assert perf["success_rate"] == pytest.approx(0.8)
    assert "consistency_score" not in perf
    assert perf["reinforcement_effectiveness"] == pytest.approx(0.8)
    assert res.value["recommendations"]["maintain_consistency"] is False

    svc = _harness(rel_backend, HB_HABIT, habit=_unmeasured_habit(HB_HABIT), done_days_ago=[0])
    res = await svc.analyze_habit_performance(HB_HABIT, min_confidence=0.7)
    assert res.is_ok, res
    perf = res.value["performance"]
    assert perf["success_rate"] is None
    assert perf["reinforcement_effectiveness"] is None
    assert res.value["insights"]["high_reinforcement"] is False
    assert res.value["recommendations"]["maintain_consistency"] is False


@pytest.mark.asyncio
async def test_practice_effectiveness_base_is_the_adherence(neo4j_driver, rel_backend, clean_neo4j):
    """0.8 * 5 base + 0.5 for one Ku + 2 * 10/30 streak = 5.167; with no rate the base term is
    absent and the two bonuses stand (1.167)."""
    await _seed_habit_graph(neo4j_driver)
    bonuses = 0.5 + (10 / 30.0) * 2.0

    svc = _harness(
        rel_backend, HB_HABIT, habit=_measured_habit(HB_HABIT), done_days_ago=KEPT_24_OF_30
    )
    res = await svc.get_habit_knowledge_reinforcement(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    assert res.value["knowledge_reinforcement"]["practice_effectiveness_score"] == pytest.approx(
        0.8 * 5.0 + bonuses
    )
    assert res.value["learning_analysis"]["learning_consistency"] == pytest.approx(0.8)

    svc = _harness(rel_backend, HB_HABIT, habit=_unmeasured_habit(HB_HABIT), done_days_ago=[0])
    res = await svc.get_habit_knowledge_reinforcement(HB_HABIT, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    assert res.value["knowledge_reinforcement"]["practice_effectiveness_score"] == pytest.approx(
        bonuses
    )
    assert res.value["learning_analysis"]["learning_consistency"] is None
