"""Real-Neo4j round-trip for the Principle cross-domain-context analytics pipeline.

End-to-end guard for the Principle→typed-reader migration (PR3 of the typed-reader
convergence phase). ``assess_principle_alignment`` (GET /api/principles/insights) now
runs over the CANONICAL typed reader (``get_cross_domain_context_typed`` → path-aware
``PrincipleCrossContext``) via ``BaseAnalyticsService._analyze_entity_with_typed_context``,
instead of the legacy UID-family ``from_dict`` path.

These tests seed a real graph, run the migrated method against it, and assert:
  * the path-aware context populates from the seeded edges (positive lock-in);
  * the rich metric blocks (cascade_impact / path_aware_context) are non-empty;
  * an edge-less principle yields an OK empty context, NOT a failure (negative control);
  * a habit reachable via two distinct paths counts once (multipath dedup);
  * the returned payload is JSON-serializable (no PathAware* dataclass leaks — the
    regression that 500'd /api/choices/insights in #246).

Mirrors test_goals_analytics_pipeline.py (PR2) / test_habits_analytics_pipeline.py (PR1).
Mocked unit tests cannot catch the key/shape mismatch (a silent empty list); the guard
must run against real Cypher. (This file also locks in the fix for a LATENT bug: the
pre-migration consumer read metric keys ``calculate_principle_metrics`` never produced —
``choice_count`` / ``adherence_score`` / ``needs_attention`` / ... — so any principle with
a non-empty context KeyError'd at /api/principles/insights.)
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.principle.principle import Principle
from core.models.relationship_registry import PRINCIPLES_CONFIG
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.principles._alignment_intelligence_mixin import _AlignmentIntelligenceMixin
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

PR = "prnctx_"  # uid prefix for this module's fixture graph
PR_USER = PR + "user"  # every seeded activity node is user-owned (Principle.user_uid is required)
PR_PRIN = PR + "principle"
PR_PRIN_BARE = PR + "principle_bare"  # negative control: no cross-domain edges
PR_GOAL = PR + "goal"  # principle -[GUIDES_GOAL]-> goal (guided_goals)
PR_CHOICE = PR + "choice"  # principle -[GUIDES_CHOICE]-> choice (guided_choices)
PR_KU = PR + "ku"  # principle -[GROUNDED_IN_KNOWLEDGE]-> ku (grounding_knowledge)
PR_HABIT = PR + "habit"  # principle -[INSPIRES_HABIT]-> habit (inspired_habits)
PR_HABIT_EMB = PR + "habit_emb"  # habit -[EMBODIES_PRINCIPLE]-> principle (embodying_habits)


@pytest.fixture
def rel_backend(neo4j_driver):
    """Multi-label Entity backend — registry edge validation requires the domain label
    alongside :Entity, so the single-:Entity form is not used."""
    return UniversalNeo4jBackend[Principle](
        neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
    )


class _PrincipleIntelHarness(_AlignmentIntelligenceMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the migrated
    method can reach ``_analyze_entity_with_typed_context``. ``graph_intel`` only needs to be
    truthy (the ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: PrinciplesOperations, relationships: Any) -> None:
        self.backend = backend
        self.relationships = relationships
        self.graph_intel = object()


def _harness(rel_backend) -> _PrincipleIntelHarness:
    """Harness over the REAL backend — every principle these tests analyse is seeded as a
    real ``:Entity:Principle`` node, so ``.get`` reads the graph rather than a stub."""
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=PRINCIPLES_CONFIG, graph_intel=None
    )
    return _PrincipleIntelHarness(rel_backend, rels)


async def _seed_principle_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (PR_PRIN, "Principle", "principle"),
            (PR_GOAL, "Goal", "goal"),
            (PR_CHOICE, "Choice", "choice"),
            (PR_HABIT, "Habit", "habit"),
            (PR_HABIT_EMB, "Habit", "habit"),
        ]:
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"user_uid:$user, status:'active', created_at:datetime()}})",
                u=uid,
                t=etype,
                user=PR_USER,
            )
        await s.run(
            "CREATE (:Entity {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=PR_KU
        )
        for a, rel, b in [
            (PR_PRIN, "GUIDES_GOAL", PR_GOAL),  # outgoing -> guided_goals
            (PR_PRIN, "GUIDES_CHOICE", PR_CHOICE),  # outgoing -> guided_choices
            (PR_PRIN, "GROUNDED_IN_KNOWLEDGE", PR_KU),  # outgoing -> grounding_knowledge
            (PR_PRIN, "INSPIRES_HABIT", PR_HABIT),  # outgoing -> inspired_habits
            (PR_HABIT_EMB, "EMBODIES_PRINCIPLE", PR_PRIN),  # incoming -> embodying_habits
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


@pytest.mark.asyncio
async def test_principle_alignment_populates_from_graph(neo4j_driver, rel_backend, clean_neo4j):
    """assess_principle_alignment surfaces seeded goals/choices/habits + rich path-aware metrics."""
    await _seed_principle_graph(neo4j_driver)
    svc = _harness(rel_backend)

    res = await svc.assess_principle_alignment(PR_PRIN, min_confidence=0.7)
    assert res.is_ok, res
    analysis = res.value

    breakdown = analysis["activities_breakdown"]
    assert [g["uid"] for g in breakdown["goals"]] == [PR_GOAL]
    assert [c["uid"] for c in breakdown["choices"]] == [PR_CHOICE]
    # Both INSPIRES_HABIT (outgoing) and EMBODIES_PRINCIPLE (incoming) habits union in.
    assert sorted(h["uid"] for h in breakdown["habits"]) == sorted([PR_HABIT, PR_HABIT_EMB])
    assert breakdown["tasks"] == []  # principles don't relate to tasks

    counts = analysis["activity_counts"]
    assert counts["goals"] == 1
    assert counts["choices"] == 1
    assert counts["habits"] == 2
    assert counts["total"] == 4  # goals + habits + choices

    # Flat metric keys the consumer reads — all present (latent KeyError fixed).
    metrics = analysis["metrics"]
    assert metrics["guided_goal_count"] == 1
    assert metrics["informed_choice_count"] == 1
    assert metrics["aligned_habit_count"] == 2
    assert metrics["knowledge_grounding_count"] == 1
    assert metrics["total_influence_count"] == 4
    assert metrics["influence_score"] == 1.0  # all 4 dimensions present
    assert metrics["is_action_guiding"] is True
    assert metrics["is_knowledge_grounded"] is True
    assert metrics["is_lived"] is True
    # Alignment keys (the pre-migration KeyError set).
    assert metrics["adherence_score"] == 1.0
    assert metrics["goal_count"] == 1
    assert metrics["choice_count"] == 1
    assert metrics["habit_count"] == 2
    assert metrics["knowledge_count"] == 1
    assert metrics["needs_attention"] is False
    assert metrics["strong_alignment"] is True
    assert metrics["consistent_practice"] is True

    assert analysis["alignment_score"] == 1.0
    assert analysis["alignment_assessment"]["strong_alignment"] is True

    # Rich path-aware additions are non-empty.
    assert metrics["cascade_impact"]["total_impact"] > 0.0
    assert analysis["cascade_impact"]["total_impact"] > 0.0
    pac = analysis["path_aware_context"]
    assert pac["total_strong_connections"] >= 5
    assert pac["max_path_depth"] == 1
    assert pac["avg_path_strength"] > 0.0

    # recommendations is a LIST (the contract assess_principle_alignment surfaces).
    assert isinstance(analysis["recommendations"], list)


@pytest.mark.asyncio
async def test_principle_alignment_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an edge-less principle yields an OK empty context, NOT a failure."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Principle {uid:$u, entity_type:'principle', title:$u, "
            "user_uid:$user, status:'active', created_at:datetime()})",
            u=PR_PRIN_BARE,
            user=PR_USER,
        )
    svc = _harness(rel_backend)

    res = await svc.assess_principle_alignment(PR_PRIN_BARE, min_confidence=0.7)
    assert res.is_ok, res
    analysis = res.value

    assert analysis["activities_breakdown"]["goals"] == []
    assert analysis["activities_breakdown"]["habits"] == []
    assert analysis["activity_counts"]["total"] == 0

    metrics = analysis["metrics"]
    assert metrics["guided_goal_count"] == 0
    assert metrics["total_influence_count"] == 0
    assert metrics["influence_score"] == 0.0
    assert metrics["adherence_score"] == 0.0
    assert metrics["needs_attention"] is True
    assert metrics["is_lived"] is False
    # Empty context still produces the rich blocks (zeroed), not a crash.
    assert metrics["cascade_impact"]["total_impact"] == 0.0
    assert analysis["path_aware_context"]["max_path_depth"] == 0
    assert isinstance(analysis["recommendations"], list)


@pytest.mark.asyncio
async def test_principle_alignment_payload_is_json_serializable(
    neo4j_driver, rel_backend, clean_neo4j
):
    """The returned payload must serialize cleanly — no PathAware* dataclass leaks.

    Guards against the #246 regression where a frozen result/dataclass in the payload
    500'd the /insights route at JSON encode. The domain ``principle`` model is replaced by
    a plain string before encoding (routes serialize it separately); everything else —
    metrics, activities_breakdown, activity_counts, alignment_assessment, recommendations,
    cascade_impact, path_aware_context — must already be primitives/dicts.
    """
    await _seed_principle_graph(neo4j_driver)
    svc = _harness(rel_backend)

    res = await svc.assess_principle_alignment(PR_PRIN, min_confidence=0.7)
    assert res.is_ok, res
    payload = dict(res.value)
    payload["principle"] = "<model>"  # routes serialize the domain model separately

    encoded = json.dumps(payload, default=str)
    assert PR_GOAL in encoded
    assert "cascade_impact" in encoded


@pytest.mark.asyncio
async def test_principle_alignment_dedupes_multipath_habit_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A habit reachable via two distinct INSPIRES_HABIT paths must count once.

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at depth=2
    a habit reached both directly (distance 1) and via an intermediary (distance 2) surfaces
    twice in the ``inspired_habits`` bucket. _union_path_buckets de-dupes by uid keeping the
    STRONGEST path, so the habit set is the two DISTINCT habits, not three.
    """
    dup_prin = PR + "dup_principle"
    dup_mid = PR + "dup_mid_habit"  # prin -INSPIRES_HABIT-> mid -INSPIRES_HABIT-> habit
    dup_habit = PR + "dup_habit"  # also prin -INSPIRES_HABIT-> habit (reached twice)
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Principle {uid:$u, entity_type:'principle', title:$u, "
            "user_uid:$user, status:'active', created_at:datetime()})",
            u=dup_prin,
            user=PR_USER,
        )
        for uid in (dup_mid, dup_habit):
            await s.run(
                "CREATE (:Entity:Habit {uid:$u, entity_type:'habit', title:$u, "
                "user_uid:$user, status:'active', created_at:datetime()})",
                u=uid,
                user=PR_USER,
            )
        for a, b in [(dup_prin, dup_habit), (dup_prin, dup_mid), (dup_mid, dup_habit)]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) "
                "CREATE (a)-[:INSPIRES_HABIT {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(rel_backend)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None
    raw = await svc.relationships.get_cross_domain_context(dup_prin, depth=2, min_confidence=0.7)
    assert raw.is_ok, raw
    dup_count = sum(1 for h in raw.value["inspired_habits"] if h["uid"] == dup_habit)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.assess_principle_alignment(dup_prin, min_confidence=0.7)
    assert res.is_ok, res
    habit_uids = [h["uid"] for h in res.value["activities_breakdown"]["habits"]]
    assert sorted(habit_uids) == sorted([dup_habit, dup_mid])  # each once, no inflation
    assert res.value["metrics"]["aligned_habit_count"] == 2
