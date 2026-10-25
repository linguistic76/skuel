"""A lateral write names the endpoint that is missing — the target as the target.

``LateralRelationshipBackend.check_entities_exist`` counts each endpoint. As two
plain ``MATCH`` clauses the query would yield no row whenever either node is
absent, zeroing BOTH counts, and the service would blame the source for a
missing target — so each count must stand on its own. Real Neo4j, because the
property lives in the query's row semantics, which a mocked backend would simply
restate.

Every write carries an ownership verifier. The one here admits the present
uids, so the existence check is what answers; an endpoint it refuses is named
exactly as a missing one is.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from core.models.enums import EntityType
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from core.utils.result_simplified import ErrorCategory
from tests.helpers.lateral_verifiers import CALLER, AdmitsAllBut
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

PRESENT_UID = "ku.existence.present"
ABSENT_UID = "ku.existence.absent"
OTHER_ABSENT_UID = "ku.existence.absent-2"
PRIVATE_UID = "task.existence-private"
VERIFIER = AdmitsAllBut(PRIVATE_UID)


@pytest.fixture
def service(neo4j_driver) -> LateralRelationshipService:
    """The real service over the real backend — nothing stubbed."""
    return LateralRelationshipService(
        backend=build_production_backends(neo4j_driver)["lateral_relationship_backend"]
    )


@pytest_asyncio.fixture(loop_scope="session")
async def one_ku(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Ku {uid: $uid, title: 'Present', entity_type: 'ku'})"
            " CREATE (:Entity:Task {uid: $private, title: 'Private', entity_type: 'task',"
            " user_uid: $user_existence_owner, status: 'active'})",
            uid=PRESENT_UID,
            private=PRIVATE_UID,
            user_existence_owner=seed_user_uid("existence_owner"),
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
            PRESENT_UID,
            ABSENT_UID,
            RelationshipName.BLOCKS,
            user_uid=CALLER,
            domain_service=VERIFIER,
        )

        error = result.expect_error()
        assert error.category == ErrorCategory.NOT_FOUND
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "target"

    async def test_missing_source_is_reported_as_the_source(
        self, service: LateralRelationshipService
    ) -> None:
        result = await service.create_lateral_relationship(
            ABSENT_UID,
            PRESENT_UID,
            RelationshipName.BLOCKS,
            user_uid=CALLER,
            domain_service=VERIFIER,
        )

        error = result.expect_error()
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "source"

    async def test_both_missing_names_the_source_first(
        self, service: LateralRelationshipService
    ) -> None:
        result = await service.create_lateral_relationship(
            ABSENT_UID,
            OTHER_ABSENT_UID,
            RelationshipName.BLOCKS,
            user_uid=CALLER,
            domain_service=VERIFIER,
        )

        error = result.expect_error()
        assert error.details["identifier"] == ABSENT_UID
        assert error.details["reason"] == "source"

    async def test_an_unowned_target_is_refused_as_a_missing_one(
        self, service: LateralRelationshipService
    ) -> None:
        refusing = AdmitsAllBut(PRIVATE_UID, ABSENT_UID)
        private = (
            await service.create_lateral_relationship(
                PRESENT_UID,
                PRIVATE_UID,
                RelationshipName.COMPLEMENTARY_TO,
                user_uid=CALLER,
                domain_service=refusing,
            )
        ).expect_error()
        missing = (
            await service.create_lateral_relationship(
                PRESENT_UID,
                ABSENT_UID,
                RelationshipName.COMPLEMENTARY_TO,
                user_uid=CALLER,
                domain_service=refusing,
            )
        ).expect_error()

        assert private.category == missing.category == ErrorCategory.NOT_FOUND
        assert private.message.replace(PRIVATE_UID, "<uid>") == missing.message.replace(
            ABSENT_UID, "<uid>"
        )
        assert private.details == {**missing.details, "identifier": PRIVATE_UID}


@pytest.mark.integration
@pytest.mark.usefixtures("one_ku")
class TestAnchorIsCounted:
    """``check_entity_exists`` — the anchor check of a read with no verifier."""

    @pytest.fixture
    def backend(self, neo4j_driver) -> LateralRelationshipBackend:
        return build_production_backends(neo4j_driver)["lateral_relationship_backend"]

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
