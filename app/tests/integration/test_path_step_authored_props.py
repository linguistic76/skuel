"""A PathStep's create doors write authored metadata, never learner state.

The shared step node is the same for every learner, so it holds what an author
sets (``mastery_threshold``) and no learner progress — a learner's mastery of a
step is their own ``(User)-[:MASTERED]->(PathStep)`` edge. A LearningPath holds
no step difficulty: difficulty is each step's own field.

Driven through the real doors (``PsService.create_step``, ``LpService.create_path``,
``LpService.update_path``) on the testcontainer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio(loop_scope="session")

_USER = "user_ps_authored_props"
_STANDALONE = "ps_authored_props_standalone"
_PATH_STEP = "ps_authored_props_in_path"


async def _cleanup(session) -> None:
    await session.run(
        """
        MATCH (u:User {uid: $user})
        OPTIONAL MATCH (u)-[:HAS_PATH]->(p:Entity)
        OPTIONAL MATCH (p)-[:HAS_STEP]->(s:Entity)
        DETACH DELETE u, p, s
        """,
        user=_USER,
    )
    await session.run(
        "MATCH (s:Entity) WHERE s.uid IN $uids DETACH DELETE s", uids=[_STANDALONE, _PATH_STEP]
    )


@pytest_asyncio.fixture(loop_scope="session")
async def authored_graph(neo4j_driver):
    async with neo4j_driver.session() as session:
        await _cleanup(session)
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await _cleanup(session)


def _step(uid: str, threshold: float):
    from core.models.pathways.path_step import PathStep

    return PathStep(
        uid=uid, title=f"Step {uid}", intent="Learn it", sequence=0, mastery_threshold=threshold
    )


async def _props(driver, uid: str) -> dict:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN properties(n) AS p", uid=uid
        )
        record = await result.single()
    assert record is not None, f"{uid} was not written"
    return dict(record["p"])


async def test_standalone_step_holds_its_threshold_and_no_learner_mastery(services, authored_graph):
    created = await services.ps.create_step(_step(_STANDALONE, 0.85))
    assert created.is_ok, created

    props = await _props(authored_graph, _STANDALONE)
    assert props["mastery_threshold"] == 0.85
    assert "current_mastery" not in props


async def test_path_steps_hold_their_threshold_and_no_learner_mastery(services, authored_graph):
    created = await services.lp.create_path(
        user_uid=_USER,
        title="Authored Props Path",
        description="steps written through the LP door",
        steps=[_step(_PATH_STEP, 0.9)],
    )
    assert created.is_ok, created

    props = await _props(authored_graph, _PATH_STEP)
    assert props["mastery_threshold"] == 0.9
    assert "current_mastery" not in props


async def test_path_update_refuses_a_step_difficulty(services, authored_graph):
    created = await services.lp.create_path(
        user_uid=_USER, title="Authored Props Update", description="", steps=[]
    )
    assert created.is_ok, created
    path_uid = created.value.uid

    refused = await services.lp.update_path(path_uid, {"step_difficulty": "advanced"})

    assert refused.is_error
    assert "step_difficulty" not in await _props(authored_graph, path_uid)


async def test_path_update_still_writes_a_path_field(services, authored_graph):
    """Control: the same door writes a field the LearningPath carries."""
    created = await services.lp.create_path(
        user_uid=_USER, title="Authored Props Update Control", description="", steps=[]
    )
    assert created.is_ok, created
    path_uid = created.value.uid

    updated = await services.lp.update_path(path_uid, {"estimated_hours": 7.5})

    assert updated.is_ok, updated
    assert (await _props(authored_graph, path_uid))["estimated_hours"] == 7.5
