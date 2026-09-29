"""A lateral write names the endpoint that is missing — the target as the target.

``LateralRelationshipBackend.check_entities_exist`` counts each endpoint. As two
plain ``MATCH`` clauses the query would yield no row whenever either node is
absent, zeroing BOTH counts, and the service would blame the source for a
missing target — so each count must stand on its own. Real Neo4j, because the
property lives in the query's row semantics, which a mocked backend would simply
restate.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import ErrorCategory

pytestmark = pytest.mark.asyncio(loop_scope="session")

PRESENT_UID = "goal_existence_present"
ABSENT_UID = "goal_existence_absent"
OTHER_ABSENT_UID = "goal_existence_absent_2"


@pytest.fixture
def service(neo4j_driver) -> LateralRelationshipService:
    """The real service over the real backend — nothing stubbed."""
    return LateralRelationshipService(
        backend=LateralRelationshipBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )


@pytest_asyncio.fixture(loop_scope="session")
async def one_goal(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Goal {uid: $uid, title: 'Present', entity_type: 'goal',"
            " status: 'active'})",
            uid=PRESENT_UID,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity {uid: $uid}) DETACH DELETE n", uid=PRESENT_UID)


@pytest.mark.integration
@pytest.mark.usefixtures("one_goal")
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
