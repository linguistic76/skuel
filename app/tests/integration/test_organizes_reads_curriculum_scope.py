"""The PathStep ORGANIZES reads never return a user-owned entity.

The ORGANIZES edge joins any two entities and the PathStep API answers
unauthenticated callers, so a personal-vault ``moc: true`` UserEntry that
organizes a PathStep sits one hop from a public read. ``PsOrganizationService``
holds two guards — the subject must be a PathStep, and organizers / children /
roots are scoped to shared curriculum by ``entity_type`` — and this file pins
both on a live graph, beside the unscoped mixin read the owner-verified
``/gradebook/{uid}`` door still needs.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.services.ps.ps_core_service import PsCoreService
from core.services.ps.ps_organization_service import (
    SHARED_CURRICULUM_TYPES,
    PsOrganizationService,
)

pytestmark = pytest.mark.integration

PREFIX = "orgscope_"
PS_ROOT = f"{PREFIX}ps_root"
PS_CHILD = f"{PREFIX}ps_child"
PS_SIBLING = f"{PREFIX}ps_sibling"
KU_CHILD = f"{PREFIX}ku_child"
UE_MAP = f"{PREFIX}ue_map"  # a private personal-vault map that links curriculum
UE_LEAF = f"{PREFIX}ue_leaf"  # a private entry a curriculum root (contrived) organizes


@pytest_asyncio.fixture
async def graph(neo4j_driver) -> PsBackend:
    """A curriculum root beside a private map that organizes the same PathStep.

    Titles are chosen so the private map sorts FIRST by title — the ordering
    ``find_organizers`` uses — which is what would make it ``get_navigation``'s
    organizer if the scope were missing.
    """
    async with neo4j_driver.session() as session:
        await session.run(f"MATCH (n:Entity) WHERE n.uid STARTS WITH '{PREFIX}' DETACH DELETE n")
        await session.run(
            """
            CREATE (root:Entity:PathStep {uid: $ps_root, entity_type: 'path_step',
                                          title: 'Python Reference', status: 'active'})
            CREATE (child:Entity:PathStep {uid: $ps_child, entity_type: 'path_step',
                                           title: 'Python Basics', status: 'active'})
            CREATE (sib:Entity:PathStep {uid: $ps_sibling, entity_type: 'path_step',
                                         title: 'Python Syntax', status: 'active'})
            CREATE (ku:Entity:Ku {uid: $ku_child, entity_type: 'ku',
                                  title: 'Empathy', status: 'active'})
            CREATE (map:Entity:UserEntry {uid: $ue_map, entity_type: 'user_entry',
                                          title: 'AAA my private study map',
                                          user_uid: 'user_private', status: 'active'})
            CREATE (leaf:Entity:UserEntry {uid: $ue_leaf, entity_type: 'user_entry',
                                           title: 'private journal entry',
                                           user_uid: 'user_private', status: 'active'})
            CREATE (root)-[:ORGANIZES {order: 0}]->(child)
            CREATE (root)-[:ORGANIZES {order: 1}]->(sib)
            CREATE (root)-[:ORGANIZES {order: 2}]->(ku)
            CREATE (root)-[:ORGANIZES {order: 3}]->(leaf)
            CREATE (map)-[:ORGANIZES {order: 0}]->(child)
            CREATE (map)-[:ORGANIZES {order: 1}]->(ku)
            """,
            ps_root=PS_ROOT,
            ps_child=PS_CHILD,
            ps_sibling=PS_SIBLING,
            ku_child=KU_CHILD,
            ue_map=UE_MAP,
            ue_leaf=UE_LEAF,
        )
    yield PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    async with neo4j_driver.session() as session:
        await session.run(f"MATCH (n:Entity) WHERE n.uid STARTS WITH '{PREFIX}' DETACH DELETE n")


@pytest.fixture
def service(graph: PsBackend) -> PsOrganizationService:
    return PsOrganizationService(ps_core=PsCoreService(backend=graph), backend=graph)


# ── Guard 1: the subject must be a PathStep ──────────────────────────────────


@pytest.mark.asyncio
async def test_a_private_map_is_not_found_as_a_subject(service: PsOrganizationService) -> None:
    for read in (service.is_organizer, service.find_organizers, service.get_organized_children):
        result = await read(UE_MAP)
        assert result.is_error, read.__name__
        assert "not found" in str(result.error).lower(), read.__name__

    view = await service.get_organization_view(UE_MAP)
    assert view.is_error
    nav = await service.get_navigation(UE_MAP)
    assert nav.is_error


# ── Guard 2: the other end is shared curriculum ──────────────────────────────


@pytest.mark.asyncio
async def test_a_private_map_is_not_an_organizer_of_the_step_it_links(
    service: PsOrganizationService,
) -> None:
    result = await service.find_organizers(PS_CHILD)
    assert result.is_ok
    assert [o["uid"] for o in result.value] == [PS_ROOT]


@pytest.mark.asyncio
async def test_a_private_map_is_not_a_root_organizer(service: PsOrganizationService) -> None:
    result = await service.list_root_organizers(limit=100)
    assert result.is_ok
    uids = {r["uid"] for r in result.value}
    assert PS_ROOT in uids
    assert UE_MAP not in uids


@pytest.mark.asyncio
async def test_a_private_entry_is_not_a_child_of_a_curriculum_root(
    service: PsOrganizationService,
) -> None:
    result = await service.get_organized_children(PS_ROOT)
    assert result.is_ok
    assert [c["uid"] for c in result.value] == [PS_CHILD, PS_SIBLING, KU_CHILD]

    view = await service.get_organization_view(PS_ROOT, max_depth=2)
    assert view.is_ok
    assert [c.uid for c in view.value.children] == [PS_CHILD, PS_SIBLING, KU_CHILD]
    assert view.value.total_steps == 3


@pytest.mark.asyncio
async def test_navigation_ignores_the_private_map_that_would_sort_first(
    service: PsOrganizationService,
) -> None:
    """Without the scope the map ('AAA…') is the first organizer and navigation
    would be computed inside a private hierarchy; with it, the siblings come
    from the curriculum root."""
    nav = await service.get_navigation(PS_CHILD)
    assert nav.is_ok
    assert nav.value.prev_uid is None
    assert nav.value.next_uid == PS_SIBLING


# ── The unscoped mixin read the owner-verified door keeps ────────────────────


@pytest.mark.asyncio
async def test_the_unscoped_backend_read_still_sees_the_private_map(graph: PsBackend) -> None:
    """``UserEntryBackend`` shares the mixin and passes no scope: behind the
    owner-verified ``/gradebook/{uid}`` read, a map's children are any type."""
    unscoped = await graph.get_organized_children(UE_MAP)
    assert unscoped.is_ok
    assert [c["uid"] for c in unscoped.value] == [PS_CHILD, KU_CHILD]

    scoped = await graph.get_organized_children(UE_MAP, child_types=SHARED_CURRICULUM_TYPES)
    assert scoped.is_ok
    assert [c["uid"] for c in scoped.value] == [PS_CHILD, KU_CHILD]

    organizers = await graph.find_organizers(PS_CHILD)
    assert organizers.is_ok
    assert {o["uid"] for o in organizers.value} == {PS_ROOT, UE_MAP}

    roots = await graph.list_root_organizers(limit=100)
    assert roots.is_ok
    assert {PS_ROOT, UE_MAP} <= {r["uid"] for r in roots.value}
