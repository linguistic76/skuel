"""What a directory sync does with its relationship pass's outcome (``ingest_directory``).

- A pass that fails leaves its files unstamped — each keeps its identity in a pending
  row — so the next sync re-processes them instead of skipping them as unchanged,
  with edges the failed pass may not have written.
- A pass that succeeds stamps its files, and hands ``links_created_fn`` the links it
  created; a pass that created none does not call it.

The bulk backend is a double whose relationship pass answers as each test says; the
tracker reads and writes an in-memory backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.ingestion.ingestion_types import IngestionResult
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.ingestion.batch import ingest_directory
from core.services.ingestion.ingestion_tracker import PENDING_MTIME
from core.utils.result_simplified import Errors, Result
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER

pytestmark = pytest.mark.asyncio

TASK_UID = "task.relpass.water-the-plants"
KU_UID = "ku.relpass.care"
FIELD = "connections.applies_knowledge"


def _result(created: dict[str, dict[str, tuple[str, ...]]] | None = None) -> IngestionResult:
    return IngestionResult(
        total_processed=1,
        nodes_created=0,
        nodes_updated=0,
        relationships_created=0,
        errors=[],
        created_targets=created or {},
    )


class _Bulk:
    """Node upserts succeed; the relationship pass answers ``relationships``."""

    def __init__(self, relationships: Result[IngestionResult]) -> None:
        self.relationships = relationships

    async def upsert_nodes(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, object]],
        relationship_config: dict[str, object],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        return Result.ok(_result())

    async def create_relationships(
        self,
        entity_label: str,
        base_label: str | None,
        entities: list[dict[str, object]],
        relationship_config: dict[str, object],
        batch_size: int = 500,
    ) -> Result[IngestionResult]:
        return self.relationships


class _Tracker:
    """The tracker's backend in memory: no prior rows, every write recorded."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def ensure_tracker_constraints(self) -> Result[None]:
        return Result.ok(None)

    async def get_ingestion_metadata(self, path_strings: list[str]) -> Result[list[object]]:
        return Result.ok([])

    async def get_ingestion_metadata_by_uids(self, uids: list[str]) -> Result[list[object]]:
        return Result.ok([])

    async def update_ingestion_metadata(self, item: dict[str, object]) -> Result[list[object]]:
        self.rows.append(item)
        return Result.ok([{"updated": 1}])

    async def update_ingestion_metadata_batch(
        self, items: list[dict[str, object]]
    ) -> Result[list[object]]:
        self.rows.extend(items)
        return Result.ok([{"updated": len(items)}])

    async def get_tracked_files_under(self, prefix: str) -> Result[list[object]]:
        return Result.ok([])

    async def get_live_entity_uids(self, uids: list[str]) -> Result[list[object]]:
        return Result.ok([])


class _Heard:
    """``links_created_fn``: records each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, dict[str, tuple[str, ...]]]]] = []

    async def __call__(
        self,
        entity_type: EntityType | NonKuDomain,
        entities: list[dict[str, Any]],  # boundary: prepared entity dicts
        created: Any,  # boundary: uid -> field -> targets, as the pass reported it
    ) -> None:
        self.calls.append(
            (
                entity_type.value,
                [str(entity["uid"]) for entity in entities],
                {uid: dict(fields) for uid, fields in created.items()},
            )
        )


def _task_file(directory: Path) -> Path:
    path = directory / "water.md"
    path.write_text(
        "---\n"
        f"type: task\nuid: {TASK_UID}\ntitle: Water the plants\n"
        f"user_uid: {INGESTION_TEST_OWNER}\n"
        f"connections:\n  applies_knowledge:\n    - {KU_UID}\n"
        "---\nBody.\n",
        encoding="utf-8",
    )
    return path


async def _sync(directory: Path, bulk: _Bulk, tracker: _Tracker, heard: _Heard) -> None:
    result = await ingest_directory(
        directory=directory,
        default_user_uid=INGESTION_TEST_OWNER,
        bulk_backend=bulk,
        ingestion_backend=tracker,
        ingestion_mode="smart",
        links_created_fn=heard,
    )
    assert result.is_ok, result


async def test_a_failed_relationship_pass_leaves_its_file_pending(tmp_path: Path) -> None:
    path = _task_file(tmp_path)
    tracker, heard = _Tracker(), _Heard()

    await _sync(
        tmp_path,
        _Bulk(Result.fail(Errors.database("create_relationships", "down"))),
        tracker,
        heard,
    )

    assert [(row["file_path"], row["file_mtime"]) for row in tracker.rows] == [
        (str(path.resolve()), PENDING_MTIME)
    ]
    assert heard.calls == []


async def test_a_pass_that_succeeds_stamps_its_file_and_reports_what_it_created(
    tmp_path: Path,
) -> None:
    path = _task_file(tmp_path)
    tracker, heard = _Tracker(), _Heard()

    await _sync(tmp_path, _Bulk(Result.ok(_result({TASK_UID: {FIELD: (KU_UID,)}}))), tracker, heard)

    assert [row["file_path"] for row in tracker.rows] == [str(path.resolve())]
    assert all(row["file_mtime"] != PENDING_MTIME for row in tracker.rows)
    assert heard.calls == [("task", [TASK_UID], {TASK_UID: {FIELD: (KU_UID,)}})]


async def test_a_pass_that_created_nothing_reports_nothing(tmp_path: Path) -> None:
    _task_file(tmp_path)
    heard = _Heard()

    await _sync(tmp_path, _Bulk(Result.ok(_result())), _Tracker(), heard)

    assert heard.calls == []
