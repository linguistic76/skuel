"""Lateral targets are filtered to the caller's audience (ADR-085 G4).

``LateralRelationshipService.get_lateral_relationships`` verifies the ANCHOR
(the entity the caller asked about) via ``_verify_entity_access`` — but a
lateral edge can join that anchor to ANY node, and the backend query used to
return every target regardless of owner. These tests pin the closure on the
real backend against the real graph: owned targets are returned only to their
owner, ownerless (curriculum-shaped) targets are returned to everyone, and an
anonymous read keeps only the ownerless ones (fail-closed).

Fixture shapes mirror the live writers: activity nodes persist ``user_uid`` as
a plain string alongside ``:Entity:<Domain>`` labels (the CRUD create door);
curriculum nodes carry no ``user_uid`` at all (SHARED — ingestion drops the
owner for curriculum types); lateral edges carry an ISO-string ``created_at``
(both the service and the edge-YAML ingestion door stamp that shape).
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

ANCHOR_UID = "goal_aud_anchor"
FOREIGN_UID = "goal_aud_foreign"
CURRICULUM_UID = "ku_aud_shared"
_FIXTURE_UIDS = [ANCHOR_UID, FOREIGN_UID, CURRICULUM_UID]

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
    """An owned anchor with two RELATED_TO neighbours: one foreign, one ownerless."""
    stamp = datetime.now().isoformat()
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (a:Entity:Goal {uid: $anchor, title: 'My goal',
                                   entity_type: 'goal', user_uid: $owner})
            CREATE (f:Entity:Goal {uid: $foreign, title: 'Someone elses goal',
                                   entity_type: 'goal', user_uid: $other})
            CREATE (k:Entity {uid: $curriculum, title: 'Shared concept',
                              entity_type: 'ku'})
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(f)
            CREATE (a)-[:RELATED_TO {created_at: $stamp}]->(k)
            """,
            anchor=ANCHOR_UID,
            foreign=FOREIGN_UID,
            curriculum=CURRICULUM_UID,
            owner=OWNER,
            other=OTHER,
            stamp=stamp,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS
        )


def _target_uids(items) -> set[str]:
    return {item["target_uid"] for item in items}


class TestTargetAudience:
    async def test_owner_sees_ownerless_but_not_foreign_targets(
        self, service, lateral_neighbourhood
    ):
        """The anchor's owner gets curriculum targets; the foreign goal is withheld."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
            user_uid=OWNER,
        )

        assert not result.is_error, result.expect_error()
        # Positive control (curriculum present) and the withhold in one set —
        # an over-broad filter that dropped everything would fail here too.
        assert _target_uids(result.value) == {CURRICULUM_UID}

    async def test_target_owner_sees_their_own_entity(self, service, lateral_neighbourhood):
        """The SAME read for the foreign goal's owner returns it — the filter is
        per-caller audience, not a blanket drop of owned targets."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
            user_uid=OTHER,
        )

        assert not result.is_error, result.expect_error()
        assert _target_uids(result.value) == {FOREIGN_UID, CURRICULUM_UID}

    async def test_anonymous_read_keeps_only_ownerless_targets(
        self, service, lateral_neighbourhood
    ):
        """No user → fail-closed: every owned target drops, curriculum survives."""
        result = await service.get_lateral_relationships(
            ANCHOR_UID,
            relationship_types=[RelationshipName.RELATED_TO],
            direction="both",
        )

        assert not result.is_error, result.expect_error()
        assert _target_uids(result.value) == {CURRICULUM_UID}
