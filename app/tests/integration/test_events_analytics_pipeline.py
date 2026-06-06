"""Real-Neo4j round-trip for the Event cross-domain-context analytics pipeline.

End-to-end guard for the Event→typed-reader migration (PR4 of the typed-reader
convergence phase). ``analyze_event_performance`` (GET /api/events/insights via
``get_domain_insights``) now runs over the CANONICAL typed reader
(``get_cross_domain_context_typed`` → path-aware ``EventCrossContext``) via
``BaseAnalyticsService._analyze_entity_with_typed_context``, instead of the previous
direct per-helper construction (``get_cross_domain_context`` / ``get_related_uids`` /
``get_habit_links_for_events``).

These tests seed a real graph, run the migrated method against it, and assert:
  * the path-aware context populates from the seeded edges, with the two-direction
    goal/habit unions folded in (positive lock-in);
  * the legacy nested payload shape (goal_support / habit_reinforcement /
    knowledge_reinforcement + overall_impact_score) is preserved;
  * the rich metric blocks (cascade_impact / path_aware_context) are non-empty;
  * an edge-less event yields an OK empty context, NOT a failure (negative control) —
    a behavior the old direct method also tolerated, now via the typed reader's
    ok-empty-context policy;
  * a goal reachable via two distinct paths counts once (multipath dedup);
  * the returned payload is JSON-serializable (no PathAware* dataclass leaks — the
    regression that 500'd /api/choices/insights in #246).

Mirrors test_principles_analytics_pipeline.py (PR3). Mocked unit tests cannot catch the
key/shape mismatch (a silent empty list); the guard must run against real Cypher.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.relationship_registry import EVENTS_CONFIG
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.events._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

EV = "evctx_"  # uid prefix for this module's fixture graph
EV_EVENT = EV + "event"
EV_EVENT_BARE = EV + "event_bare"  # negative control: no cross-domain edges
EV_GOAL = EV + "goal"  # event -[CONTRIBUTES_TO_GOAL]-> goal (supported_goals)
EV_GOAL_CELEB = EV + "goal_celeb"  # event -[CELEBRATES_GOAL]-> goal (celebrated_goals)
EV_HABIT = EV + "habit"  # event -[REINFORCES_HABIT]-> habit (reinforced_habits)
EV_HABIT_PRAC = EV + "habit_prac"  # habit -[PRACTICED_AT_EVENT]-> event (practiced_habits)
EV_KU = EV + "ku"  # event -[APPLIES_KNOWLEDGE]-> ku (applied_knowledge)


@pytest.fixture
def rel_backend(neo4j_driver):
    """Multi-label Entity backend — registry edge validation requires the domain label
    alongside :Entity, so the single-:Entity form is not used."""
    return UniversalNeo4jBackend[Event](
        neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY
    )


class _FakeEventBackend:
    """Minimal backend exposing the single ``.get`` the mixin calls — returns an Event."""

    def __init__(self, event: Event) -> None:
        self._event = event

    async def get(self, _uid: str) -> Result[Event]:
        return Result.ok(self._event)


class _EventIntelHarness(_CoreIntelligenceMixin, BaseAnalyticsService):
    """Mirrors the real service composition (mixin + BaseAnalyticsService) so the migrated
    method can reach ``_analyze_entity_with_typed_context``. ``graph_intel`` only needs to be
    truthy (the ``@requires_graph_intelligence`` guard is its sole reader)."""

    def __init__(self, backend: _FakeEventBackend, relationships: Any) -> None:
        self.backend = backend
        self.relationships = relationships
        self.graph_intel = object()


def _harness(rel_backend, event_uid: str, *, quality: int | None = 4) -> _EventIntelHarness:
    event = Event(
        uid=event_uid,
        title="Morning workout",
        user_uid="evctx_user",
        habit_completion_quality=quality,
        duration_minutes=45,
    )
    rels: UnifiedRelationshipService[Any, Any, Any] = UnifiedRelationshipService(
        backend=rel_backend, config=EVENTS_CONFIG, graph_intel=None
    )
    return _EventIntelHarness(_FakeEventBackend(event), rels)


async def _seed_event_graph(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (EV_EVENT, "Event", "event"),
            (EV_GOAL, "Goal", "goal"),
            (EV_GOAL_CELEB, "Goal", "goal"),
            (EV_HABIT, "Habit", "habit"),
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
            (EV_EVENT, "CONTRIBUTES_TO_GOAL", EV_GOAL),  # outgoing -> supported_goals
            (EV_EVENT, "CELEBRATES_GOAL", EV_GOAL_CELEB),  # outgoing -> celebrated_goals
            (EV_EVENT, "REINFORCES_HABIT", EV_HABIT),  # outgoing -> reinforced_habits
            (EV_HABIT_PRAC, "PRACTICED_AT_EVENT", EV_EVENT),  # incoming -> practiced_habits
            (EV_EVENT, "APPLIES_KNOWLEDGE", EV_KU),  # outgoing -> applied_knowledge
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}),(b {{uid:$b}}) CREATE (a)-[:{rel} {{confidence:0.95}}]->(b)",
                a=a,
                b=b,
            )


@pytest.mark.asyncio
async def test_event_performance_populates_from_graph(neo4j_driver, rel_backend, clean_neo4j):
    """analyze_event_performance surfaces seeded goals/habits/knowledge + rich path-aware metrics,
    folding both goal directions (supported + celebrated) and both habit directions
    (reinforced + practiced) into the path-aware context."""
    await _seed_event_graph(neo4j_driver)
    svc = _harness(rel_backend, EV_EVENT)

    res = await svc.analyze_event_performance(EV_EVENT)
    assert res.is_ok, res
    analysis = res.value

    # Legacy nested payload shape preserved.
    assert analysis["event_uid"] == EV_EVENT
    assert analysis["event_title"] == "Morning workout"

    gs = analysis["goal_support"]
    assert gs["supports_goals"] is True
    assert gs["goal_uid"] in {EV_GOAL, EV_GOAL_CELEB}  # single-goal lens (goals[0])
    assert gs["contribution_weight"] == 1.0

    hr = analysis["habit_reinforcement"]
    assert hr["reinforces_habit"] is True
    assert hr["habit_uid"] in {EV_HABIT, EV_HABIT_PRAC}  # single-habit lens (habits[0])
    assert hr["quality_score"] == 4

    kr = analysis["knowledge_reinforcement"]
    assert kr["reinforces_knowledge"] is True
    assert kr["knowledge_units"] == [EV_KU]
    assert kr["knowledge_count"] == 1
    assert kr["study_time_minutes"] == 45

    # overall_impact_score: goal 1.0 + habit (1.0 + 4/5=0.8) + knowledge (1*0.5) = 3.3
    assert analysis["overall_impact_score"] == pytest.approx(3.3)

    # graph_context_depth = total cross-domain connections (2 goals + 2 habits + 1 ku).
    assert analysis["graph_context_depth"] == 5

    # Rich path-aware additions are non-empty.
    assert analysis["cascade_impact"]["total_impact"] > 0.0
    pac = analysis["path_aware_context"]
    assert pac["total_strong_connections"] == 5  # all 5 edges at confidence 0.95
    assert pac["direct_connections_count"] == 5  # all distance=1
    assert pac["max_path_depth"] == 1
    assert pac["avg_path_strength"] > 0.0


@pytest.mark.asyncio
async def test_event_performance_empty_when_no_edges(neo4j_driver, rel_backend, clean_neo4j):
    """Negative control: an edge-less event yields an OK empty context, NOT a failure."""
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Event {uid:$u, entity_type:'event', title:$u, "
            "status:'active', created_at:datetime()})",
            u=EV_EVENT_BARE,
        )
    svc = _harness(rel_backend, EV_EVENT_BARE, quality=None)

    res = await svc.analyze_event_performance(EV_EVENT_BARE)
    assert res.is_ok, res
    analysis = res.value

    assert analysis["goal_support"]["supports_goals"] is False
    assert analysis["goal_support"]["goal_uid"] is None
    assert analysis["habit_reinforcement"]["reinforces_habit"] is False
    assert analysis["knowledge_reinforcement"]["reinforces_knowledge"] is False
    assert analysis["overall_impact_score"] == 0.0
    assert analysis["graph_context_depth"] == 0
    # Empty context still produces the rich blocks (zeroed), not a crash.
    assert analysis["cascade_impact"]["total_impact"] == 0.0
    assert analysis["path_aware_context"]["max_path_depth"] == 0
    assert analysis["path_aware_context"]["direct_connections_count"] == 0


@pytest.mark.asyncio
async def test_event_performance_payload_is_json_serializable(
    neo4j_driver, rel_backend, clean_neo4j
):
    """The returned payload must serialize cleanly — no PathAware* dataclass leaks.

    Guards against the #246 regression where a frozen result/dataclass in the payload
    500'd the /insights route at JSON encode. Everything in the payload —
    goal_support / habit_reinforcement / knowledge_reinforcement / overall_impact_score /
    cascade_impact / path_aware_context — must be primitives/dicts (status is an
    EntityStatus enum, encoded via default=str as the route already does).
    """
    await _seed_event_graph(neo4j_driver)
    svc = _harness(rel_backend, EV_EVENT)

    res = await svc.analyze_event_performance(EV_EVENT)
    assert res.is_ok, res

    encoded = json.dumps(res.value, default=str)
    assert EV_KU in encoded
    assert "cascade_impact" in encoded


@pytest.mark.asyncio
async def test_event_performance_dedupes_multipath_goal_at_depth2(
    neo4j_driver, rel_backend, clean_neo4j
):
    """A goal reachable via two distinct CONTRIBUTES_TO_GOAL paths must count once.

    The Cypher behind get_cross_domain_context does ``collect(DISTINCT {uid, distance,
    path_strength, ...})`` — DISTINCT over the whole path map, not the uid — so at depth=2
    a goal reached both directly (distance 1) and via an intermediary (distance 2) surfaces
    twice in the ``supported_goals`` bucket. _union_path_buckets de-dupes by uid keeping the
    STRONGEST path, so the goal set is the two DISTINCT goals, not three.
    """
    dup_event = EV + "dup_event"
    dup_mid = EV + "dup_mid_goal"  # event -CONTRIBUTES_TO_GOAL-> mid -CONTRIBUTES_TO_GOAL-> goal
    dup_goal = EV + "dup_goal"  # also event -CONTRIBUTES_TO_GOAL-> goal (reached twice)
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:Event {uid:$u, entity_type:'event', title:$u, "
            "status:'active', created_at:datetime()})",
            u=dup_event,
        )
        for uid in (dup_mid, dup_goal):
            await s.run(
                "CREATE (:Entity:Goal {uid:$u, entity_type:'goal', title:$u, "
                "status:'active', created_at:datetime()})",
                u=uid,
            )
        for a, b in [(dup_event, dup_goal), (dup_event, dup_mid), (dup_mid, dup_goal)]:
            await s.run(
                "MATCH (a {uid:$a}),(b {uid:$b}) "
                "CREATE (a)-[:CONTRIBUTES_TO_GOAL {confidence:0.95}]->(b)",
                a=a,
                b=b,
            )
    svc = _harness(rel_backend, dup_event)

    # Sanity: the raw bucket DOES carry the duplicate (proves dedup is load-bearing).
    assert svc.relationships is not None
    raw = await svc.relationships.get_cross_domain_context(dup_event, depth=2, min_confidence=0.7)
    assert raw.is_ok, raw
    dup_count = sum(1 for g in raw.value["supported_goals"] if g["uid"] == dup_goal)
    assert dup_count >= 2, f"expected multipath duplicate, got {dup_count}"

    res = await svc.analyze_event_performance(dup_event)
    assert res.is_ok, res
    # path-aware context dedupes to the two DISTINCT goals (no inflation).
    assert res.value["path_aware_context"]["direct_connections_count"] == 2
