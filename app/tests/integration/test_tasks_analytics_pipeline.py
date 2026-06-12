"""Real-Neo4j round-trip for the Task cross-domain-context analytics pipeline.

End-to-end guard for the Task "unify + elevate" migration (PR5, final domain, of the
typed-reader convergence phase). ``get_domain_insights`` (GET /api/tasks/insights) now
COMPOSES two sources:

  1. Task's distinctive READINESS lens — graph-intel ``get_knowledge_prerequisites``
     (``knowledge_prerequisites`` / ``has_prerequisites``) plus task-field insights — kept
     intact.
  2. A path-aware CROSS-DOMAIN block over the CANONICAL typed reader
     (``get_cross_domain_context_typed`` → path-aware ``TaskCrossContext``) via
     ``BaseAnalyticsService._analyze_entity_with_typed_context`` — knowledge it
     requires/applies + goals it contributes to, with cascade_impact / path_aware_context,
     surfaced additively under ``cross_domain``.

Scope of the cross-domain block is cross-domain ONLY: same-domain task→task dependencies
(DEPENDS_ON) are NOT part of it (owned by the lateral-relationships system / ZPD) — they
were dropped from the path-aware ``TaskCrossContext`` in this migration.

These tests seed a real graph, run the migrated method against it, and assert:
  * the path-aware cross-domain block populates from the seeded edges, with the two goal-link
    directions (CONTRIBUTES_TO_GOAL + FULFILLS_GOAL) folded in (positive lock-in);
  * the rich metric blocks (cascade_impact / path_aware_context) are non-empty;
  * the existing readiness keys (``knowledge_prerequisites`` / ``has_prerequisites``) and the
    task-field ``insights`` dict are still present (composition, not replacement);
  * an edge-less task yields an OK insights payload with the readiness block + an OK empty
    cross-domain block (``available: True`` / zeroed counts), NOT a 500/fail (negative
    control);
  * a goal reachable via two distinct paths counts once (multipath dedup);
  * the returned payload is JSON-serializable (no PathAware* dataclass leaks).

Mirrors test_events_analytics_pipeline.py (PR4). Mocked unit tests cannot catch the
key/shape mismatch (a silent empty list); the guard must run against real Cypher.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_registry import TASKS_CONFIG
from core.models.task.task import Task
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.utils.result_simplified import Result

TK = "tkctx_"  # uid prefix for this module's fixture graph
TK_TASK = TK + "task"
TK_TASK_BARE = TK + "task_bare"  # negative control: no cross-domain edges
TK_KU_REQ = TK + "ku_req"  # task -[REQUIRES_KNOWLEDGE]-> ku (required_knowledge)
TK_KU_APP = TK + "ku_app"  # task -[APPLIES_KNOWLEDGE]-> ku (applied_knowledge)
TK_GOAL_CONTRIB = TK + "goal_contrib"  # task -[CONTRIBUTES_TO_GOAL]-> goal (contributing_goals)
TK_GOAL_FULFILL = TK + "goal_fulfill"  # task -[FULFILLS_GOAL]-> goal (goal_context)


@pytest.fixture
def rel_backend(neo4j_driver):
    """Multi-label Entity backend — registry edge validation requires the domain label
    alongside :Entity, so the single-:Entity form is not used."""
    return UniversalNeo4jBackend[Task](
        neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY
    )


class _FakeTaskBackend:
    """Minimal backend exposing the single ``.get`` the service calls — returns a Task."""

    def __init__(self, task: Task) -> None:
        self._task = task

    async def get(self, _uid: str) -> Result[Task]:
        return Result.ok(self._task)


class _TaskIntelHarness(_CoreIntelligenceMixin, BaseAnalyticsService):
    """Mirrors the real service composition so ``get_domain_insights`` can reach both
    ``_analyze_entity_with_typed_context`` (cross-domain block) AND ``graph_intel``
    (readiness block). ``graph_intel`` is left None here so the readiness block degrades to
    its empty-prerequisites branch — the cross-domain composition is what this guard
    exercises, and the readiness keys must still be present."""

    # Bind the real method under test from the shell service (not a mixin).
    get_domain_insights = TasksIntelligenceService.get_domain_insights
    _build_cross_domain_block = TasksIntelligenceService._build_cross_domain_block

    def __init__(self, backend: _FakeTaskBackend, relationships: Any) -> None:
        from core.utils.logging import get_logger

        self.backend = backend
        self.relationships = relationships
        self.graph_intel = None
        self.logger = get_logger("test.tasks.intel")


def _harness(rel_backend, task_uid: str) -> _TaskIntelHarness:
    task = Task(uid=task_uid, title="Write the report", user_uid="tkctx_user", priority="high")
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=TASKS_CONFIG, graph_intel=None
    )
    return _TaskIntelHarness(_FakeTaskBackend(task), rels)


async def _seed_task_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=TK_TASK,
        )
        for uid, label, etype in [
            (TK_GOAL_CONTRIB, "Goal", "goal"),
            (TK_GOAL_FULFILL, "Goal", "goal"),
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
            (TK_TASK, "REQUIRES_KNOWLEDGE", TK_KU_REQ),  # -> required_knowledge
            (TK_TASK, "APPLIES_KNOWLEDGE", TK_KU_APP),  # -> applied_knowledge
            (TK_TASK, "CONTRIBUTES_TO_GOAL", TK_GOAL_CONTRIB),  # -> contributing_goals
            (TK_TASK, "FULFILLS_GOAL", TK_GOAL_FULFILL),  # -> goal_context
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


@pytest.mark.asyncio
async def test_task_insights_compose_readiness_and_cross_domain(
    neo4j_driver, rel_backend, clean_neo4j
):
    """get_domain_insights surfaces the readiness keys AND a populated path-aware
    cross-domain block (knowledge + both goal-link directions) with rich metrics."""
    await _seed_task_graph(neo4j_driver)
    svc = _harness(rel_backend, TK_TASK)

    res = await svc.get_domain_insights(TK_TASK)
    assert res.is_ok, res
    insights = res.value

    # Readiness lens preserved (graph_intel is None here → empty prerequisites, key present).
    assert insights["task_uid"] == TK_TASK
    assert insights["task_title"] == "Write the report"
    assert "knowledge_prerequisites" in insights
    assert "has_prerequisites" in insights
    assert insights["insights"]["is_high_priority"] is True

    # Additive cross-domain block populated.
    cd = insights["cross_domain"]
    assert cd["available"] is True

    ctx = cd["context"]
    assert ctx["total_connections"] == 4  # 2 knowledge + 2 goals
    assert ctx["required_knowledge"] == [TK_KU_REQ]
    assert ctx["applied_knowledge"] == [TK_KU_APP]
    assert set(ctx["contributing_goals"]) == {TK_GOAL_CONTRIB, TK_GOAL_FULFILL}

    metrics = cd["metrics"]
    assert metrics["required_knowledge_count"] == 1
    assert metrics["applied_knowledge_count"] == 1
    assert metrics["knowledge_coverage"] == 2
    assert metrics["goal_support_count"] == 2
    assert metrics["has_required_knowledge"] is True
    assert metrics["has_applied_knowledge"] is True
    assert metrics["has_goal_support"] is True

    # Rich path-aware additions are non-empty.
    assert metrics["cascade_impact"]["total_impact"] > 0.0
    pac = metrics["path_aware_context"]
    assert pac["total_strong_connections"] == 4  # all 4 edges at confidence 0.95
    assert pac["direct_connections_count"] == 4  # all distance=1
    assert pac["max_path_depth"] == 1
    assert pac["avg_path_strength"] > 0.0

    assert isinstance(cd["recommendations"], list)


@pytest.mark.asyncio
async def test_task_insights_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an edge-less task yields an OK insights payload with the readiness
    block AND an OK empty cross-domain block — NOT a 500/failure."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=TK_TASK_BARE,
        )
    svc = _harness(rel_backend, TK_TASK_BARE)

    res = await svc.get_domain_insights(TK_TASK_BARE)
    assert res.is_ok, res
    insights = res.value

    # Readiness keys present.
    assert "knowledge_prerequisites" in insights
    assert insights["has_prerequisites"] is False

    # Cross-domain block is OK-empty (available True, zeroed), not absent / not a crash.
    cd = insights["cross_domain"]
    assert cd["available"] is True
    assert cd["context"]["total_connections"] == 0
    assert cd["context"]["required_knowledge"] == []
    assert cd["context"]["applied_knowledge"] == []
    assert cd["context"]["contributing_goals"] == []
    assert cd["metrics"]["knowledge_coverage"] == 0
    assert cd["metrics"]["goal_support_count"] == 0
    assert cd["metrics"]["cascade_impact"]["total_impact"] == 0.0
    assert cd["metrics"]["path_aware_context"]["max_path_depth"] == 0
    assert cd["metrics"]["path_aware_context"]["direct_connections_count"] == 0


@pytest.mark.asyncio
async def test_task_insights_payload_is_json_serializable(neo4j_driver, rel_backend, clean_neo4j):
    """The returned payload must serialize cleanly — no PathAware* dataclass leaks.

    Guards against the #246 regression where a frozen dataclass in the payload 500'd the
    /insights route at JSON encode. Everything must be primitives/dicts (the cross-domain
    block surfaces UIDs/counts, never PathAware* instances).
    """
    await _seed_task_graph(neo4j_driver)
    svc = _harness(rel_backend, TK_TASK)

    res = await svc.get_domain_insights(TK_TASK)
    assert res.is_ok, res

    encoded = json.dumps(res.value, default=str)
    assert TK_KU_REQ in encoded
    assert "cross_domain" in encoded
    assert "cascade_impact" in encoded


@pytest.mark.asyncio
async def test_task_insights_dedupes_multipath_goal_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A goal reachable via two distinct CONTRIBUTES_TO_GOAL paths must count once.

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at depth=2
    a goal reached both directly and via an intermediary surfaces twice in the
    ``contributing_goals`` bucket. _union_path_buckets de-dupes by uid keeping the STRONGEST
    path, so the goal set is the two DISTINCT goals, not three.
    """
    dup_task = TK + "dup_task"
    dup_mid = TK + "dup_mid_goal"  # task -CONTRIBUTES_TO_GOAL-> mid -CONTRIBUTES_TO_GOAL-> goal
    dup_goal = TK + "dup_goal"  # also task -CONTRIBUTES_TO_GOAL-> goal (reached twice)
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
            "status:'active', created_at:datetime()})",
            u=dup_task,
        )
        for uid in (dup_mid, dup_goal):
            await s.run(
                "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        for a, b in [(dup_task, dup_goal), (dup_task, dup_mid), (dup_mid, dup_goal)]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) "
                "CREATE (a)-[:CONTRIBUTES_TO_GOAL {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(rel_backend, dup_task)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None
    raw = await svc.relationships.get_cross_domain_context(dup_task, depth=2, min_confidence=0.7)
    assert raw.is_ok, raw
    dup_count = sum(1 for g in raw.value["contributing_goals"] if g["uid"] == dup_goal)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.get_domain_insights(dup_task)
    assert res.is_ok, res
    cd = res.value["cross_domain"]
    # path-aware context dedupes to the two DISTINCT goals (no inflation).
    assert cd["metrics"]["goal_support_count"] == 2
    assert set(cd["context"]["contributing_goals"]) == {dup_mid, dup_goal}
