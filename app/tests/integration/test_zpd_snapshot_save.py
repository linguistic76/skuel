"""A ZPD snapshot is kept on its user's history, and never writes a user.

``ZPDSnapshotBackend.save_snapshot`` refreshes the one ``:ZPDHistory`` a user holds.
For a uid no ``:User`` holds — an account erased between the event and its snapshot —
it writes nothing and answers not-found: no title-less ``:User`` is minted to hang the
history on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.zpd_snapshot_backend import ZPDSnapshotBackend
from core.models.type_hints import UserUID
from core.models.zpd.zpd_assessment import ZPDAssessment
from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_LEARNER = UserUID(seed_user_uid("zpd_snapshot_learner"))
_NOBODY = UserUID(seed_user_uid("zpd_snapshot_nobody"))


def _assessment() -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=["ku.test.zpd-snapshot-a"],
        proximal_zone=["ku.test.zpd-snapshot-b"],
        engaged_paths=[],
        readiness_scores={},
        blocking_gaps=[],
        behavioral_readiness=0.5,
    )


def _snapshots(driver: AsyncDriver) -> ZPDSnapshotBackend:
    backend = build_production_backends(driver)["zpd_snapshot_backend"]
    assert isinstance(backend, ZPDSnapshotBackend)
    return backend


async def _count(driver: AsyncDriver, query: str, uid: str) -> int:
    async with driver.session() as session:
        record = await (await session.run(query, uid=uid)).single()
    assert record is not None
    return int(record[0])


@pytest_asyncio.fixture(loop_scope="session")
async def graph(neo4j_driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = 'ZPD learner'", uid=_LEARNER)
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids OR n.user_uid IN $uids DETACH DELETE n",
            uids=[_LEARNER, _NOBODY],
        )


async def test_a_snapshot_lands_on_its_users_one_history(graph: AsyncDriver) -> None:
    backend = _snapshots(graph)

    assert (await backend.save_snapshot(_LEARNER, _assessment(), "test.first")).is_ok
    assert (await backend.save_snapshot(_LEARNER, _assessment(), "test.second")).is_ok

    assert (
        await _count(
            graph,
            "MATCH (:User {uid: $uid})-[:HAS_ZPD_HISTORY]->(h:ZPDHistory) "
            "RETURN count(h) * 10 + max(h.snapshot_count)",
            _LEARNER,
        )
        == 12
    )


async def test_a_snapshot_for_a_uid_no_user_holds_writes_nothing(graph: AsyncDriver) -> None:
    saved = await _snapshots(graph).save_snapshot(_NOBODY, _assessment(), "test.orphan")

    assert saved.is_error
    assert saved.expect_error().category == ErrorCategory.NOT_FOUND
    assert await _count(graph, "MATCH (u:User {uid: $uid}) RETURN count(u)", _NOBODY) == 0
    assert (
        await _count(graph, "MATCH (h:ZPDHistory {user_uid: $uid}) RETURN count(h)", _NOBODY) == 0
    )
