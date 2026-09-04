"""
Integration: a vault Group lands with its owner's ``:OWNS`` edge, or the file fails.

Drives the production path against a real Neo4j through both ingest doors — the
directory sync and the single-file door — with a vault ``type: group`` file. The
invariant every write door owes (ADR-086 § 1): ``owner_uid`` property ``==``
``:OWNS`` owner. For a Group that edge is written by
``IngestionWriteBackend.create_group_ownership``, which returns the MERGE count;
a count of 0 (the owner has no ``:User`` node) fails the file, and a failed file
is not stamped — the next sync retries it instead of hash-skipping a
property-only Group nobody can reach through an ``:OWNS`` traversal.

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
from core.models.type_hints import UserUID
from core.services.ingestion.types import IncrementalStats

_MARK = "zzzgrpowns"
_OWNER = UserUID(f"user_{_MARK}_owner")
_NOBODY = f"user_{_MARK}_nobody"  # never given a :User node
_GROUP_ONE = f"group.{_MARK}.one"
_GROUP_TWO = f"group.{_MARK}.two"


def _group_file(vault: Path, name: str, uid: str, owner: str) -> Path:
    path = vault / f"{name}.md"
    path.write_text(
        f"---\ntype: group\nuid: {uid}\nname: Group {name}\nowner_uid: {owner}\n---\nBody.\n"
    )
    return path


async def _owns_edge_exists(neo4j_driver, owner: str, group_uid: str) -> bool:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (u:User {uid: $o})-[r:OWNS]->(g:Group {uid: $g}) RETURN count(r) AS c",
            {"o": owner, "g": group_uid},
        )
        record = await res.single()
        return bool(record and record["c"] > 0)


async def _tracker_rows(neo4j_driver, entity_uid: str) -> list[dict[str, Any]]:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (s:IngestionMetadata {entity_uid: $uid}) RETURN s.file_path AS file_path",
            {"uid": entity_uid},
        )
        return [dict(record) async for record in res]


@pytest_asyncio.fixture
async def group_ingestion_service(neo4j_driver):
    """UnifiedIngestionService with the tracker wired; the known owner exists."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.title = $uid, u.is_active = true",
            {"uid": str(_OWNER)},
        )
    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
        default_user_uid=_OWNER,
    )
    yield service
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (g:Group) WHERE g.uid CONTAINS $mark DETACH DELETE g", {"mark": _MARK}
        )
        await session.run(
            "MATCH (u:User) WHERE u.uid CONTAINS $mark DETACH DELETE u", {"mark": _MARK}
        )
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid CONTAINS $mark DELETE s",
            {"mark": _MARK},
        )


@pytest.mark.integration
class TestVaultGroupOwnership:
    async def test_directory_door_writes_the_owner_edge(
        self, group_ingestion_service, neo4j_driver, tmp_path: Path
    ):
        """A synced Group file names a known owner → the :OWNS edge exists and
        the file's tracker row is stamped with the Group's uid."""
        vault = tmp_path / "vault"
        vault.mkdir()
        path = _group_file(vault, "one", _GROUP_ONE, str(_OWNER))
        result = await group_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result.is_ok, f"sync failed: {result}"
        stats = cast("IncrementalStats", result.value)
        assert not stats.errors, f"sync errors: {stats.errors}"
        assert await _owns_edge_exists(neo4j_driver, str(_OWNER), _GROUP_ONE)
        rows = await _tracker_rows(neo4j_driver, _GROUP_ONE)
        assert [row["file_path"] for row in rows] == [str(path.resolve())]

    async def test_directory_door_fails_the_file_when_the_owner_is_unknown(
        self, group_ingestion_service, neo4j_driver, tmp_path: Path
    ):
        """An owner with no :User node → the sync reports the file as an error
        naming the owner, writes no edge, and leaves the file unstamped so the
        next sync retries it."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _group_file(vault, "two", _GROUP_TWO, _NOBODY)
        result = await group_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result.is_ok, f"sync raised instead of reporting: {result}"
        stats = cast("IncrementalStats", result.value)
        assert stats.errors, "an unknown owner must surface as a sync error"
        assert any(_NOBODY in str(error) for error in stats.errors), stats.errors
        assert not await _owns_edge_exists(neo4j_driver, _NOBODY, _GROUP_TWO)
        assert await _tracker_rows(neo4j_driver, _GROUP_TWO) == []

    async def test_single_file_door_writes_the_owner_edge_and_stamps(
        self, group_ingestion_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        path = _group_file(vault, "one", _GROUP_ONE, str(_OWNER))
        result = await group_ingestion_service.ingest_file(path)
        assert result.is_ok, f"ingest failed: {result}"
        assert await _owns_edge_exists(neo4j_driver, str(_OWNER), _GROUP_ONE)
        rows = await _tracker_rows(neo4j_driver, _GROUP_ONE)
        assert [row["file_path"] for row in rows] == [str(path.resolve())]

    async def test_single_file_door_fails_on_unknown_owner(
        self, group_ingestion_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        path = _group_file(vault, "two", _GROUP_TWO, _NOBODY)
        result = await group_ingestion_service.ingest_file(path)
        assert result.is_error, "an unknown owner must fail the file"
        assert _NOBODY in str(result.expect_error())
        assert not await _owns_edge_exists(neo4j_driver, _NOBODY, _GROUP_TWO)
        assert await _tracker_rows(neo4j_driver, _GROUP_TWO) == []
