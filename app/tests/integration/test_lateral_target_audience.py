"""Lateral targets are filtered to the caller's audience (ADR-085 G4).

``LateralRelationshipService.get_lateral_relationships`` gates the ANCHOR (the
entity the caller asked about) via ``_verify_entity_access`` — on the shared
path, with no verifier, it must be curriculum — but a lateral edge can join
that anchor to ANY node, so the backend query ties each target to the caller
with the far-node rule (``build_far_node_clause``). These tests pin that rule on
the real backend against the real graph, from a curriculum anchor (the shape a
ku / ps / lp route reads): a target is returned to its owner whichever way the
graph spells ownership (``user_uid`` on an activity, ``owner_uid`` plus the
``OWNS`` edge on an Exercise), published ownerless (curriculum-shaped) targets
are returned to everyone, a draft is returned to nobody, and an anonymous read
keeps only the published ownerless ones (fail-closed).

Fixture shapes mirror the live writers: activity nodes persist ``user_uid`` as
a plain string alongside ``:Entity:<Domain>`` labels (the CRUD create door);
an Exercise persists ``owner_uid`` and is reached by ``(:User)-[:OWNS]->`` with
no ``user_uid`` (the exercise create door, ADR-086); curriculum nodes carry no
``user_uid`` at all (SHARED — ingestion drops the owner for curriculum types),
and a draft is marked ``publication_state: draft``; lateral edges carry an
ISO-string ``created_at`` (both the service and the edge-YAML ingestion door
stamp that shape).
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

ANCHOR_UID = "ku.aud.anchor"
MINE_UID = "goal_aud_mine"
FOREIGN_UID = "goal_aud_foreign"
CURRICULUM_UID = "ku_aud_shared"
DRAFT_UID = "ku_aud_draft"
FOREIGN_EXERCISE_UID = "ex_aud_foreign"
_FIXTURE_UIDS = [
    ANCHOR_UID,
    MINE_UID,
    FOREIGN_UID,
    CURRICULUM_UID,
    DRAFT_UID,
    FOREIGN_EXERCISE_UID,
]

OWNER = "user_test_123"
OTHER = "user_test_456"


@pytest.fixture
def service(neo4j_driver) -> LateralRelationshipService:
    """The real service over the real backend — nothing stubbed."""
    return LateralRelationshipService(
        backend=LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )


@pytest_asyncio.fixture(loop_scope="session")
async def lateral_neighbourhood(neo4j_driver):
    """A curriculum anchor with five RELATED_TO neighbours: two owned goals, the other
    user's Exercise (owned by edge and ``owner_uid``, no ``user_uid``), one published
    ownerless Ku and one draft Ku."""
    stamp = datetime.now().isoformat()
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (o:User {uid: $other})
            CREATE (a:Entity:Ku {uid: $anchor, title: 'Anchor concept', entity_type: 'ku'})
            CREATE (m:Entity:Goal {uid: $mine, title: 'My goal',
                                   entity_type: 'goal', user_uid: $owner})
            CREATE (f:Entity:Goal {uid: $foreign, title: 'Someone elses goal',
                                   entity_type: 'goal', user_uid: $other})
            CREATE (x:Entity:Exercise {uid: $foreign_exercise, title: 'Someone elses exercise',
                                       entity_type: 'exercise', scope: 'personal',
                                       owner_uid: $other})
            CREATE (o)-[:OWNS]->(x)
            CREATE (k:Entity {uid: $curriculum, title: 'Shared concept',
                              entity_type: 'ku'})
            CREATE (d:Entity:Ku {uid: $draft, title: 'Draft concept', entity_type: 'ku',
                                 publication_state: 'draft'})
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(m)
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(f)
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(x)
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(k)
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(d)
            """,
            anchor=ANCHOR_UID,
            mine=MINE_UID,
            foreign=FOREIGN_UID,
            foreign_exercise=FOREIGN_EXERCISE_UID,
            curriculum=CURRICULUM_UID,
            draft=DRAFT_UID,
            owner=OWNER,
            other=OTHER,
            stamp=stamp,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS
        )
        await session.run("MATCH (u:User {uid: $other}) DETACH DELETE u", other=OTHER)


def _target_uids(items) -> set[str]:
    return {item["target_uid"] for item in items}


class TestTargetAudience:
    async def test_a_reader_sees_their_own_and_ownerless_targets_but_not_foreign_ones(
        self, service, lateral_neighbourhood
    ):
        """A reader gets their own goal and the published curriculum; the foreign goal,
        the foreign exercise (owned by edge, not ``user_uid``) and the draft are withheld."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
            user_uid=OWNER,
        )

        assert not result.is_error, result.expect_error()
        # Positive controls (own goal and curriculum present) and the withhold
        # in one set — an over-broad filter that dropped everything would fail
        # here too.
        assert _target_uids(result.value) == {MINE_UID, CURRICULUM_UID}

    async def test_target_owner_sees_their_own_entity(self, service, lateral_neighbourhood):
        """The SAME read for the foreign goal's owner returns it, and their exercise
        through its ``OWNS`` edge, and withholds the first reader's — the filter is
        per-caller audience, not a blanket drop of owned targets."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
            user_uid=OTHER,
        )

        assert not result.is_error, result.expect_error()
        assert _target_uids(result.value) == {FOREIGN_UID, FOREIGN_EXERCISE_UID, CURRICULUM_UID}

    async def test_anonymous_read_keeps_only_ownerless_targets(
        self, service, lateral_neighbourhood
    ):
        """No user → fail-closed: every owned target and the draft drop, published
        curriculum survives."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
        )

        assert not result.is_error, result.expect_error()
        assert _target_uids(result.value) == {CURRICULUM_UID}
