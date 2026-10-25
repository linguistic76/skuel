"""The sync reports every node it wrote, split by what MERGE did.

A vault sync's "notes ingested" (``VaultSyncStats.entries_ingested``) is
``nodes_created + nodes_updated``, so a write onto a node that already exists
counts: a re-ingested edited file is one node updated, never nothing.

The first test drives the vault door in four stages. Stages 1 and 2 hold for a
counter that never reports an update; stage 3 refutes it, because it writes a
node without creating one.

1. New file                -> created 1, updated 0
2. Re-sync, file untouched -> created 0, updated 0   (the hash gate)
3. Edited file             -> created 0, updated 1
4. Force re-ingest         -> created 0, updated 1   (written although unchanged)

Stage 3 asserts the edit landed, so "updated 1" is pinned to a real write rather
than to a file that was merely re-read.

The second test reads the backend directly for what the vault door cannot stage in
one call: a node someone else owns, which the upsert refuses, is in neither count,
and a uid two rows name is one node.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.types import IncrementalStats
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

KU_UID = "ku.nodewrite-reporting"

# The backend test's tasks: one the owner already has, one new, one another user owns.
EXISTING_TASK = "task.nodewrite-existing"
NEW_TASK = "task.nodewrite-new"
FOREIGN_TASK = "task.nodewrite-foreign"
OTHER_OWNER = seed_user_uid("test_123")  # seeded by the ensure_test_users fixture

_FIXTURE_UIDS = [KU_UID, EXISTING_TASK, NEW_TASK, FOREIGN_TASK]

# The vault sync doors run "smart" (VaultReconciler.sync).
SYNC_MODE = "smart"


def _ku_file(title: str) -> str:
    return f"""---
type: ku
title: {title}
description: A node whose writes the sync reports
uid: {KU_UID}
domain: knowledge
---

Body for {KU_UID}.
"""


@pytest_asyncio.fixture(loop_scope="session")
async def node_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "node_write_vault"
    vault.mkdir()
    return vault


@pytest_asyncio.fixture(loop_scope="session")
async def node_ingestion_service(neo4j_driver: AsyncDriver):
    """Ingestion service with a backend — smart mode requires the tracker."""

    service = build_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=build_production_backends(neo4j_driver)["ingestion_backend"],
        default_user_uid=INGESTION_TEST_OWNER,
    )
    yield service
    await _delete_fixture_nodes(neo4j_driver)


async def _delete_fixture_nodes(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS)
        await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.file_path CONTAINS 'node_write_vault' DELETE m"
        )


async def _sync(service, vault: Path, *, force: bool = False) -> IncrementalStats:
    result = await service.ingest_directory(
        directory=vault,
        pattern="*",
        ingestion_mode=SYNC_MODE,
        force=force,
    )
    assert result.is_ok, result.error
    stats = result.value
    assert isinstance(stats, IncrementalStats)
    assert not stats.errors, stats.errors
    return stats


async def _title(driver: AsyncDriver, uid: str) -> str | None:
    async with driver.session() as session:
        record = await (
            await session.run("MATCH (n:Entity {uid: $uid}) RETURN n.title AS title", uid=uid)
        ).single()
    assert record is not None
    return record["title"]


def _touch_forward(path: Path) -> None:
    """Guarantee the mtime moved, so the smart-mode fast path defers to the hash."""
    future = path.stat().st_mtime + 10
    os.utime(path, (future, future))


async def test_node_writes_are_reported_and_split_by_what_merge_did(
    node_ingestion_service, node_vault: Path, neo4j_driver: AsyncDriver
):
    ku_file = node_vault / f"{KU_UID}.md"

    # Stage 1: a new file creates its node.
    ku_file.write_text(_ku_file("First title"))
    first = await _sync(node_ingestion_service, node_vault)
    assert (first.nodes_created, first.nodes_updated) == (1, 0)

    # Stage 2: an untouched file is filtered on hash, so nothing is written.
    second = await _sync(node_ingestion_service, node_vault)
    assert (second.nodes_created, second.nodes_updated) == (0, 0)

    # Stage 3: an edited file writes onto the node it already has.
    ku_file.write_text(_ku_file("Edited title"))
    _touch_forward(ku_file)
    third = await _sync(node_ingestion_service, node_vault)
    assert (third.nodes_created, third.nodes_updated) == (0, 1)
    assert await _title(neo4j_driver, KU_UID) == "Edited title"

    # Stage 4: a force run writes the unchanged file again, and says so.
    forced = await _sync(node_ingestion_service, node_vault, force=True)
    assert (forced.nodes_created, forced.nodes_updated) == (0, 1)


def _task(uid: str, user_uid: str, title: str) -> dict[str, str]:
    return {
        "uid": uid,
        "user_uid": user_uid,
        "entity_type": EntityType.TASK.value,
        "title": title,
    }


async def test_upsert_counts_each_node_it_wrote_once(ensure_test_users, neo4j_driver: AsyncDriver):
    config = ENTITY_CONFIGS[EntityType.TASK]
    backend = build_production_backends(neo4j_driver)["bulk_upsert_backend"]

    async def upsert(entities: list[dict[str, str]]):
        result = await backend.upsert_nodes(
            entity_label=config.entity_label,
            base_label=config.base_label,
            entities=entities,
            relationship_config=config.relationship_config or {},
        )
        assert result.is_ok, result
        return result.value

    try:
        seeded = await upsert(
            [
                _task(EXISTING_TASK, INGESTION_TEST_OWNER, "Existing"),
                _task(FOREIGN_TASK, OTHER_OWNER, "Someone else's"),
            ]
        )
        assert (seeded.nodes_created, seeded.nodes_updated) == (2, 0)

        written = await upsert(
            [
                _task(EXISTING_TASK, INGESTION_TEST_OWNER, "Existing, edited"),
                _task(NEW_TASK, INGESTION_TEST_OWNER, "New"),
                _task(NEW_TASK, INGESTION_TEST_OWNER, "New, named twice"),
                _task(FOREIGN_TASK, INGESTION_TEST_OWNER, "Not mine to write"),
            ]
        )
        assert (written.nodes_created, written.nodes_updated) == (1, 1)
        assert written.refused_uids == (FOREIGN_TASK,)
        assert await _title(neo4j_driver, EXISTING_TASK) == "Existing, edited"
        assert await _title(neo4j_driver, FOREIGN_TASK) == "Someone else's"
    finally:
        await _delete_fixture_nodes(neo4j_driver)
