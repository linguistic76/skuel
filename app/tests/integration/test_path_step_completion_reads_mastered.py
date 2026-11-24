"""A learner has completed a path step when they hold a MASTERED edge to it.

A step is shared curriculum: every learner on a path reads the same node, so its
completion is the learner's own edge to it, never a property on it. The curriculum
statement reads that edge in three places — each enrolled path's steps, the path's
completed count and progress, and each active step's prerequisites — and Askesis tells
the LLM the count. Two learners share one path here and have mastered different steps,
so each reading is checked against the other learner's.
"""

from __future__ import annotations

from typing import Any

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.askesis.grounding_projection import render_askesis_grounding
from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_builder import UserContextBuilder
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.usefixtures("held_run_clock")

_ONE = seed_user_uid("pscomplete_one")
_TWO = seed_user_uid("pscomplete_two")
_NONE = seed_user_uid("pscomplete_none")
_PATH = "lp.pscomplete.path"
_EMPTY_PATH = "lp.pscomplete.empty"
_FIRST = "ps.pscomplete.first"
_SECOND = "ps.pscomplete.second"
_THIRD = "ps.pscomplete.third"

_SEED = """
UNWIND $users AS user_uid
MERGE (u:User {uid: user_uid}) SET u.title = user_uid
WITH collect(u) AS users
CREATE (lp:Entity:LearningPath {uid: $path, entity_type: 'learning_path', title: 'Shared path'})
CREATE (empty:Entity:LearningPath {uid: $empty_path, entity_type: 'learning_path', title: 'Empty path'})
CREATE (s1:Entity:PathStep {uid: $first, entity_type: 'path_step', title: 'First'})
CREATE (s2:Entity:PathStep {uid: $second, entity_type: 'path_step', title: 'Second'})
CREATE (s3:Entity:PathStep {uid: $third, entity_type: 'path_step', title: 'Third'})
CREATE (lp)-[:HAS_STEP {sequence: 1}]->(s1)
CREATE (lp)-[:HAS_STEP {sequence: 2}]->(s2)
CREATE (lp)-[:HAS_STEP {sequence: 3}]->(s3)
CREATE (s3)-[:REQUIRES_STEP]->(s1)
CREATE (s3)-[:REQUIRES_STEP]->(s2)
WITH users, lp, empty, s1, s2, s3
UNWIND users AS u
CREATE (u)-[:ENROLLED_IN]->(lp)
CREATE (u)-[:ENROLLED_IN]->(empty)
CREATE (u)-[:IN_PROGRESS]->(s3)
"""

_MASTER = """
MATCH (u:User {uid: $user_uid}), (s:PathStep)
WHERE s.uid IN $steps
CREATE (u)-[:MASTERED {mastered_at: datetime($now), mastery_score: 1.0, confidence: 1.0, method: 'derived'}]->(s)
"""


@pytest.fixture
async def shared_path(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """One path, three learners: one mastered First, two mastered First and Second, one none.

    The first learner also marked Second as read: reading a step is not completing it.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            _SEED,
            users=[_ONE, _TWO, _NONE],
            path=_PATH,
            empty_path=_EMPTY_PATH,
            first=_FIRST,
            second=_SECOND,
            third=_THIRD,
        )
        await session.run(_MASTER, user_uid=_ONE, steps=[_FIRST], now="2026-01-01T00:00:00Z")
        await session.run(
            _MASTER, user_uid=_TWO, steps=[_FIRST, _SECOND], now="2026-01-01T00:00:00Z"
        )
        await session.run(
            "MATCH (u:User {uid: $user_uid}), (s:PathStep {uid: $step}) "
            "CREATE (u)-[:MARKED_AS_READ]->(s)",
            user_uid=_ONE,
            step=_SECOND,
        )


async def _context(driver: AsyncDriver, user_uid: UserUID) -> UserContext:
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(driver)))
    user = User(uid=user_uid, title=user_uid, email=f"{user_uid}@test.com")
    result = await builder.build_rich_user_context(user_uid, user)
    assert result.is_ok, result.error
    return result.value


def _path(
    context: UserContext, path_uid: str
) -> dict[str, Any]:  # boundary: a path's graph_context
    [graph_context] = [
        item["graph_context"]
        for item in context.enrolled_paths_rich
        if item["path"]["uid"] == path_uid
    ]
    return graph_context


def _steps(context: UserContext) -> dict[str, bool]:
    return {step["uid"]: step["completed"] for step in _path(context, _PATH)["steps"]}


def _prerequisites(context: UserContext) -> dict[str, bool]:
    [step] = [
        item["graph_context"]
        for item in context.active_path_steps_rich
        if item["step"]["uid"] == _THIRD
    ]
    return {row["uid"]: row["completed"] for row in step["prerequisite_steps"]}


@pytest.mark.asyncio
async def test_a_mastered_step_reads_completed_for_its_learner_only(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    one = await _context(neo4j_driver, _ONE)
    two = await _context(neo4j_driver, _TWO)

    assert _steps(one) == {_FIRST: True, _SECOND: False, _THIRD: False}
    assert _steps(two) == {_FIRST: True, _SECOND: True, _THIRD: False}


@pytest.mark.asyncio
async def test_a_paths_count_and_progress_are_this_learners_mastered_steps(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    one = _path(await _context(neo4j_driver, _ONE), _PATH)
    two = _path(await _context(neo4j_driver, _TWO), _PATH)

    assert (one["completed_steps"], one["total_steps"]) == (1, 3)
    assert one["progress_percentage"] == pytest.approx(100.0 / 3)
    assert (two["completed_steps"], two["total_steps"]) == (2, 3)
    assert two["progress_percentage"] == pytest.approx(200.0 / 3)


@pytest.mark.asyncio
async def test_a_prerequisite_step_reads_completed_only_for_the_learner_who_mastered_it(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    assert _prerequisites(await _context(neo4j_driver, _ONE)) == {_FIRST: True, _SECOND: False}
    assert _prerequisites(await _context(neo4j_driver, _TWO)) == {_FIRST: True, _SECOND: True}


@pytest.mark.asyncio
async def test_a_learner_who_mastered_nothing_reads_every_step_not_completed(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    context = await _context(neo4j_driver, _NONE)

    assert _steps(context) == {_FIRST: False, _SECOND: False, _THIRD: False}
    assert _prerequisites(context) == {_FIRST: False, _SECOND: False}
    path = _path(context, _PATH)
    assert (path["completed_steps"], path["progress_percentage"]) == (0, 0.0)


@pytest.mark.asyncio
async def test_a_path_with_no_steps_reads_nothing_completed(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    empty = _path(await _context(neo4j_driver, _TWO), _EMPTY_PATH)

    assert empty["steps"] == []
    assert (empty["total_steps"], empty["completed_steps"], empty["progress_percentage"]) == (
        0,
        0,
        0.0,
    )


@pytest.mark.asyncio
async def test_the_askesis_line_names_each_learners_own_count(
    neo4j_driver: AsyncDriver, shared_path: None
) -> None:
    one = render_askesis_grounding(await _context(neo4j_driver, _ONE))
    two = render_askesis_grounding(await _context(neo4j_driver, _TWO))

    assert "Shared path (1/3 steps)" in one
    assert "Shared path (2/3 steps)" in two
