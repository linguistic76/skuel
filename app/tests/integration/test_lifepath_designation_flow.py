"""
Integration tests for LifePath designation CRUD (testcontainer Neo4j).

Exercises LifePathCoreService + LifePathBackend against a real graph:
vision persistence on the User node, the ULTIMATE_PATH designation edge
with its entity_type promotion (learning_path → life_path), re-designation
reverting the previous path, alignment-score writes on the edge, and the
daily ALIGNMENT_SNAPSHOT trend history.

These paths were previously untested at the service layer (only route-level
mocks existed) — the designation Cypher does OPTIONAL MATCH + SET + DELETE
in one statement, which only a real graph can prove correct.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.lifepath_backend import LifePathBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.principle_enums import AlignmentLevel
from core.services.lifepath.lifepath_core_service import LifePathCoreService
from core.utils.result_simplified import ErrorCategory

pytestmark = pytest.mark.asyncio(loop_scope="session")

_USER_UID = "user_test_lifepath_designation"
_LP_A = "lp.test.designation.alpha"
_LP_B = "lp.test.designation.beta"


@pytest_asyncio.fixture(loop_scope="session")
async def core_service(neo4j_driver) -> LifePathCoreService:
    """Real backend, no LP-service validation (backend behavior under test)."""
    backend = LifePathBackend(Neo4jQueryExecutor(neo4j_driver))
    return LifePathCoreService(backend=backend, lp_service=None)


@pytest_asyncio.fixture(loop_scope="session")
async def designation_graph(neo4j_driver):
    """Fresh User + two LearningPaths per test; full cleanup after."""
    async with neo4j_driver.session() as session:
        # Reset any residue from a previous test in this module first
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[_USER_UID, _LP_A, _LP_B],
        )
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.title = $uid",
            uid=_USER_UID,
        )
        for lp_uid, title in ((_LP_A, "Designation LP Alpha"), (_LP_B, "Designation LP Beta")):
            await session.run(
                """
                MERGE (lp:Entity:LearningPath {uid: $uid})
                SET lp.title = $title,
                    lp.entity_type = 'learning_path',
                    lp.status = 'active'
                """,
                uid=lp_uid,
                title=title,
            )

    yield {"user_uid": _USER_UID, "lp_a": _LP_A, "lp_b": _LP_B}

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[_USER_UID, _LP_A, _LP_B],
        )


async def _entity_type_of(neo4j_driver, uid: str) -> str | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN n.entity_type AS et", uid=uid
        )
        record = await result.single()
        return record["et"] if record else None


async def _ultimate_path_targets(neo4j_driver) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $uid})-[:ULTIMATE_PATH]->(lp) RETURN lp.uid AS uid",
            uid=_USER_UID,
        )
        return [r["uid"] async for r in result]


class TestVisionPersistence:
    async def test_unknown_user_has_no_designation(self, core_service, designation_graph):
        result = await core_service.get_designation("user_does_not_exist_anywhere")

        assert result.is_ok
        assert result.value is None

    async def test_user_without_vision_or_designation_returns_none(
        self, core_service, designation_graph
    ):
        result = await core_service.get_designation(_USER_UID)

        assert result.is_ok
        assert result.value is None

    async def test_save_vision_round_trip(self, core_service, designation_graph):
        saved = await core_service.save_vision(
            _USER_UID,
            "I want to become a mindful technical leader",
            ["mindfulness", "leadership"],
        )
        assert saved.is_ok
        assert saved.value.has_vision
        assert not saved.value.has_designation

        fetched = await core_service.get_designation(_USER_UID)

        assert fetched.is_ok
        designation = fetched.value
        assert designation is not None
        assert designation.vision_statement == "I want to become a mindful technical leader"
        assert designation.vision_themes == ("mindfulness", "leadership")
        assert designation.has_vision
        assert not designation.has_designation
        # The backend persists ISO strings; the service must hand back datetime
        # (get_full_status calls .isoformat() on this field)
        assert isinstance(designation.vision_captured_at, datetime)

    async def test_save_vision_for_unknown_user_is_not_found(self, core_service, designation_graph):
        result = await core_service.save_vision("user_ghost", "some long enough vision", [])

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND


class TestDesignation:
    async def test_designate_creates_the_edge_and_leaves_the_node_alone(
        self, core_service, designation_graph, neo4j_driver
    ):
        """The ULTIMATE_PATH edge IS the designation.

        This used to also assert the node's ``entity_type`` was promoted to
        ``'life_path'`` in place. That promotion left the node's
        ``:LearningPath`` label saying one thing and its discriminator another,
        which made every LP-service read of a designated path fail and the
        alignment payload report the title as "Unknown" (LIFEPATH_ALIGNMENT_DEBT
        item 2).
        """
        result = await core_service.designate_life_path(_USER_UID, _LP_A)

        assert result.is_ok
        assert result.value.life_path_uid == _LP_A
        assert result.value.designated_at is not None

        assert await _ultimate_path_targets(neo4j_driver) == [_LP_A]
        assert await _entity_type_of(neo4j_driver, _LP_A) == "learning_path", (
            "designation mutated the node — label and discriminator now disagree"
        )

        fetched = await core_service.get_designation(_USER_UID)
        assert fetched.is_ok and fetched.value is not None
        assert fetched.value.has_designation
        assert fetched.value.life_path_uid == _LP_A
        assert fetched.value.alignment_score == pytest.approx(0.0)

    async def test_redesignation_moves_the_edge(
        self, core_service, designation_graph, neo4j_driver
    ):
        """One life path per user; neither node is touched by the move.

        There is no longer a demotion to get wrong: the previous path was never
        promoted, so re-designating cannot leave it half-reverted.
        """
        assert (await core_service.designate_life_path(_USER_UID, _LP_A)).is_ok

        result = await core_service.designate_life_path(_USER_UID, _LP_B)

        assert result.is_ok
        # Exactly one designation, pointing at the new path
        assert await _ultimate_path_targets(neo4j_driver) == [_LP_B]
        # Both nodes are ordinary LearningPaths throughout
        assert await _entity_type_of(neo4j_driver, _LP_A) == "learning_path"
        assert await _entity_type_of(neo4j_driver, _LP_B) == "learning_path"

    async def test_designate_nonexistent_lp_is_not_found(self, core_service, designation_graph):
        result = await core_service.designate_life_path(_USER_UID, "lp.test.designation.ghost")

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND

    async def test_remove_designation_reverts_but_keeps_vision(
        self, core_service, designation_graph, neo4j_driver
    ):
        assert (
            await core_service.save_vision(_USER_UID, "a vision worth keeping", ["mastery"])
        ).is_ok
        assert (await core_service.designate_life_path(_USER_UID, _LP_A)).is_ok

        removed = await core_service.remove_designation(_USER_UID)

        assert removed.is_ok
        assert removed.value is True
        assert await _ultimate_path_targets(neo4j_driver) == []
        assert await _entity_type_of(neo4j_driver, _LP_A) == "learning_path"

        # Vision survives designation removal
        fetched = await core_service.get_designation(_USER_UID)
        assert fetched.is_ok and fetched.value is not None
        assert fetched.value.vision_statement == "a vision worth keeping"
        assert not fetched.value.has_designation

    async def test_remove_designation_without_one_returns_false(
        self, core_service, designation_graph
    ):
        result = await core_service.remove_designation(_USER_UID)

        assert result.is_ok
        assert result.value is False


class TestAlignmentScoreAndSnapshots:
    async def test_update_alignment_score_writes_edge_and_snapshot(
        self, core_service, designation_graph, neo4j_driver
    ):
        assert (await core_service.designate_life_path(_USER_UID, _LP_A)).is_ok

        result = await core_service.update_alignment_score(
            _USER_UID,
            alignment_score=0.62,
            dimension_scores={
                "knowledge": 0.5,
                "activity": 0.7,
                "goal": 0.6,
                "principle": 0.65,
                "momentum": 0.7,
            },
        )

        assert result.is_ok
        assert result.value is True

        async with neo4j_driver.session() as session:
            edge = await session.run(
                """
                MATCH (:User {uid: $uid})-[r:ULTIMATE_PATH]->(:Entity {uid: $lp})
                RETURN r.alignment_score AS score, r.alignment_level AS level,
                       r.knowledge_alignment AS knowledge, r.momentum AS momentum
                """,
                uid=_USER_UID,
                lp=_LP_A,
            )
            record = await edge.single()
        assert record is not None
        assert record["score"] == pytest.approx(0.62)
        assert record["level"] == AlignmentLevel.from_score(0.62).value
        assert record["knowledge"] == pytest.approx(0.5)
        assert record["momentum"] == pytest.approx(0.7)

        # get_designation reads the score back from the edge
        fetched = await core_service.get_designation(_USER_UID)
        assert fetched.is_ok and fetched.value is not None
        assert fetched.value.alignment_score == pytest.approx(0.62)
        assert fetched.value.alignment_level == AlignmentLevel.from_score(0.62)

    async def test_snapshot_is_idempotent_per_day(
        self, core_service, designation_graph, neo4j_driver
    ):
        assert (await core_service.designate_life_path(_USER_UID, _LP_A)).is_ok

        assert (await core_service.update_alignment_score(_USER_UID, 0.4)).is_ok
        assert (await core_service.update_alignment_score(_USER_UID, 0.55)).is_ok

        async with neo4j_driver.session() as session:
            result = await session.run(
                """
                MATCH (:User {uid: $uid})-[r:ALIGNMENT_SNAPSHOT]->(:Entity {uid: $lp})
                RETURN count(r) AS c, collect(r.score) AS scores
                """,
                uid=_USER_UID,
                lp=_LP_A,
            )
            record = await result.single()
        assert record["c"] == 1, "same-day snapshots must MERGE, not accumulate"
        assert record["scores"] == [pytest.approx(0.55)], "snapshot keeps the latest score"

    async def test_update_alignment_score_without_designation_returns_false(
        self, core_service, designation_graph
    ):
        result = await core_service.update_alignment_score(_USER_UID, 0.5)

        assert result.is_ok
        assert result.value is False

    async def test_trend_data_windows_and_orders_newest_first(
        self, core_service, designation_graph, neo4j_driver
    ):
        assert (await core_service.designate_life_path(_USER_UID, _LP_A)).is_ok
        assert (await core_service.update_alignment_score(_USER_UID, 0.7)).is_ok

        # Seed an older snapshot directly (the service can only write "today")
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $uid})-[:ULTIMATE_PATH]->(lp:Entity {uid: $lp})
                MERGE (u)-[r:ALIGNMENT_SNAPSHOT {date: date() - duration({days: 10})}]->(lp)
                SET r.score = 0.3, r.recorded_at = datetime() - duration({days: 10})
                """,
                uid=_USER_UID,
                lp=_LP_A,
            )

        wide = await core_service.get_alignment_trend_data(_USER_UID, days=31)
        assert wide.is_ok
        assert [pytest.approx(s["score"]) for s in wide.value] == [0.7, 0.3]

        narrow = await core_service.get_alignment_trend_data(_USER_UID, days=3)
        assert narrow.is_ok
        assert [pytest.approx(s["score"]) for s in narrow.value] == [0.7]
