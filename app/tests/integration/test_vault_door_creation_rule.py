"""The vault door applies the Task creation rule to the files it creates.

A ``type: task`` file authored with neither ``due_date`` nor ``scheduled_date``
must land dated — on its ``created_at`` day — or the task renders on no day of
the calendar or ``/today``. The bulk upsert never builds a ``Task``, so the rule
the service create primitive applies on the entity is applied here on the node
by the post-persist pass. These tests drive the REAL doors (``ingest_file`` and
``ingest_directory``) against a real graph, because the post-persist seam is
exactly where the wiring can be absent and still look correct from a
hand-built backend call.

Pinned:

- an undated file lands with ``due_date`` = its own ``created_at`` day (the
  node's stamp, not the test's clock — the two can differ across midnight UTC);
- a file with only ``scheduled_date`` keeps ``due_date`` NULL — a work date is
  a date;
- an authored ``due_date`` is never overwritten;
- a born-completed file whose ``✅`` day is earlier takes that day;
- a file authored OPEN beside a leftover stamp line is due on its creation day
  (the stamp is not consulted; the status step then clears it);
- a re-sync that removes the file's last date line has the creation day
  restored — the vault's equivalent of the app's refusal to clear the last
  date (``TasksCoreService._validate_update``), since the upsert has already
  merged the removal; a re-sync that keeps a date changes nothing;
- the directory door behaves the same.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

OWNER_UID = "user_test_integration"  # seeded by the ensure_test_users fixture


@pytest.fixture
def door(neo4j_driver):
    """A real ingestion service (CORE-tier shape: no bus, nothing to publish)."""
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.ingestion_service_factory import (
        make_unified_ingestion_service,
    )
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    return make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
    )


def _write(directory: Path, slug: str, frontmatter: str = "") -> Path:
    path = directory / f"{slug}.md"
    path.write_text(
        f"---\ntype: task\nuid: task.{slug}\ntitle: {slug}\nuser_uid: {OWNER_UID}\n"
        f"{frontmatter}---\n\nBody of {slug}.\n"
    )
    return path


async def _props(neo4j_driver, uid: str) -> dict[str, Any]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Task {uid: $uid}) RETURN n.due_date AS due_date, "
            "n.scheduled_date AS scheduled_date, toString(n.created_at) AS created_at, "
            "valueType(n.due_date) AS due_type",
            {"uid": uid},
        )
        record = await result.single()
        assert record is not None, f"{uid} is not in the graph"
        return dict(record)


@pytest.mark.asyncio
async def test_an_undated_file_lands_due_on_its_creation_day(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    path = _write(tmp_path, "rule-undated")

    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-undated")
    assert node["due_date"] == node["created_at"][:10]
    assert node["due_type"].startswith("STRING"), "writers store ISO date strings"
    assert node["scheduled_date"] is None


@pytest.mark.asyncio
async def test_a_scheduled_only_file_gets_no_deadline(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    path = _write(tmp_path, "rule-scheduled", "scheduled_date: 2026-12-20\n")

    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-scheduled")
    assert node["due_date"] is None
    assert str(node["scheduled_date"])[:10] == "2026-12-20"


@pytest.mark.asyncio
async def test_an_authored_due_date_is_kept(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    path = _write(tmp_path, "rule-dated", "due_date: 2026-12-31\n")

    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-dated")
    assert str(node["due_date"])[:10] == "2026-12-31"


@pytest.mark.asyncio
async def test_a_born_completed_file_takes_its_earlier_completion_day(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    """A historical ``✅`` line was lived on the day it was done, not ingested."""
    path = _write(tmp_path, "rule-done", "status: completed\ncompletion_date: 2026-03-04\n")

    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-done")
    assert node["due_date"] == "2026-03-04"


@pytest.mark.asyncio
async def test_a_file_authored_open_beside_a_stamp_is_due_on_its_creation_day(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    """The creation rule runs before the stamp-clear, so it must not read the
    stamp it is about to lose: an open task's ``completion_date`` is not a day
    it was lived."""
    path = _write(tmp_path, "rule-open-stamp", "status: active\ncompletion_date: 2026-03-04\n")

    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-open-stamp")
    assert node["due_date"] == node["created_at"][:10]
    assert node["due_date"] != "2026-03-04"
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (n:Task {uid: $uid}) RETURN n.completion_date AS stamp",
                {"uid": "task.rule-open-stamp"},
            )
        ).single()
    assert record is not None and record["stamp"] is None, "the status step did not clear it"


@pytest.mark.asyncio
async def test_a_resync_that_drops_the_last_date_restores_the_creation_day(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    """The blank line writes null and ``SET n += props`` deletes the property —
    the upsert cannot refuse what the app's update rule refuses, so the pass
    restores the creation day: the task keeps a day either way."""
    path = _write(tmp_path, "rule-resync", "due_date: 2026-12-31\n")
    assert (await door.ingest_file(path)).is_ok
    first = await _props(neo4j_driver, "task.rule-resync")
    assert str(first["due_date"])[:10] == "2026-12-31"

    _write(tmp_path, "rule-resync", "due_date:\n")
    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-resync")
    assert node["due_date"] == first["created_at"][:10], "the task lost its last date"


@pytest.mark.asyncio
async def test_a_resync_that_keeps_a_date_changes_nothing(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    path = _write(tmp_path, "rule-resync-kept", "scheduled_date: 2026-12-20\n")
    assert (await door.ingest_file(path)).is_ok

    _write(tmp_path, "rule-resync-kept", "scheduled_date: 2026-12-20\ndescription: edited\n")
    assert (await door.ingest_file(path)).is_ok

    node = await _props(neo4j_driver, "task.rule-resync-kept")
    assert node["due_date"] is None, "a scheduled-only task was given a deadline on re-sync"
    assert str(node["scheduled_date"])[:10] == "2026-12-20"


@pytest.mark.asyncio
async def test_the_directory_door_dates_its_creates_too(
    clean_neo4j, neo4j_driver, door, tmp_path: Path
) -> None:
    _write(tmp_path, "rule-dir-undated")
    _write(tmp_path, "rule-dir-scheduled", "scheduled_date: 2026-12-20\n")

    assert (await door.ingest_directory(tmp_path)).is_ok

    undated = await _props(neo4j_driver, "task.rule-dir-undated")
    assert undated["due_date"] == undated["created_at"][:10]
    scheduled = await _props(neo4j_driver, "task.rule-dir-scheduled")
    assert scheduled["due_date"] is None
