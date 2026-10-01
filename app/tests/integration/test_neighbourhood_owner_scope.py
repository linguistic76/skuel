"""Real-Neo4j guard: an entity's graph neighbourhood holds its owner's nodes and shared
content — nobody else's.

Two users who each link their own entity to the same shared Ku are two hops apart, and
every edge on that path is one its own owner may write. The path-aware producer
(``build_domain_context_with_paths``) ties each node on a path to the centre's owner, so
neither the bucketed reader (``get_cross_domain_context``) nor the intent reader
(``query_with_intent`` → ``GraphContext``, which carries each node's full property map)
returns the other user's node — direct, two hops out, or as a stepping stone to
anything behind it.

Fixtures mirror the writers: a user-owned entity carries ``user_uid`` and its owner's
``OWNS`` edge. The three ownership spellings are each pinned on their own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_registry import (
    CHOICES_CONFIG,
    EVENTS_CONFIG,
    GOALS_CONFIG,
    HABITS_CONFIG,
    PRINCIPLES_CONFIG,
    TASKS_CONFIG,
    DomainRelationshipConfig,
)
from core.models.task.task import Task
from core.models.type_hints import Neo4jValue
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession

    from core.models.task.task_dto import TaskDTO
    from core.ports.base_protocols import BackendOperations

P = "nbo_"  # uid prefix for this module's fixture graph

ME = "user_test_123"  # User nodes the session's ``ensure_test_users`` keeps
THEM = "user_test_456"

CENTER = P + "center"  # mine — the entity whose neighbourhood is read
KU = P + "ku"  # shared: center, MINE_VIA_KU and THEIRS_VIA_KU all link it
MINE_VIA_KU = P + "mine_via_ku"  # mine, two hops out through the shared Ku
THEIRS_VIA_KU = P + "theirs_via_ku"  # theirs, two hops out through the shared Ku
THEIRS_DIRECT = P + "theirs_direct"  # theirs, linked straight to the center
MINE_BEHIND_THEIRS = P + "mine_behind_theirs"  # mine, reachable only through THEIRS_DIRECT
KU_BEHIND_THEIRS = P + "ku_behind_theirs"  # shared, reachable only through THEIRS_DIRECT

THEIR_WORDS = "private words of the other user"

# (registry config, domain label, entity_type, the domain's own edge to a Ku)
DOMAINS = [
    pytest.param(TASKS_CONFIG, "Task", "task", "APPLIES_KNOWLEDGE", id="tasks"),
    pytest.param(GOALS_CONFIG, "Goal", "goal", "REQUIRES_KNOWLEDGE", id="goals"),
    pytest.param(HABITS_CONFIG, "Habit", "habit", "REINFORCES_KNOWLEDGE", id="habits"),
    pytest.param(EVENTS_CONFIG, "Event", "event", "APPLIES_KNOWLEDGE", id="events"),
    pytest.param(CHOICES_CONFIG, "Choice", "choice", "INFORMED_BY_KNOWLEDGE", id="choices"),
    pytest.param(
        PRINCIPLES_CONFIG, "Principle", "principle", "GROUNDED_IN_KNOWLEDGE", id="principles"
    ),
]

# How a node says who owns it. The writers stamp a user-owned entity both ways
# ("entity"); the other three are each spelling on its own.
SPELLINGS = ["entity", "user_uid", "owner_uid", "owns_edge"]


@pytest.fixture
def backend(neo4j_driver: AsyncDriver) -> UniversalNeo4jBackend[Task]:
    """Any domain backend runs the producer — the statement takes its label as an argument."""
    return UniversalNeo4jBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)


@pytest.fixture
def graph_intel(neo4j_driver: AsyncDriver) -> GraphIntelligenceService:
    return GraphIntelligenceService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))


async def _create_owned(
    session: AsyncSession, uid: str, label: str, etype: str, owner: str, spelling: str = "entity"
) -> None:
    props: dict[str, Neo4jValue] = {
        "uid": uid,
        "entity_type": etype,
        "title": uid,
        "description": THEIR_WORDS if owner == THEM else "my own words",
        "status": "active",
    }
    if spelling in ("entity", "user_uid"):
        props["user_uid"] = owner
    if spelling == "owner_uid":
        props["owner_uid"] = owner
    await session.run(
        f"CREATE (n:Entity:{label}) SET n = $props, n.created_at = datetime()", props=props
    )
    if spelling in ("entity", "owns_edge"):
        await session.run(
            "MATCH (u:User {uid:$owner}), (n {uid:$uid}) CREATE (u)-[:OWNS]->(n)",
            owner=owner,
            uid=uid,
        )


async def _create_ku(session: AsyncSession, uid: str) -> None:
    await session.run(
        "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})", u=uid
    )


async def _link(session: AsyncSession, source: str, edge: str, target: str) -> None:
    await session.run(
        f"MATCH (a {{uid:$a}}), (b {{uid:$b}}) CREATE (a)-[:{edge} {{confidence:0.95}}]->(b)",
        a=source,
        b=target,
    )


async def _seed(
    neo4j_driver: AsyncDriver,
    label: str,
    etype: str,
    edge: str,
    *,
    center_spelling: str = "entity",
    neighbour_spelling: str = "entity",
) -> None:
    """The center, one shared Ku, and every way another user's node could be near it."""
    async with neo4j_driver.session() as s:
        await _create_owned(s, CENTER, label, etype, ME, center_spelling)
        await _create_owned(s, MINE_VIA_KU, label, etype, ME, neighbour_spelling)
        await _create_owned(s, MINE_BEHIND_THEIRS, label, etype, ME, neighbour_spelling)
        await _create_owned(s, THEIRS_VIA_KU, label, etype, THEM, neighbour_spelling)
        await _create_owned(s, THEIRS_DIRECT, label, etype, THEM, neighbour_spelling)
        await _create_ku(s, KU)
        await _create_ku(s, KU_BEHIND_THEIRS)
        for source, target in [
            (CENTER, KU),
            (MINE_VIA_KU, KU),
            (THEIRS_VIA_KU, KU),
            (CENTER, THEIRS_DIRECT),
            (MINE_BEHIND_THEIRS, THEIRS_DIRECT),
            (THEIRS_DIRECT, KU_BEHIND_THEIRS),
        ]:
            await _link(s, source, edge, target)


async def _raw_neighbourhood(
    backend: UniversalNeo4jBackend[Task], config: DomainRelationshipConfig
) -> set[str]:
    """The producer's rows for the center, read as the bucketed reader reads them."""
    result = await backend.get_domain_context_raw(
        entity_uid=CENTER,
        entity_label=config.entity_label,
        relationship_types=config.cross_domain_relationship_types,
        depth=2,
        min_confidence=0.7,
        bidirectional=True,
    )
    assert result.is_ok, result
    return {row["uid"] for row in result.value}


@pytest.mark.asyncio
@pytest.mark.parametrize(("config", "label", "etype", "edge"), DOMAINS)
async def test_neighbourhood_is_the_owners_nodes_and_shared_content(
    neo4j_driver, backend, clean_neo4j, config, label, etype, edge
):
    """The shared Ku and my node behind it are in; their nodes, and anything reachable
    only through one of theirs, are out — in every activity domain's vocabulary."""
    await _seed(neo4j_driver, label, etype, edge)

    assert await _raw_neighbourhood(backend, config) == {KU, MINE_VIA_KU}

    relationships: UnifiedRelationshipService[BackendOperations[Task], Task, TaskDTO] = (
        UnifiedRelationshipService(backend=backend, config=config, graph_intel=None)
    )
    bucketed = await relationships.get_cross_domain_context(CENTER, depth=2, min_confidence=0.7)
    assert bucketed.is_ok, bucketed
    in_buckets = {
        entry["uid"]
        for entries in bucketed.value.values()
        if isinstance(entries, list)
        for entry in entries
    }
    assert KU in in_buckets
    assert in_buckets <= {KU, MINE_VIA_KU}


@pytest.mark.asyncio
@pytest.mark.parametrize("neighbour_spelling", SPELLINGS)
@pytest.mark.parametrize("center_spelling", SPELLINGS)
async def test_every_ownership_spelling_is_read(
    neo4j_driver, backend, clean_neo4j, center_spelling, neighbour_spelling
):
    """``user_uid``, ``owner_uid`` and the ``OWNS`` edge each tie a node to its owner —
    on the center and on the nodes around it."""
    await _seed(
        neo4j_driver,
        "Task",
        "task",
        "APPLIES_KNOWLEDGE",
        center_spelling=center_spelling,
        neighbour_spelling=neighbour_spelling,
    )

    assert await _raw_neighbourhood(backend, TASKS_CONFIG) == {KU, MINE_VIA_KU}


@pytest.mark.asyncio
async def test_intent_reader_carries_no_other_users_properties(
    neo4j_driver, graph_intel, clean_neo4j
):
    """Both intent lenses — the registry vocabulary and every edge type — return my
    nodes and shared content only. The every-edge lens also walks ``OWNS`` and the
    learner edges, where the other user's ``User`` node sits one hop past the Ku."""
    await _seed(neo4j_driver, "Task", "task", "APPLIES_KNOWLEDGE")
    async with neo4j_driver.session() as s:
        for user in (ME, THEM):
            await s.run(
                "MATCH (u:User {uid:$u}), (k {uid:$k}) CREATE (u)-[:VIEWED]->(k)", u=user, k=KU
            )

    registry = await graph_intel.query_with_intent(
        domain=Domain.TASKS,
        node_uid=CENTER,
        intent=TASKS_CONFIG.default_context_intent,
        depth=2,
        relationship_types=TASKS_CONFIG.cross_domain_relationship_types,
    )
    assert registry.is_ok, registry
    assert {n.uid for n in registry.value.all_nodes} == {KU, MINE_VIA_KU}
    assert registry.value.get_summary()["total_nodes"] == 2

    every_edge = await graph_intel.get_entity_context(CENTER, depth=2)
    assert every_edge.is_ok, every_edge
    reached = {n.uid for n in every_edge.value.all_nodes}
    # Mine, shared, and my own User node (CENTER <-OWNS- ME), which leads to all I own.
    assert reached == {KU, MINE_VIA_KU, MINE_BEHIND_THEIRS, ME}
    for lens in (registry.value, every_edge.value):
        assert all(n.properties.get("description") != THEIR_WORDS for n in lens.all_nodes)


@pytest.mark.asyncio
async def test_an_entity_shared_with_me_is_not_in_my_neighbourhood(
    neo4j_driver, graph_intel, clean_neo4j
):
    """A share link lets me open their entity; it does not make it part of what
    surrounds mine. The every-edge lens reaches it in two hops through my User node."""
    await _seed(neo4j_driver, "Task", "task", "APPLIES_KNOWLEDGE")
    async with neo4j_driver.session() as s:
        await s.run(
            "MATCH (u:User {uid:$me}), (n {uid:$n}) CREATE (u)-[:SHARES_WITH]->(n)",
            me=ME,
            n=THEIRS_VIA_KU,
        )

    every_edge = await graph_intel.get_entity_context(CENTER, depth=2)

    assert every_edge.is_ok, every_edge
    assert THEIRS_VIA_KU not in {n.uid for n in every_edge.value.all_nodes}


@pytest.mark.asyncio
async def test_shared_content_has_only_shared_content_around_it(
    neo4j_driver, graph_intel, clean_neo4j
):
    """A Ku is nobody's, and the reader is not told who is asking: its neighbourhood is
    the shared content around it — no user's entities, and no ``User`` node."""
    await _seed(neo4j_driver, "Task", "task", "APPLIES_KNOWLEDGE")
    step = P + "step"
    async with neo4j_driver.session() as s:
        await s.run(
            "CREATE (:Entity:PathStep {uid:$u, entity_type:'path_step', title:$u, "
            "created_at:datetime()})",
            u=step,
        )
        await _link(s, step, "USES_KU", KU)
        await s.run("MATCH (u:User {uid:$u}), (k {uid:$k}) CREATE (u)-[:VIEWED]->(k)", u=ME, k=KU)

    every_edge = await graph_intel.get_entity_context(KU, depth=2)

    assert every_edge.is_ok, every_edge
    assert {n.uid for n in every_edge.value.all_nodes} == {step}
