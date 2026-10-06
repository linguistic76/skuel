"""Vault door: a task file's goals land as CONTRIBUTES_TO_GOAL edges — one per target, nothing else.

Drives the production path (directory sync, smart mode) against a real Neo4j.
``connections.contributes_to_goal:`` is the registered field: each target becomes one
``(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)`` edge, and no node property names a goal — every
reader of a task's goals traverses the edges. A target dropped from the file loses its
edge on the next sync (the authored-edge diff), and only that one.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.ingestion.types import IncrementalStats

_MARK = "zzzgoalparity"
_USER = f"user_{_MARK}"
_GOAL = f"goal.{_MARK}.ship"
_OTHER_GOAL = f"goal.{_MARK}.grow"
_TASK = f"task.{_MARK}.one"


def _goal_files(vault: Path) -> None:
    for uid, slug in ((_GOAL, "ship"), (_OTHER_GOAL, "grow")):
        (vault / f"{slug}.md").write_text(
            f"---\ntype: goal\nuid: {uid}\ntitle: Goal {slug}\nuser_uid: {_USER}\n---\nBody.\n"
        )


def _task_file(vault: Path, *, connection: list[str] | None = None) -> Path:
    lines = ["type: task", f"uid: {_TASK}", "title: Write the parity test", f"user_uid: {_USER}"]
    if connection is not None:
        lines.append("connections:")
        lines.append("  contributes_to_goal:")
        lines.extend(f"    - {uid}" for uid in connection)
    path = vault / "one.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
    return path


async def _edge_targets(neo4j_driver) -> list[str]:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (t {uid: $t})-[:CONTRIBUTES_TO_GOAL]->(g) RETURN g.uid AS uid ORDER BY uid",
            {"t": _TASK},
        )
        return [record["uid"] async for record in res]


#: The node properties that would name a task's goal link — none may be written.
_GOAL_LINK_PROPERTIES = frozenset(
    {"fulfills_goal_uid", "contributes_to_goal_uid", "contributes_to_goal_uids"}
)


async def _goal_named_properties(neo4j_driver) -> list[str]:
    """The goal-link property keys on the task node."""
    async with neo4j_driver.session() as session:
        res = await session.run("MATCH (t {uid: $t}) RETURN keys(t) AS keys", {"t": _TASK})
        record = await res.single()
        assert record is not None, "the task was not ingested"
        return sorted(set(record["keys"]) & _GOAL_LINK_PROPERTIES)


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
class TestVaultTaskGoalLinks:
    async def test_two_targets_write_two_edges_and_no_column(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_files(vault)
        _task_file(vault, connection=[_GOAL, _OTHER_GOAL])

        await _sync(parity_service, vault)

        assert await _edge_targets(neo4j_driver) == sorted([_GOAL, _OTHER_GOAL])
        assert await _goal_named_properties(neo4j_driver) == [], (
            "a node property names a goal — the edges are the one record"
        )

    async def test_a_dropped_target_loses_only_its_edge(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_files(vault)
        _task_file(vault, connection=[_GOAL, _OTHER_GOAL])
        await _sync(parity_service, vault)

        _task_file(vault, connection=[_OTHER_GOAL])
        await _sync(parity_service, vault)

        assert await _edge_targets(neo4j_driver) == [_OTHER_GOAL]

    async def test_removing_every_target_retracts_every_edge(
        self, parity_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _goal_files(vault)
        _task_file(vault, connection=[_GOAL, _OTHER_GOAL])
        await _sync(parity_service, vault)

        _task_file(vault, connection=None)
        await _sync(parity_service, vault)

        assert await _edge_targets(neo4j_driver) == [], "a dropped edge was not retracted"
        assert await _goal_named_properties(neo4j_driver) == []
