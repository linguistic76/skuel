"""``paths_completed`` is the user's completed enrollments, read off the enrollment edges.

A learner's progress in a path lives on their ``(User)-[:ENROLLED_IN]->(LearningPath)``
edge, and the edge's ``status`` turns ``completed`` in the same write that records the
last Ku mastered (``record_enrollment_progress``). Counting those edges is the whole
figure, so it is proven here against the real writers: the enroll door, the progress
recount, and a repeat enroll on a path already finished.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

LEARNER = seed_user_uid("paths_completed")
OTHER = seed_user_uid("paths_other")

FINISHED = "lp.paths.finished"
UNDERWAY = "lp.paths.underway"
KU_MASTERED = "ku.paths.mastered"
KU_OPEN = "ku.paths.open"


@pytest.mark.asyncio
@pytest.mark.integration
class TestPathsCompleted:
    @pytest_asyncio.fixture
    async def graph(self, neo4j_driver, clean_neo4j):
        """Two paths: one whose only Ku both learners mastered, one with a Ku nobody has."""
        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                UNWIND [[$finished, $ku_mastered], [$underway, $ku_open]] AS pair
                MERGE (lp:Entity:LearningPath {uid: pair[0]})
                SET lp.entity_type = 'learning_path', lp.title = pair[0]
                MERGE (ku:Entity:Ku {uid: pair[1]})
                SET ku.entity_type = 'ku', ku.title = pair[1]
                MERGE (lp)-[:REQUIRES_KNOWLEDGE]->(ku)
                WITH 1 AS one LIMIT 1
                MATCH (ku:Ku {uid: $ku_mastered})
                UNWIND $learners AS learner
                MATCH (u:User {uid: learner})
                MERGE (u)-[:MASTERED {mastery_score: 0.9}]->(ku)
                """,
                finished=FINISHED,
                underway=UNDERWAY,
                ku_mastered=KU_MASTERED,
                ku_open=KU_OPEN,
                learners=[LEARNER, OTHER],
            )
            await result.consume()

    @pytest_asyncio.fixture
    async def doors(self, neo4j_driver):
        from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.pathways.learning_path import LearningPath

        return (
            build_production_backends(neo4j_driver)["users_backend"],
            LpBackend(
                neo4j_driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY
            ),
        )

    @pytest_asyncio.fixture
    async def service(self, neo4j_driver):
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
        from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

        return CrossDomainAnalyticsService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))

    async def _enroll_and_recount(self, doors, user_uid: str, lp_uid: str) -> None:
        users, paths = doors
        enrolled = await users.enroll_in_learning_path(user_uid, lp_uid)
        assert enrolled.is_ok, enrolled
        recorded = await paths.record_enrollment_progress(
            user_uid, lp_uid, datetime.now(UTC).isoformat()
        )
        assert recorded.is_ok and recorded.value, recorded

    async def _paths_completed(self, service, user_uid: str) -> int:
        result = await service.get_learning_velocity(user_uid, days_back=30)
        assert result.is_ok, result
        return result.value.paths_completed

    async def test_a_path_completed_by_the_progress_recount_is_counted(self, graph, doors, service):
        """The finished path counts; the one still underway does not."""
        await self._enroll_and_recount(doors, LEARNER, FINISHED)
        await self._enroll_and_recount(doors, LEARNER, UNDERWAY)

        assert await self._paths_completed(service, LEARNER) == 1

    async def test_another_learners_completions_do_not_leak(self, graph, doors, service):
        """Both learners finished the same path; each counts their own enrollment once."""
        await self._enroll_and_recount(doors, LEARNER, FINISHED)
        await self._enroll_and_recount(doors, OTHER, FINISHED)

        assert await self._paths_completed(service, LEARNER) == 1
        assert await self._paths_completed(service, OTHER) == 1

    async def test_enrolling_again_in_a_finished_path_keeps_it_completed(
        self, graph, doors, service
    ):
        """The list card offers Enroll on every path, including one already finished.

        A repeat enroll refreshes the enrollment's fields; it does not undo the
        completion the recount recorded, so the count stays where it was.
        """
        await self._enroll_and_recount(doors, LEARNER, FINISHED)
        assert await self._paths_completed(service, LEARNER) == 1, "positive control"

        users, _ = doors
        again = await users.enroll_in_learning_path(LEARNER, FINISHED)
        assert again.is_ok and again.value is False, "a repeat enroll, not a new one"

        assert await self._paths_completed(service, LEARNER) == 1

    async def test_a_learner_with_no_enrollment_has_completed_none(self, graph, service):
        assert await self._paths_completed(service, LEARNER) == 0
