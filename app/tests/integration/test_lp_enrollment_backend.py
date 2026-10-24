"""
Integration tests for UserBackend Learning Path enrollment (testcontainer Neo4j).

Pins the phantom-label bug class (systems-review Arc B): enrollment queries
matched ``(lp:Lp {...})`` — a label that exists on no node (LearningPath nodes
are ``:Entity:LearningPath``) — so every enrollment write silently matched
nothing. These tests assert the ENROLLED_IN edge actually LANDS in the graph
(a passing call with zero edges is the #496 skip-field signature).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from core.utils.result_simplified import ErrorCategory
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_USER_UID = seed_user_uid("test_lp_enroll")
_LP_UID = "lp.test.enrollment-backend"


@pytest_asyncio.fixture(loop_scope="session")
async def enrollment_graph(neo4j_driver):
    """User + LearningPath nodes with production labels (:Entity:LearningPath)."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.title = $uid",
            uid=_USER_UID,
        )
        await session.run(
            """
            MERGE (lp:Entity:LearningPath {uid: $uid})
            SET lp.title = 'Enrollment Backend Test LP',
                lp.entity_type = 'learning_path',
                lp.status = 'active'
            """,
            uid=_LP_UID,
        )

    yield {"user_uid": _USER_UID, "lp_uid": _LP_UID}

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) DETACH DELETE u",
            uid=_USER_UID,
        )
        await session.run(
            "MATCH (lp:LearningPath {uid: $uid}) DETACH DELETE lp",
            uid=_LP_UID,
        )


async def _count_enrollments(neo4j_driver, status: str | None = None) -> int:
    query = """
    MATCH (:User {uid: $user_uid})-[r:ENROLLED_IN]->(:LearningPath {uid: $lp_uid})
    WHERE $status IS NULL OR r.status = $status
    RETURN count(r) AS c
    """
    async with neo4j_driver.session() as session:
        result = await session.run(query, user_uid=_USER_UID, lp_uid=_LP_UID, status=status)
        record = await result.single()
        return int(record["c"]) if record else 0


async def test_enroll_creates_enrolled_in_edge(neo4j_driver, enrollment_graph):
    """enroll_in_learning_path lands a real ENROLLED_IN edge on :LearningPath."""
    backend = build_production_backends(neo4j_driver)["users_backend"]

    result = await backend.enroll_in_learning_path(
        _USER_UID, _LP_UID, motivation_note="arc-b integration"
    )

    assert result.is_ok, f"Enrollment failed: {result.error}"
    assert result.value is True
    assert await _count_enrollments(neo4j_driver, status="active") == 1, (
        "ENROLLED_IN edge must actually exist in the graph — a passing call "
        "with zero edges is the phantom-label signature this test pins"
    )


async def test_enroll_is_idempotent(neo4j_driver, enrollment_graph):
    """MERGE semantics: enrolling twice leaves exactly one edge — and reports
    the transition once, so LearningPathStarted is published once."""
    backend = build_production_backends(neo4j_driver)["users_backend"]

    first = await backend.enroll_in_learning_path(_USER_UID, _LP_UID)
    second = await backend.enroll_in_learning_path(_USER_UID, _LP_UID)

    assert first.is_ok and second.is_ok
    assert (first.value, second.value) == (True, False)
    assert await _count_enrollments(neo4j_driver) == 1


async def test_enroll_nonexistent_lp_fails(neo4j_driver, enrollment_graph):
    """Enrolling in a missing LP returns an error Result, not silent success."""
    backend = build_production_backends(neo4j_driver)["users_backend"]

    result = await backend.enroll_in_learning_path(_USER_UID, "lp:test:does-not-exist")

    assert result.is_error, "Missing LP must surface as an error, not a silent no-op"
    assert result.expect_error().category == ErrorCategory.NOT_FOUND, (
        "Missing LP is a not-found, not a database outage"
    )


async def test_complete_learning_path_updates_enrollment(neo4j_driver, enrollment_graph):
    """complete_learning_path (same phantom-label bug) flips the edge to completed."""
    backend = build_production_backends(neo4j_driver)["users_backend"]

    enroll = await backend.enroll_in_learning_path(_USER_UID, _LP_UID)
    assert enroll.is_ok

    complete = await backend.complete_learning_path(_USER_UID, _LP_UID, completion_score=0.9)

    assert complete.is_ok, f"Completion failed: {complete.error}"
    assert await _count_enrollments(neo4j_driver, status="completed") == 1


async def test_a_repeat_enroll_keeps_a_completed_enrollment_completed(
    neo4j_driver, enrollment_graph
):
    """Enrolling again in a finished path refreshes the edge; it does not undo the finish.

    The pathways list card offers Enroll on every path, including one already
    completed, so this is reachable from the UI. The commitment fields are what
    a repeat enroll is for; the completion stays where the learner earned it.
    """
    backend = build_production_backends(neo4j_driver)["users_backend"]
    assert (await backend.enroll_in_learning_path(_USER_UID, _LP_UID)).is_ok
    assert (await backend.complete_learning_path(_USER_UID, _LP_UID)).is_ok

    again = await backend.enroll_in_learning_path(
        _USER_UID, _LP_UID, weekly_time_commitment=120, motivation_note="once more"
    )

    assert again.is_ok and again.value is False
    assert await _count_enrollments(neo4j_driver, status="completed") == 1
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:User {uid: $user_uid})-[r:ENROLLED_IN]->(:LearningPath {uid: $lp_uid})
            RETURN r.weekly_time_commitment AS minutes, r.motivation_note AS note
            """,
            user_uid=_USER_UID,
            lp_uid=_LP_UID,
        )
        record = await result.single()
    assert (record["minutes"], record["note"]) == (120, "once more"), "the refresh still lands"


async def test_enrollment_lifecycle_visible_to_readers(neo4j_driver, enrollment_graph):
    """Readers stay aligned with the writer across the enrollment lifecycle.

    Kody #498: query_active_learning_paths filtered on LP NODE status and
    query_completed_learning_paths / get_completed_learning_paths read a
    :COMPLETED edge no writer creates — so a completed LP stayed "active"
    forever and the completed readers were permanently empty. All four
    readers now read r.status on the ENROLLED_IN edge the writer maintains.
    """
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.user_progress_backend import UserProgressBackend

    backends = build_production_backends(neo4j_driver)
    user_backend = backends["users_backend"]
    adaptive = backends["ps_backend"]
    progress = UserProgressBackend(Neo4jQueryExecutor(neo4j_driver))

    async def active_uids() -> tuple[list[str], list[str]]:
        adaptive_res = await adaptive.query_active_learning_paths(_USER_UID)
        progress_res = await progress.get_active_learning_paths(_USER_UID)
        assert adaptive_res.is_ok and progress_res.is_ok
        # Tier 6: the backend returns typed LearningPath models, not raw records
        return (
            [lp.uid for lp in adaptive_res.value],
            list(progress_res.value[0]["active_paths"]) if progress_res.value else [],
        )

    async def completed_uids() -> tuple[list[str], list[str]]:
        adaptive_res = await adaptive.query_completed_learning_paths(_USER_UID)
        progress_res = await progress.get_completed_learning_paths(_USER_UID)
        assert adaptive_res.is_ok and progress_res.is_ok
        return (
            [str(r["lp_uid"]) for r in adaptive_res.value],
            list(progress_res.value[0]["completed_paths"]) if progress_res.value else [],
        )

    # Enrolled → visible as active, absent from completed
    assert (await user_backend.enroll_in_learning_path(_USER_UID, _LP_UID)).is_ok
    adaptive_active, progress_active = await active_uids()
    assert _LP_UID in adaptive_active and _LP_UID in progress_active
    adaptive_done, progress_done = await completed_uids()
    assert _LP_UID not in adaptive_done and _LP_UID not in progress_done

    # Completed → leaves active, appears in completed
    assert (await user_backend.complete_learning_path(_USER_UID, _LP_UID)).is_ok
    adaptive_active, progress_active = await active_uids()
    assert _LP_UID not in adaptive_active and _LP_UID not in progress_active
    adaptive_done, progress_done = await completed_uids()
    assert _LP_UID in adaptive_done and _LP_UID in progress_done
