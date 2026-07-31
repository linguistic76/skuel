"""The vault sync surface reports edge-YAML writes, split by what MERGE did.

``IncrementalStats`` carried ``edges_deleted`` — a deleted Edge YAML reported its
removed relationship all the way to the JSON API and the CLI printer — but the
opposite direction reported nothing at all. Edge files create no nodes, so
``entries_ingested`` (``nodes_created + nodes_updated``) is unmoved by them: a
sync that wrote five edges was byte-identical to one where the files did not
exist. #890 made the truthful signal available (``ingest_edge`` returns MERGE's
own ``ON CREATE``/``ON MATCH`` flag) and #891 deferred this call; this is it.

Three stages, because a two-stage test passes against the wrong implementation.
An ``edges_created = edges_written`` copy — the shape #891 deleted — satisfies
stage 1 alone, and the counters are only proven to be *two-sided* by a stage that
drives created to 0 while updating one:

1. New edge file            -> created 1, updated 0
2. Re-sync, file untouched  -> created 0, updated 0   (the hash gate)
3. Edited property          -> created 0, updated 1

Stage 2 is load-bearing twice over. It pins the reason the counter is signal and
not noise — unchanged edge files are filtered on hash *before parsing*
(``filter_files_needing_ingestion``), so they never reach the edge writer — and it
refutes a counter wired to files *seen* rather than edges *written*.

The relationship count is asserted at every stage: MERGE is an upsert, so a
"created" that ran twice would leave one edge and could hide behind the counts.
Stage 3 also asserts the property actually refreshed, so "updated 1" is pinned to
a real write rather than to a file that was merely re-read.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.ingestion.types import IncrementalStats

pytestmark = pytest.mark.asyncio(loop_scope="session")

SOURCE_UID = "ku.edgewrite-source"
TARGET_UID = "ku.edgewrite-target"
_FIXTURE_UIDS = [SOURCE_UID, TARGET_UID]

# The vault sync doors run "smart" (VaultReconciler.sync) — the mode under test,
# not the "incremental" sibling, so the hash gate exercised here is the real one.
SYNC_MODE = "smart"


def _edge_yaml(confidence: float) -> str:
    return f"""type: Edge
from: {SOURCE_UID}
to: {TARGET_UID}
relationship: RELATED_TO
confidence: {confidence}
"""


@pytest_asyncio.fixture(loop_scope="session")
async def edge_vault(tmp_path: Path) -> Path:
    """A vault holding the two endpoint entities and nothing else yet."""
    vault = tmp_path / "edge_write_vault"
    vault.mkdir()
    for uid in _FIXTURE_UIDS:
        (vault / f"{uid}.md").write_text(
            f"""---
type: ku
title: {uid}
description: Endpoint for the edge-write reporting test
uid: {uid}
domain: testing
---

Body for {uid}.
"""
        )
    return vault


@pytest_asyncio.fixture(loop_scope="session")
async def edge_ingestion_service(neo4j_driver: AsyncDriver):
    """Ingestion service with a backend — incremental/smart modes require the tracker."""
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.ingestion_service_factory import (
        make_unified_ingestion_service,
    )

    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
    )
    yield service

    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_FIXTURE_UIDS)
        await session.run(
            "MATCH (m:IngestionMetadata) WHERE m.file_path CONTAINS 'edge_write_vault' DELETE m"
        )


async def _relationship_count(driver: AsyncDriver) -> int:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $from_uid})-[r:RELATED_TO]->(:Entity {uid: $to_uid}) "
            "RETURN count(r) AS n",
            from_uid=SOURCE_UID,
            to_uid=TARGET_UID,
        )
        record = await result.single()
    assert record is not None
    return int(record["n"])


async def _confidence(driver: AsyncDriver) -> float | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $from_uid})-[r:RELATED_TO]->(:Entity {uid: $to_uid}) "
            "RETURN r.confidence AS confidence",
            from_uid=SOURCE_UID,
            to_uid=TARGET_UID,
        )
        record = await result.single()
    assert record is not None
    return record["confidence"]


async def _sync(service, vault: Path) -> IncrementalStats:
    result = await service.ingest_directory(
        directory=vault,
        pattern="*",
        ingestion_mode=SYNC_MODE,
    )
    assert result.is_ok, result.error
    stats = result.value
    assert isinstance(stats, IncrementalStats)
    return stats


def _touch_forward(path: Path) -> None:
    """Guarantee the mtime moved, so the smart-mode fast path defers to the hash.

    Filesystem mtime granularity is the only thing standing between a rewrite
    inside one test and a spurious "unchanged" skip; an explicit bump removes
    the timing dependency rather than relying on nanosecond stamps.
    """
    future = path.stat().st_mtime + 10
    os.utime(path, (future, future))


async def test_edge_writes_are_reported_and_split_by_what_merge_did(
    edge_ingestion_service, edge_vault: Path, neo4j_driver: AsyncDriver
):
    # Endpoints first: edges are written after entities, and a missing endpoint
    # is an error rather than a write, which would make every count below 0.
    seed = await _sync(edge_ingestion_service, edge_vault)
    assert seed.edges_created == 0
    assert seed.edges_updated == 0

    edge_file = edge_vault / "edge-source-target.yaml"

    # Stage 1: a new Edge YAML reports a created edge.
    edge_file.write_text(_edge_yaml(0.8))
    first = await _sync(edge_ingestion_service, edge_vault)
    assert first.edges_created == 1
    assert first.edges_updated == 0
    assert await _relationship_count(neo4j_driver) == 1
    assert await _confidence(neo4j_driver) == pytest.approx(0.8)

    # Stage 2: an untouched edge file is filtered on hash before parsing, so
    # nothing is written and nothing is reported.
    second = await _sync(edge_ingestion_service, edge_vault)
    assert second.edges_created == 0
    assert second.edges_updated == 0
    assert await _relationship_count(neo4j_driver) == 1

    # Stage 3: editing a property re-writes the same edge — created flips to 0
    # and updated to 1, which is what makes the pair two-sided.
    edge_file.write_text(_edge_yaml(0.4))
    _touch_forward(edge_file)
    third = await _sync(edge_ingestion_service, edge_vault)
    assert third.edges_created == 0
    assert third.edges_updated == 1
    assert await _relationship_count(neo4j_driver) == 1
    assert await _confidence(neo4j_driver) == pytest.approx(0.4)


async def test_deleted_edge_file_reports_the_other_direction(
    edge_ingestion_service, edge_vault: Path, neo4j_driver: AsyncDriver
):
    """The write counters do not disturb the deletion counter they mirror.

    ``edges_deleted`` is the field this pair was added to be symmetric with, and
    both directions run off the same tracked edge-file row — a write counter fed
    from the wrong place (edge files *seen*, say) would show up here as a delete
    that also reports a write.
    """
    edge_file = edge_vault / "edge-source-target.yaml"
    edge_file.write_text(_edge_yaml(0.8))
    created = await _sync(edge_ingestion_service, edge_vault)
    assert created.edges_created == 1
    assert created.edges_deleted == 0

    edge_file.unlink()
    deleted = await _sync(edge_ingestion_service, edge_vault)
    assert deleted.edges_deleted == 1
    assert deleted.edges_created == 0
    assert deleted.edges_updated == 0
    assert await _relationship_count(neo4j_driver) == 0
