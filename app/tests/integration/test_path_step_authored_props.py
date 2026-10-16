"""A PathStep's door writes authored metadata, never learner state.

The shared step node is the same for every learner, so it holds what an author
sets (``mastery_threshold``) and no learner progress — a learner's mastery of a
step is their own ``(User)-[:MASTERED]->(PathStep)`` edge.

Driven through the one door that writes curriculum, the content-vault sync
(ADR-091), on the testcontainer: a standalone step file, and a learning path
file whose ``connections.contains_steps`` lists a step.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from tests.integration._activity_link_rig import sync_vault

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MARK = "zzzauthoredprops"
_STANDALONE = f"ps.{_MARK}.standalone"
_PATH_STEP = f"ps.{_MARK}.in-path"
_PATH = f"lp.{_MARK}.path"
_UIDS = [_STANDALONE, _PATH_STEP, _PATH]


async def _cleanup(driver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)
        await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.entity_uid IN $uids DETACH DELETE m", uids=_UIDS
        )


@pytest_asyncio.fixture(loop_scope="session")
async def authored_graph(neo4j_driver):
    await _cleanup(neo4j_driver)
    yield neo4j_driver
    await _cleanup(neo4j_driver)


def _step_file(vault: Path, name: str, uid: str, threshold: float) -> None:
    (vault / f"{name}.md").write_text(
        f"---\ntype: ps\nuid: {uid}\ntitle: Step {name}\nmastery_threshold: {threshold}\n"
        "---\nLearn it.\n"
    )


def _path_file(vault: Path, steps: list[str]) -> None:
    lines = ["type: lp", f"uid: {_PATH}", "title: Authored Props Path", "connections:"]
    lines.append("  contains_steps:")
    lines.extend(f"    - {step}" for step in steps)
    (vault / "path.md").write_text("---\n" + "\n".join(lines) + "\n---\nA path.\n")


async def _props(driver, uid: str) -> dict:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN properties(n) AS p", uid=uid
        )
        record = await result.single()
    assert record is not None, f"{uid} was not written"
    return dict(record["p"])


async def _has_step(driver, path_uid: str, step_uid: str) -> bool:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $lp})-[r:HAS_STEP]->(:Entity {uid: $ps}) RETURN count(r) AS n",
            lp=path_uid,
            ps=step_uid,
        )
        record = await result.single()
    return bool(record and record["n"] > 0)


async def test_standalone_step_holds_its_threshold_and_no_learner_mastery(
    authored_graph, tmp_path: Path
):
    _step_file(tmp_path, "standalone", _STANDALONE, 0.85)

    await sync_vault(authored_graph, tmp_path)

    props = await _props(authored_graph, _STANDALONE)
    assert props["mastery_threshold"] == 0.85
    assert "current_mastery" not in props


async def test_path_file_lists_its_step_which_holds_its_threshold(authored_graph, tmp_path: Path):
    _step_file(tmp_path, "in-path", _PATH_STEP, 0.9)
    _path_file(tmp_path, [_PATH_STEP])

    await sync_vault(authored_graph, tmp_path)

    assert await _has_step(authored_graph, _PATH, _PATH_STEP)
    props = await _props(authored_graph, _PATH_STEP)
    assert props["mastery_threshold"] == 0.9
    assert "current_mastery" not in props
