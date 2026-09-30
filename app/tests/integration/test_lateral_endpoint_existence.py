"""A lateral write names the endpoint that is missing — the target as the target.

``LateralRelationshipBackend.check_entities_exist`` counts each endpoint. As two
plain ``MATCH`` clauses the query would yield no row whenever either node is
absent, zeroing BOTH counts, and the service would blame the source for a
missing target — so each count must stand on its own. Real Neo4j, because the
property lives in the query's row semantics, which a mocked backend would simply
restate.

The service is called with no ownership verifier — the shared-content path,
which joins curriculum only — so the fixture is a Ku, and an endpoint of any
other kind is named exactly as a missing one is.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums import EntityType
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import ErrorCategory

pytestmark = pytest.mark.asyncio(loop_scope="session")

PRESENT_UID = "ku.existence.present"
ABSENT_UID = "ku.existence.absent"
OTHER_ABSENT_UID = "ku.existence.absent-2"
PRIVATE_UID = "task_existence_private"


@pytest.fixture
def service(neo4j_driver) -> LateralRelationshipService:
    """The real service over the real backend — nothing stubbed."""
    return LateralRelationshipService(
        backend=LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )


@pytest_asyncio.fixture(loop_scope="session")
async def one_ku(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Ku {uid: $uid, title: 'Present', entity_type: 'ku'})"
            " CREATE (:Entity:Task {uid: $private, title: 'Private', entity_type: 'task',"
            " user_uid: 'user_existence_owner', status: 'active'})",
            uid=PRESENT_UID,
            private=PRIVATE_UID,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[PRESENT_UID, PRIVATE_UID],
        )


@pytest.mark.integration
@pytest.mark.usefixtures("one_ku")
class TestMissingEndpointIsNamed:
    async def test_missing_target_is_reported_as_the_target(
        self, service: LateralRelationshipService
    ) -> None:
        result = await service.create_lateral_relationship(
            PRESENT_UID, ABSENT_UID, RelationshipName.BLOCKS
        )

        error = result.expect_error()
        assert error.category == ErrorCategory.NOT_FOUND
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "target"

    async def test_missing_source_is_reported_as_the_source(
        self, service: LateralRelationshipService
    ) -> None:
        result = await service.create_lateral_relationship(
            ABSENT_UID, PRESENT_UID, RelationshipName.BLOCKS
        )

        error = result.expect_error()
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "source"

    async def test_both_missing_names_the_source_first(
        self, service: LateralRelationshipService
    ) -> None:
        result = await service.create_lateral_relationship(
            ABSENT_UID, OTHER_ABSENT_UID, RelationshipName.BLOCKS
        )

        error = result.expect_error()
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "source"

    async def test_a_non_curriculum_target_is_named_as_a_missing_one(
        self, service: LateralRelationshipService
    ) -> None:
        private = (
            await service.create_lateral_relationship(
                PRESENT_UID, PRIVATE_UID, RelationshipName.COMPLEMENTARY_TO
            )
        ).expect_error()
        missing = (
            await service.create_lateral_relationship(
                PRESENT_UID, ABSENT_UID, RelationshipName.COMPLEMENTARY_TO
            )
        ).expect_error()

        assert private.category == missing.category == ErrorCategory.NOT_FOUND
        assert private.message.replace(PRIVATE_UID, "<uid>") == missing.message.replace(
            ABSENT_UID, "<uid>"
        )
        assert private.details["reason"] == missing.details["reason"] == "target"


@pytest.mark.integration
@pytest.mark.usefixtures("one_ku")
class TestAnchorIsCounted:
    """``check_entity_exists`` — the anchor check of a read with no verifier."""

    @pytest.fixture
    def backend(self, neo4j_driver) -> LateralRelationshipBackend:
        return LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))

    async def test_a_curriculum_anchor_counts_one(
        self, backend: LateralRelationshipBackend
    ) -> None:
        rows = (await backend.check_entity_exists(PRESENT_UID, {EntityType.KU})).value

        assert [row["entity_count"] for row in rows] == [1]

    async def test_a_missing_anchor_and_a_non_curriculum_one_both_count_zero(
        self, backend: LateralRelationshipBackend
    ) -> None:
        """One row each, so the service reads a count — never an absent row."""
        curriculum = {EntityType.KU, EntityType.PATH_STEP, EntityType.LEARNING_PATH}
        missing = (await backend.check_entity_exists(ABSENT_UID, curriculum)).value
        private = (await backend.check_entity_exists(PRIVATE_UID, curriculum)).value

        assert missing == private == [{"entity_count": 0}]

    async def test_no_kind_filter_counts_any_entity(
        self, backend: LateralRelationshipBackend
    ) -> None:
        rows = (await backend.check_entity_exists(PRIVATE_UID)).value

        assert [row["entity_count"] for row in rows] == [1]
