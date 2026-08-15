"""Real-Neo4j round-trip for the Goal cross-domain-context analytics pipeline.

End-to-end guard for the Goal→typed-reader migration (PR2 of the typed-reader
convergence phase). The three analytics methods
(``get_goal_progress_dashboard`` / ``get_goal_completion_forecast`` /
``get_goal_learning_requirements``) now run over the CANONICAL typed reader
(``get_cross_domain_context_typed`` → path-aware ``GoalCrossContext``) via
``BaseAnalyticsService._analyze_entity_with_typed_context``, instead of the legacy
UID-family ``from_dict`` path.

These tests seed a real graph, run the migrated methods against it, and assert:
  * the path-aware context populates from the seeded edges (positive lock-in);
  * the rich metric blocks (cascade_impact / path_aware_context) are non-empty;
  * an edge-less goal yields an OK empty context, NOT a failure (negative control);
  * a knowledge unit reachable via two distinct paths counts once (multipath dedup);
  * the returned payloads are JSON-serializable (no PathAware* dataclass leaks —
    the regression that 500'd /api/choices/insights in #246).

Mirrors test_habits_analytics_pipeline.py (PR1). Mocked unit tests cannot catch the
key/shape mismatch (a silent empty list); the guard must run against real Cypher.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.relationship_registry import GOALS_CONFIG
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.goals._analytics_mixin import _AnalyticsMixin
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

GL = "glctx_"  # uid prefix for this module's fixture graph
GL_GOAL = GL + "goal"
GL_GOAL_BARE = GL + "goal_bare"  # negative control: no cross-domain edges
GL_TASK = GL + "task"  # task -[FULFILLS_GOAL]-> goal (contributing_tasks)
GL_HABIT = GL + "habit"  # habit -[SUPPORTS_GOAL]-> goal (contributing_habits)
GL_KU = GL + "ku"  # goal -[REQUIRES_KNOWLEDGE]-> ku (required_knowledge)
GL_SUBGOAL = GL + "subgoal"  # subgoal -[SUBGOAL_OF]-> goal (sub_goals)
GL_PARENT = GL + "parent"  # goal -[SUBGOAL_OF]-> parent (parent_goal)
GL_PRIN = GL + "principle"  # goal -[GUIDED_BY_PRINCIPLE]-> principle (aligned_principles)


@pytest.fixture
def rel_backend(neo4j_driver):
    """Multi-label Entity backend — registry edge validation requires the domain label
    alongside :Entity, so the single-:Entity form is not used."""
    return UniversalNeo4jBackend[Goal](
        neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
    )


class _FakeGoalBackend:
    """Minimal backend exposing the single ``.get`` the mixin calls — returns a real Goal."""

    def __init__(self, goal: Goal) -> None:
        self._goal = goal

    async def get(self, _uid: str) -> Result[Goal]:
        return Result.ok(self._goal)


class _FakeProgress:
    """Canned progress service for the forecast path — the migration only changed how
    forecast reads its graph_context block off the path-aware context; the velocity/forecast
    maths is untouched and out of scope, so we feed it fixed values."""

    def calculate_velocity_metrics(self, _context: Any, _goal: Goal) -> dict[str, float]:
        return {
            "current_progress_rate": 0.5,
            "task_completion_velocity": 0.3,
            "habit_consistency_score": 0.7,
        }

    def generate_forecast(self, _goal: Goal, _rate: float) -> dict[str, Any]:
        return {
            "estimated_completion_date": date.today(),
            "days_ahead_or_behind": 3,
            "completion_probability": 0.8,
        }

    def calculate_timeline_analysis(
        self, _goal: Goal, _velocity: dict[str, float], _days: int
    ) -> dict[str, Any]:
        return {
            "required_velocity": 0.4,
            "confidence_level": "medium",
            "target_date": date.today(),
            "days_remaining": 30,
            "current_pace": "on_track",
        }

    def identify_risk_factors(self, _velocity: dict[str, float], _context: Any) -> list[str]:
        return []

    def identify_acceleration_opportunities(
        self, _velocity: dict[str, float], _context: Any, _required: float
    ) -> list[str]:
        return []


class _GoalIntelHarness(_AnalyticsMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the migrated
    methods can reach ``_analyze_entity_with_typed_context``. ``graph_intel`` only needs to be
    truthy (the ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: _FakeGoalBackend, relationships: Any) -> None:
        self.backend = backend
        self.relationships = relationships
        self.progress = _FakeProgress()
        self.graph_intel = object()


def _harness(rel_backend, goal_uid: str) -> _GoalIntelHarness:
    goal = Goal(
        uid=goal_uid,
        title="Master the topic",
        user_uid="glctx_user",
        progress_percentage=25.0,
    )
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=GOALS_CONFIG, graph_intel=None
    )
    return _GoalIntelHarness(_FakeGoalBackend(goal), rels)


async def _seed_goal_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (GL_GOAL, "Goal", "goal"),
            (GL_TASK, "Task", "task"),
            (GL_HABIT, "Habit", "habit"),
            (GL_SUBGOAL, "Goal", "goal"),
            (GL_PARENT, "Goal", "goal"),
            (GL_PRIN, "Principle", "principle"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=GL_KU
        )
        for a, rel, b in [
            (GL_TASK, "FULFILLS_GOAL", GL_GOAL),  # incoming -> contributing_tasks
            (GL_HABIT, "SUPPORTS_GOAL", GL_GOAL),  # incoming -> contributing_habits
            (GL_GOAL, "REQUIRES_KNOWLEDGE", GL_KU),  # outgoing -> required_knowledge
            (GL_SUBGOAL, "SUBGOAL_OF", GL_GOAL),  # incoming -> sub_goals
            (GL_GOAL, "SUBGOAL_OF", GL_PARENT),  # outgoing -> parent_goal
            (GL_GOAL, "GUIDED_BY_PRINCIPLE", GL_PRIN),  # outgoing -> aligned_principles
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


@pytest.mark.asyncio
async def test_goal_progress_dashboard_populates_from_graph(neo4j_driver, rel_backend, clean_neo4j):
    """get_goal_progress_dashboard surfaces seeded tasks/habits and rich path-aware metrics."""
    await _seed_goal_graph(neo4j_driver)
    svc = _harness(rel_backend, GL_GOAL)

    res = await svc.get_goal_progress_dashboard(GL_GOAL, min_confidence=0.7)
    assert res.is_ok, res
    analysis = res.value

    activities = analysis["supporting_activities"]
    assert [t["uid"] for t in activities["tasks"]] == [GL_TASK]
    assert [h["uid"] for h in activities["habits"]] == [GL_HABIT]
    assert activities["learning_paths"] == []  # 0 LearningPath nodes live
    assert activities["total_tasks"] == 1
    assert activities["active_habits"] == 1

    # Flat metric keys preserved (payload contract).
    metrics = analysis["metrics"]
    assert metrics["task_support_count"] == 1
    assert metrics["habit_support_count"] == 1
    assert metrics["knowledge_requirement_count"] == 1
    assert metrics["sub_goal_count"] == 1
    assert metrics["principle_guidance_count"] == 1
    assert metrics["has_habit_system"] is True
    assert metrics["has_curriculum_alignment"] is False
    assert metrics["support_coverage"] == 1.0  # tasks + habits + knowledge all present
    assert metrics["is_well_supported"] is True

    # Rich path-aware additions are non-empty.
    assert metrics["cascade_impact"]["total_impact"] > 0.0
    pac = metrics["path_aware_context"]
    assert pac["total_strong_connections"] >= 4
    assert pac["max_path_depth"] == 1
    assert pac["avg_path_strength"] > 0.0


@pytest.mark.asyncio
async def test_goal_completion_forecast_reads_graph_context(neo4j_driver, rel_backend, clean_neo4j):
    """get_goal_completion_forecast's graph_context block reads off the path-aware context."""
    await _seed_goal_graph(neo4j_driver)
    svc = _harness(rel_backend, GL_GOAL)

    res = await svc.get_goal_completion_forecast(GL_GOAL, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    gc = res.value["graph_context"]
    assert gc["task_support_count"] == 1
    assert gc["habit_support_count"] == 1
    assert res.value["metrics"]["cascade_impact"]["total_impact"] > 0.0


@pytest.mark.asyncio
async def test_goal_learning_requirements_populates_from_graph(
    neo4j_driver, rel_backend, clean_neo4j
):
    """get_goal_learning_requirements surfaces the seeded REQUIRES_KNOWLEDGE edge."""
    await _seed_goal_graph(neo4j_driver)
    svc = _harness(rel_backend, GL_GOAL)

    res = await svc.get_goal_learning_requirements(GL_GOAL, depth=1, min_confidence=0.7)
    assert res.is_ok, res
    kr = res.value["knowledge_requirements"]
    assert [k["uid"] for k in kr["required_knowledge"]] == [GL_KU]
    assert kr["total_required"] == 1
    assert res.value["learning_paths"]["available_paths"] == []  # none live
    assert res.value["metrics"]["knowledge_requirement_count"] == 1


@pytest.mark.asyncio
async def test_goal_learning_requirements_mastery_is_real_with_context(
    neo4j_driver, rel_backend, clean_neo4j
):
    """The depth fix: passing a user context with the required KU mastered closes the gap.

    Same seeded REQUIRES_KNOWLEDGE edge as above; the only difference is whether the lens
    is handed real mastery. Context-free → the KU is an open gap (the pre-fix behaviour);
    with the KU mastered → no gap, ready_to_start flips true. Proves the lens reads actual
    ``knowledge_mastery`` end-to-end over the real graph, not a stub.
    """
    await _seed_goal_graph(neo4j_driver)
    svc = _harness(rel_backend, GL_GOAL)

    # Context-free: the required KU is an open gap.
    bare = await svc.get_goal_learning_requirements(GL_GOAL, depth=1, min_confidence=0.7)
    assert bare.is_ok, bare
    assert [g["uid"] for g in bare.value["knowledge_requirements"]["knowledge_gaps"]] == [GL_KU]
    assert bare.value["learning_analysis"]["ready_to_start"] is False

    # With the KU mastered in the user's context: gap closes, ready_to_start flips true.
    ctx = SimpleNamespace(knowledge_mastery={GL_KU: 0.9}, completed_task_uids=set())
    res = await svc.get_goal_learning_requirements(
        GL_GOAL, depth=1, min_confidence=0.7, user_context=ctx
    )
    assert res.is_ok, res
    kr = res.value["knowledge_requirements"]
    assert kr["knowledge_gaps"] == []
    assert [k["uid"] for k in kr["mastered_knowledge"]] == [GL_KU]
    assert kr["mastery_percentage"] == 100.0
    assert res.value["learning_analysis"]["ready_to_start"] is True


@pytest.mark.asyncio
async def test_goal_intelligence_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an edge-less goal yields an OK empty context, NOT a failure."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
            "status:'active', created_at:datetime()})",
            u=GL_GOAL_BARE,
        )
    svc = _harness(rel_backend, GL_GOAL_BARE)

    dash = await svc.get_goal_progress_dashboard(GL_GOAL_BARE, min_confidence=0.7)
    assert dash.is_ok, dash
    assert dash.value["supporting_activities"]["tasks"] == []
    assert dash.value["supporting_activities"]["habits"] == []
    assert dash.value["metrics"]["task_support_count"] == 0
    assert dash.value["metrics"]["has_habit_system"] is False
    # Empty context still produces the rich blocks (zeroed), not a crash.
    assert dash.value["metrics"]["cascade_impact"]["total_impact"] == 0.0
    assert dash.value["metrics"]["path_aware_context"]["max_path_depth"] == 0

    lr = await svc.get_goal_learning_requirements(GL_GOAL_BARE, depth=1, min_confidence=0.7)
    assert lr.is_ok, lr
    assert lr.value["knowledge_requirements"]["required_knowledge"] == []


@pytest.mark.asyncio
async def test_goal_dashboard_payload_is_json_serializable(neo4j_driver, rel_backend, clean_neo4j):
    """The returned payload must serialize cleanly — no PathAware* dataclass leaks.

    Guards against the #246 regression where a frozen result/dataclass in the payload
    500'd the /insights route at JSON encode. The domain ``goal`` model is replaced by a
    plain dict before encoding (routes serialize it separately); everything else — metrics,
    supporting_activities, contributions, insights, recommendations, cascade_impact,
    path_aware_context — must already be primitives/dicts (NO PathAware* leaks).
    """
    await _seed_goal_graph(neo4j_driver)
    svc = _harness(rel_backend, GL_GOAL)

    res = await svc.get_goal_progress_dashboard(GL_GOAL, min_confidence=0.7)
    assert res.is_ok, res
    payload = res.value

    serializable = {
        "supporting_activities": payload["supporting_activities"],
        "metrics": payload["metrics"],
        "contributions": payload["contributions"],
        "insights": payload["insights"],
        "recommendations": payload["recommendations"],
    }
    encoded = json.dumps(serializable, default=str)
    assert GL_TASK in encoded


@pytest.mark.asyncio
async def test_goal_dashboard_dedupes_multipath_knowledge_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A knowledge unit reachable via two distinct REQUIRES_KNOWLEDGE paths must count once.

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at depth=2
    a KU reached both directly (distance 1) and via an intermediary (distance 2) surfaces
    twice in the ``required_knowledge`` bucket. _union_path_buckets de-dupes by uid keeping
    the STRONGEST path, so the knowledge set is the two DISTINCT KUs, not three.
    """
    dup_goal = GL + "dup_goal"
    dup_mid = GL + "dup_mid_ku"  # goal -REQUIRES_KNOWLEDGE-> mid -REQUIRES_KNOWLEDGE-> ku
    dup_ku = GL + "dup_ku"  # also goal -REQUIRES_KNOWLEDGE-> ku (reached twice)
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
            "status:'active', created_at:datetime()})",
            u=dup_goal,
        )
        for uid in (dup_mid, dup_ku):
            await s.run(
                "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
                u=uid,
            )
        for a, b in [(dup_goal, dup_ku), (dup_goal, dup_mid), (dup_mid, dup_ku)]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) "
                "CREATE (a)-[:REQUIRES_KNOWLEDGE {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(rel_backend, dup_goal)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None
    raw = await svc.relationships.get_cross_domain_context(dup_goal, depth=2, min_confidence=0.7)
    assert raw.is_ok, raw
    dup_count = sum(1 for k in raw.value["required_knowledge"] if k["uid"] == dup_ku)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.get_goal_learning_requirements(dup_goal, depth=2, min_confidence=0.7)
    assert res.is_ok, res
    ku_uids = [k["uid"] for k in res.value["knowledge_requirements"]["required_knowledge"]]
    assert sorted(ku_uids) == [dup_ku, dup_mid]  # each once, no inflation
    assert res.value["metrics"]["knowledge_requirement_count"] == 2
