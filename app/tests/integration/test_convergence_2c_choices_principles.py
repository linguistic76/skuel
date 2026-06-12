"""Real-Neo4j guard for Convergence Phase 1 (PR 2C): Choices + Principles onto mechanism B.

2C routes the Choices and Principles intelligence-service graph-context retrieval
(``get_with_context``, used by both the facade and the ``/api/<domain>/context``
route) through ``UnifiedRelationshipService.get_with_context`` — the
registry-sourced mechanism B the Tasks facade established in 2A (PR #225) and
Goals/Habits copied in 2B (PR #226). (The ``get_<domain>_with_context``
domain-named aliases were deleted in the tasks bloat campaign.)

These two domains gain the most: their ``default_context_intent`` is HIERARCHICAL
(``HAS_CHILD`` / ``PARENT_OF`` / ``CHILD_OF``), which surfaces almost nothing — a
Choice/Principle is rarely a tree node. Their real edges (AFFECTS_GOAL, GUIDES_GOAL,
INFORMED_BY_PRINCIPLE, …) live only in the registry, so registry-sourcing is the
headline win. Two things must hold:

1. **Delegation, no recursion.** The intelligence ``get_with_context`` must route
   to ``self.relationships`` (the shared mixin owns the real implementation).
   (Principles had no service-level override but inherited the EXPLORATORY loader.)
2. **Registry-sourced edges surface (live Neo4j).** Through the very method the mixins
   delegate to, a Choice/Principle surfaces a registry edge that the bare HIERARCHICAL
   clause omits, while a noise edge outside the registry is filtered out. The negative
   control proves the bare clause genuinely misses it.

See: /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.backends.activity_backends import (
    ChoicesBackend,
    PrinciplesBackend,
)
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.choice.choice import Choice
from core.models.enums.neo_labels import NeoLabel
from core.models.principle.principle import Principle
from core.models.relationship_registry import CHOICES_CONFIG, PRINCIPLES_CONFIG
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.principles.principles_intelligence_service import PrinciplesIntelligenceService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

P = "conv2c_"  # uid prefix for this module's fixture graph

# --- Choices fixture graph ---
CHOICE = P + "choice"
CHOICE_GOAL = P + "choice_goal"  # via AFFECTS_GOAL (registry edge, NOT in HIERARCHICAL clause)
CHOICE_NOISE = P + "choice_noise"  # via NOISE_LINK (outside the registry → filtered)

# --- Principles fixture graph ---
PRINCIPLE = P + "principle"
PRINCIPLE_GOAL = P + "principle_goal"  # via GUIDES_GOAL (registry edge, NOT in HIERARCHICAL clause)
PRINCIPLE_NOISE = P + "principle_noise"  # via NOISE_LINK (outside the registry → filtered)


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
async def test_choices_delegation_routes_to_mechanism_b_without_recursion():
    svc, rel = _intel_stub(ChoicesIntelligenceService)
    assert await svc.get_with_context("c", 2) == "MECHANISM_B"
    rel.get_with_context.assert_any_await("c", 2)


@pytest.mark.asyncio
async def test_principles_delegation_routes_to_mechanism_b_without_recursion():
    svc, rel = _intel_stub(PrinciplesIntelligenceService)
    assert await svc.get_with_context("p", 2) == "MECHANISM_B"
    rel.get_with_context.assert_any_await("p", 2)


@pytest.mark.asyncio
async def test_delegation_fails_cleanly_without_relationship_service():
    svc = ChoicesIntelligenceService.__new__(ChoicesIntelligenceService)
    svc.graph_intel = MagicMock()
    svc.logger = MagicMock()
    svc.relationships = None
    res = await svc.get_with_context("c")
    assert res.is_error, "missing relationship_service must be an error, not a recursion/crash"


# ============================================================================
# Registry-sourced traversal through mechanism B (live Neo4j)
# ============================================================================


@pytest.fixture
def choices_rel(neo4j_driver):
    """Choices UnifiedRelationshipService wired to a real graph_intel — mechanism B.

    Uses the REAL ChoicesBackend(entity_class=Choice) the app wires (see
    services_bootstrap/_backends.py), NOT a DTO-typed UniversalNeo4jBackend — so
    backend.get() returns a full Choice domain model. This faithfulness is load-bearing
    for the focal-entity-type assertion below (Codex P2 refutation).
    """
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = ChoicesBackend(neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY)
    return UnifiedRelationshipService(
        backend=backend, config=CHOICES_CONFIG, graph_intel=graph_intel
    )


@pytest.fixture
def principles_rel(neo4j_driver):
    """Principles UnifiedRelationshipService wired to a real graph_intel — mechanism B.

    Uses the REAL PrinciplesBackend(entity_class=Principle) (see _backends.py), so
    backend.get() returns a full Principle domain model — faithful to production.
    """
    graph_intel = GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))
    backend = PrinciplesBackend(
        neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
    )
    return UnifiedRelationshipService(
        backend=backend, config=PRINCIPLES_CONFIG, graph_intel=graph_intel
    )


@pytest.mark.asyncio
async def test_choices_registry_sourced_through_get_with_context(
    neo4j_driver, choices_rel, clean_neo4j
):
    """A choice's registry edge (AFFECTS_GOAL) surfaces via get_with_context; noise filtered."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (CHOICE, "Choice", "choice"),
            (CHOICE_GOAL, "Goal", "goal"),
            (CHOICE_NOISE, "Choice", "choice"),
        ]:
            # The origin is converted to a domain model by get_with_context; Choice is
            # user-owned and requires a user_uid (the neighbours are returned as raw nodes).
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', user_uid:'conv2c_user', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (c{uid:$c}),(g{uid:$g}) CREATE (c)-[:AFFECTS_GOAL]->(g)",
            c=CHOICE,
            g=CHOICE_GOAL,
        )
        await s.run(
            "MATCH (c{uid:$c}),(n{uid:$n}) CREATE (c)-[:NOISE_LINK]->(n)", c=CHOICE, n=CHOICE_NOISE
        )

    # AFFECTS_GOAL is a registry edge but is absent from the hard-coded HIERARCHICAL clause.
    assert "AFFECTS_GOAL" in CHOICES_CONFIG.cross_domain_relationship_types
    assert "AFFECTS_GOAL" not in {"HAS_CHILD", "PARENT_OF", "CHILD_OF"}
    assert CHOICES_CONFIG.default_context_intent.value == "hierarchical"

    # Mechanism B (intent=None → registry-sourced): the real edge surfaces, noise out.
    # get_with_context returns (entity, GraphContext) — the context is the second element.
    reg = await choices_rel.get_with_context(CHOICE, depth=1)
    assert reg.is_ok, reg
    _choice, reg_ctx = reg.value
    # Focal-entity shape (refutes Codex P2 on PR #227): CHOICES_CONFIG.model_class is
    # Entity, but the real ChoicesBackend returns a full Choice and
    # _context_to_domain_model's `isinstance(data, model_class)` early-return passes it
    # through unchanged — so no choice-specific fields are dropped. A base Entity would
    # fail this isinstance (Entity is NOT a Choice).
    assert isinstance(_choice, Choice), (
        f"mechanism B must preserve the full Choice domain model, got {type(_choice).__name__}"
    )
    reg_uids = _uids(reg_ctx)
    assert CHOICE_GOAL in reg_uids, "AFFECTS_GOAL neighbour should surface registry-sourced"
    assert CHOICE_NOISE not in reg_uids, "edge outside the registry must be filtered out"
    assert CHOICE not in reg_uids, "origin must not leak into its own context"

    # Negative control: the bare HIERARCHICAL clause misses AFFECTS_GOAL.
    bare = await choices_rel.graph_intel.query_with_intent(
        domain=None, node_uid=CHOICE, intent=CHOICES_CONFIG.default_context_intent, depth=1
    )
    assert bare.is_ok, bare
    assert CHOICE_GOAL not in _uids(bare.value), (
        "AFFECTS_GOAL is absent from the hard-coded HIERARCHICAL clause — the bare path "
        "must miss it, which is exactly what registry-sourcing fixes"
    )


@pytest.mark.asyncio
async def test_principles_registry_sourced_through_get_with_context(
    neo4j_driver, principles_rel, clean_neo4j
):
    """A principle's registry edge (GUIDES_GOAL) surfaces via get_with_context; noise filtered."""
    async with neo4j_driver.session() as s:
        for uid, label, etype in [
            (PRINCIPLE, "Principle", "principle"),
            (PRINCIPLE_GOAL, "Goal", "goal"),
            (PRINCIPLE_NOISE, "Principle", "principle"),
        ]:
            # The origin is converted to a domain model by get_with_context; Principle is
            # user-owned and requires a user_uid (the neighbours are returned as raw nodes).
            await s.run(
                f"CREATE (n:Entity:{label} {{uid:$u, entity_type:$t, title:$u, "
                f"status:'active', user_uid:'conv2c_user', created_at:datetime()}})",
                u=uid,
                t=etype,
            )
        await s.run(
            "MATCH (p{uid:$p}),(g{uid:$g}) CREATE (p)-[:GUIDES_GOAL]->(g)",
            p=PRINCIPLE,
            g=PRINCIPLE_GOAL,
        )
        await s.run(
            "MATCH (p{uid:$p}),(n{uid:$n}) CREATE (p)-[:NOISE_LINK]->(n)",
            p=PRINCIPLE,
            n=PRINCIPLE_NOISE,
        )

    # GUIDES_GOAL is a registry edge but is absent from the hard-coded HIERARCHICAL clause.
    assert "GUIDES_GOAL" in PRINCIPLES_CONFIG.cross_domain_relationship_types
    assert "GUIDES_GOAL" not in {"HAS_CHILD", "PARENT_OF", "CHILD_OF"}
    assert PRINCIPLES_CONFIG.default_context_intent.value == "hierarchical"

    reg = await principles_rel.get_with_context(PRINCIPLE, depth=1)
    assert reg.is_ok, reg
    _principle, reg_ctx = reg.value
    # Focal-entity shape (refutes Codex P2): PRINCIPLES_CONFIG.model_class is Entity, but
    # the real PrinciplesBackend returns a full Principle, preserved by the isinstance
    # early-return in _context_to_domain_model — no principle-specific fields dropped.
    assert isinstance(_principle, Principle), (
        f"mechanism B must preserve the full Principle domain model, got {type(_principle).__name__}"
    )
    reg_uids = _uids(reg_ctx)
    assert PRINCIPLE_GOAL in reg_uids, "GUIDES_GOAL neighbour should surface registry-sourced"
    assert PRINCIPLE_NOISE not in reg_uids, "edge outside the registry must be filtered out"
    assert PRINCIPLE not in reg_uids, "origin must not leak into its own context"

    bare = await principles_rel.graph_intel.query_with_intent(
        domain=None, node_uid=PRINCIPLE, intent=PRINCIPLES_CONFIG.default_context_intent, depth=1
    )
    assert bare.is_ok, bare
    assert PRINCIPLE_GOAL not in _uids(bare.value), (
        "GUIDES_GOAL is absent from the hard-coded HIERARCHICAL clause — the bare path must miss it"
    )
