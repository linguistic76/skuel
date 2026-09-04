"""Vault door: a task file's goal link lands as BOTH the edge and the property.

Drives the production path (directory sync, smart mode) against a real Neo4j. Before
this, ``connections.fulfills_goal:`` wrote ``(Task)-[:FULFILLS_GOAL]->(Goal)`` and nothing
else — the node column ``fulfills_goal_uid`` stayed NULL, so every in-hand reader (the
relevance scorer, the completion → goal-progress cascade, ``get_tasks_for_goal`` behind
the goal Gantt) saw a vault task as goal-less while the graph readers saw its goal. The
invariant pinned here: property == edge target, wherever both exist — and when the link
is removed from the file, BOTH halves go on the next sync.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.ingestion.types import IncrementalStats

_MARK = "zzzgoalparity"
_USER = f"user_{_MARK}"
_GOAL = f"goal.{_MARK}.ship"
_TASK = f"task.{_MARK}.one"


def _goal_file(vault: Path) -> Path:
    path = vault / "ship.md"
    path.write_text(
        f"---\ntype: goal\nuid: {_GOAL}\ntitle: Ship the parity\nuser_uid: {_USER}\n---\nBody.\n"
    )
    return path


def _task_file(
    vault: Path, *, connection: list[str] | None = None, bare_property: str | None = None
) -> Path:
    lines = ["type: task", f"uid: {_TASK}", "title: Write the parity test", f"user_uid: {_USER}"]
    if bare_property:
        lines.append(f"fulfills_goal_uid: {bare_property}")
    if connection is not None:
        lines.append("connections:")
        lines.append("  fulfills_goal:")
        lines.extend(f"    - {uid}" for uid in connection)
    path = vault / "one.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
    return path


async def _edge_targets(neo4j_driver) -> list[str]:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (t {uid: $t})-[:FULFILLS_GOAL]->(g) RETURN collect(g.uid) AS uids", {"t": _TASK}
        )
        record = await res.single()
        return record["uids"]


async def _property(neo4j_driver) -> Any:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (t {uid: $t}) RETURN t.fulfills_goal_uid AS goal", {"t": _TASK}
        )
        record = await res.single()
        assert record is not None, "the task was not ingested"
        return record["goal"]


async def _sync(service, vault: Path) -> IncrementalStats:
    result = await service.ingest_directory(vault, ingestion_mode="smart")
    assert result.is_ok, f"sync failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert not stats.errors, f"sync errors: {stats.errors}"
    return stats


@pytest_asyncio.fixture
async def parity_service(neo4j_driver):
    executor = Neo4jQueryExecutor(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", {"uid": _USER}
        )
    service = make_unified_ingestion_service(
        driver=neo4j_driver, ingestion_backend=IngestionBackend(executor=executor)
    )
    yield service
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid CONTAINS $mark DETACH DELETE n", {"mark": _MARK}
        )
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid CONTAINS $mark DELETE s",
            {"mark": _MARK},
        )
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", {"uid": _USER})


@pytest.mark.integration
class TestVaultTaskGoalLinkParity:
    async def test_the_connection_writes_the_edge_and_stamps_the_property(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_file(vault)
        _task_file(vault, connection=[_GOAL])

        await _sync(parity_service, vault)

        assert await _edge_targets(neo4j_driver) == [_GOAL]
        assert await _property(neo4j_driver) == _GOAL, (
            "the vault door wrote the FULFILLS_GOAL edge and left fulfills_goal_uid NULL — "
            "every in-hand reader sees this task as goal-less"
        )

    async def test_removing_the_link_clears_both_halves_on_the_next_sync(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_file(vault)
        _task_file(vault, connection=[_GOAL])
        await _sync(parity_service, vault)
        assert await _property(neo4j_driver) == _GOAL

        _task_file(vault, connection=None)
        await _sync(parity_service, vault)

        assert await _edge_targets(neo4j_driver) == [], "the dropped edge was not retracted"
        assert await _property(neo4j_driver) is None, (
            "the edge was retracted but the property still names the goal"
        )

    async def test_a_bare_property_spelling_still_gets_the_edge(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        """A file that authors the link as the column rather than the connection must
        reach the graph readers too."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_file(vault)
        _task_file(vault, bare_property=_GOAL)

        await _sync(parity_service, vault)

        assert await _property(neo4j_driver) == _GOAL
        assert await _edge_targets(neo4j_driver) == [_GOAL], (
            "fulfills_goal_uid authored as a property wrote no FULFILLS_GOAL edge"
        )
