"""Real-Neo4j guard for Convergence Phase 1 (PR 2B): Goals + Habits onto mechanism B.

2B routes the Goals and Habits intelligence-service graph-context retrieval
(``get_with_context``, used by both the facade and the ``/api/<domain>/context``
route) through ``UnifiedRelationshipService.get_with_context`` — the
registry-sourced mechanism B the Tasks facade established in 2A (PR #225).
(The ``get_<domain>_with_context`` domain-named aliases were deleted in the
tasks bloat campaign — generic ``get_with_context`` is the one path.)
Two things must hold:

1. **Delegation, no recursion.** The intelligence ``get_with_context`` must route
   to ``self.relationships`` (the shared mixin owns the real implementation).
   Locked by the two ``*_delegation_routes_to_mechanism_b_without_recursion`` tests.
2. **Registry-sourced edges surface (live Neo4j).** Through the very method the mixins
   delegate to, a Goal/Habit surfaces a registry edge that the bare default-intent
   clause (GOAL_ACHIEVEMENT / PRACTICE) omits, while a noise edge outside the registry
   is filtered out. The negative control proves the bare clause genuinely misses it.

See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.cross_domain_backend import _INTENT_EDGE_SETS, CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.goal.goal_dto import GoalDTO
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.relationship_registry import GOALS_CONFIG, HABITS_CONFIG
from core.services.goals.goals_intelligence_service import GoalsIntelligenceService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result

P = "conv2b_"  # uid prefix for this module's fixture graph

# --- Goals fixture graph ---
GOAL = P + "goal"
GOAL_CHOICE = P + "goal_choice"  # via INSPIRED_BY_CHOICE (registry edge, NOT in GOAL_ACHIEVEMENT)
GOAL_PRINCIPLE = P + "goal_principle"  # principle -[SUPPORTS_GOAL]-> goal (registry edge)
GOAL_NOISE = P + "goal_noise"  # via NOISE_LINK (outside the registry → filtered)

# --- Habits fixture graph ---
HABIT = P + "habit"
HABIT_GOAL = P + "habit_goal"  # via SUPPORTS_GOAL (registry edge, NOT in PRACTICE clause)
HABIT_NOISE = P + "habit_noise"  # via NOISE_LINK (outside the registry → filtered)


def _uids(graph_context) -> set[str]:
    return {node.uid for node in graph_context.all_nodes}


# ============================================================================
# Delegation / recursion guard (no Neo4j — pure wiring)
# ============================================================================


def _intel_stub(cls):
    """An intelligence service with only the attrs get_with_context needs."""
    svc = cls.__new__(cls)
    svc.graph_intel = MagicMock()  # truthy → @requires_graph_intelligence does not short-circuit
    svc.logger = MagicMock()
    rel = MagicMock()
    rel.get_with_context = AsyncMock(return_value="MECHANISM_B")
    svc.relationships = rel
    return svc, rel


@pytest.mark.asyncio
async def test_goals_delegation_routes_to_mechanism_b_without_recursion():
    svc, rel = _intel_stub(GoalsIntelligenceService)
    assert await svc.get_with_context("g", 2) == "MECHANISM_B"
    rel.get_with_context.assert_any_await("g", 2)


@pytest.mark.asyncio
async def test_habits_delegation_routes_to_mechanism_b_without_recursion():
    """The Habits read is mechanism B with the habit's derived rate hydrated on top."""
    svc, rel = _intel_stub(HabitsIntelligenceService)
    habit = Habit(uid="h", user_uid="u", title="h")
    graph_context = MagicMock()
    rel.get_with_context = AsyncMock(return_value=Result.ok((habit, graph_context)))
    svc.backend = MagicMock()
    svc.backend.get_habit_window_completions = AsyncMock(return_value=Result.ok({"h": []}))

    result = await svc.get_with_context("h", 2)

    assert result.is_ok
    assert result.value[0].uid == "h" and result.value[1] is graph_context
    rel.get_with_context.assert_any_await("h", 2)
    svc.backend.get_habit_window_completions.assert_awaited_once()


@pytest.mark.asyncio
async def test_delegation_fails_cleanly_without_relationship_service():
    svc = GoalsIntelligenceService.__new__(GoalsIntelligenceService)
    svc.graph_intel = MagicMock()
    svc.logger = MagicMock()
    svc.relationships = None
    res = await svc.get_with_context("g")
    assert res.is_error, "missing relationship_service must be an error, not a recursion/crash"


# ============================================================================
# Registry-sourced traversal through mechanism B (live Neo4j)
# ============================================================================


@pytest.fixture
def goals_rel(neo4j_driver):
    """Goals UnifiedRelationshipService wired to a real graph_intel — mechanism B."""
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = UniversalNeo4jBackend[GoalDTO](neo4j_driver, "Entity", GoalDTO)
    return UnifiedRelationshipService(backend=backend, config=GOALS_CONFIG, graph_intel=graph_intel)


@pytest.fixture
def habits_rel(neo4j_driver):
    """Habits UnifiedRelationshipService wired to a real graph_intel — mechanism B."""
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = UniversalNeo4jBackend[HabitDTO](neo4j_driver, "Entity", HabitDTO)
    return UnifiedRelationshipService(
        backend=backend, config=HABITS_CONFIG, graph_intel=graph_intel
    )


@pytest.mark.asyncio
async def test_goals_registry_sourced_through_get_with_context(
    neo4j_driver, goals_rel, clean_neo4j
):
    """A goal's registry edge (INSPIRED_BY_CHOICE) surfaces via get_with_context; noise filtered."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (GOAL, "Goal", "goal"),
            (GOAL_CHOICE, "Choice", "choice"),
            (GOAL_PRINCIPLE, "Principle", "principle"),
            (GOAL_NOISE, "Goal", "goal"),
        ]:
            # The origin is converted to a domain model by get_with_context; Goal is
            # user-owned and requires a user_uid (the neighbours are returned as raw nodes).
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', user_uid:'conv2b_user', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (g{uid:$g}),(c{uid:$c}) CREATE (g)-[:INSPIRED_BY_CHOICE]->(c)",
            g=GOAL,
            c=GOAL_CHOICE,
        )
        await s.run(
            "MATCH (p{uid:$p}),(g{uid:$g}) CREATE (p)-[:SUPPORTS_GOAL]->(g)",
            p=GOAL_PRINCIPLE,
            g=GOAL,
        )
        await s.run(
            "MATCH (g{uid:$g}),(n{uid:$n}) CREATE (g)-[:NOISE_LINK]->(n)", g=GOAL, n=GOAL_NOISE
        )

    # INSPIRED_BY_CHOICE is a registry edge but is absent from the hard-coded
    # GOAL_ACHIEVEMENT clause; SUPPORTS_GOAL is in both.
    assert "INSPIRED_BY_CHOICE" in GOALS_CONFIG.cross_domain_relationship_types
    assert "SUPPORTS_GOAL" in GOALS_CONFIG.cross_domain_relationship_types
    assert "INSPIRED_BY_CHOICE" not in _INTENT_EDGE_SETS["goal_achievement"]
    assert "SUPPORTS_GOAL" in _INTENT_EDGE_SETS["goal_achievement"]
    assert GOALS_CONFIG.default_context_intent.value == "goal_achievement"

    # Mechanism B (intent=None → registry-sourced): the real edges surface, noise out.
    # get_with_context returns (entity, GraphContext) — the context is the second element.
    reg = await goals_rel.get_with_context(GOAL, depth=1)
    assert reg.is_ok, reg
    _goal, reg_ctx = reg.value
    reg_uids = _uids(reg_ctx)
    assert GOAL_CHOICE in reg_uids, "INSPIRED_BY_CHOICE neighbour should surface registry-sourced"
    assert GOAL_PRINCIPLE in reg_uids, "a principle that supports the goal is its neighbour"
    assert GOAL_NOISE not in reg_uids, "edge outside the registry must be filtered out"
    assert GOAL not in reg_uids, "origin must not leak into its own context"

    # Negative control: the bare GOAL_ACHIEVEMENT clause misses INSPIRED_BY_CHOICE.
    bare = await goals_rel.graph_intel.query_with_intent(
        domain=None, node_uid=GOAL, intent=GOALS_CONFIG.default_context_intent, depth=1
    )
    assert bare.is_ok, bare
    assert GOAL_CHOICE not in _uids(bare.value), (
        "INSPIRED_BY_CHOICE is absent from the hard-coded GOAL_ACHIEVEMENT clause — the bare "
        "path must miss it, which is exactly what registry-sourcing fixes"
    )


@pytest.mark.asyncio
async def test_habits_registry_sourced_through_get_with_context(
    neo4j_driver, habits_rel, clean_neo4j
):
    """A habit's registry edge (SUPPORTS_GOAL) surfaces via get_with_context; noise filtered."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (HABIT, "Habit", "habit"),
            (HABIT_GOAL, "Goal", "goal"),
            (HABIT_NOISE, "Habit", "habit"),
        ]:
            # The origin is converted to a domain model by get_with_context; Habit is
            # user-owned and requires a user_uid (the neighbours are returned as raw nodes).
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', user_uid:'conv2b_user', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (h{uid:$h}),(g{uid:$g}) CREATE (h)-[:SUPPORTS_GOAL]->(g)", h=HABIT, g=HABIT_GOAL
        )
        await s.run(
            "MATCH (h{uid:$h}),(n{uid:$n}) CREATE (h)-[:NOISE_LINK]->(n)", h=HABIT, n=HABIT_NOISE
        )

    # SUPPORTS_GOAL is a registry edge but is absent from the hard-coded PRACTICE clause.
    assert "SUPPORTS_GOAL" in HABITS_CONFIG.cross_domain_relationship_types
    assert "SUPPORTS_GOAL" not in {"PRACTICES", "REINFORCES", "APPLIES_KNOWLEDGE"}
    assert HABITS_CONFIG.default_context_intent.value == "practice"

    reg = await habits_rel.get_with_context(HABIT, depth=1)
    assert reg.is_ok, reg
    _habit, reg_ctx = reg.value
    reg_uids = _uids(reg_ctx)
    assert HABIT_GOAL in reg_uids, "SUPPORTS_GOAL neighbour should surface registry-sourced"
    assert HABIT_NOISE not in reg_uids, "edge outside the registry must be filtered out"
    assert HABIT not in reg_uids, "origin must not leak into its own context"

    bare = await habits_rel.graph_intel.query_with_intent(
        domain=None, node_uid=HABIT, intent=HABITS_CONFIG.default_context_intent, depth=1
    )
    assert bare.is_ok, bare
    assert HABIT_GOAL not in _uids(bare.value), (
        "SUPPORTS_GOAL is absent from the hard-coded PRACTICE clause — the bare path must miss it"
    )
