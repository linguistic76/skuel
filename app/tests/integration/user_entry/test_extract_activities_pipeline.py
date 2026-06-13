"""
EXTRACT_ACTIVITIES pipeline integration — ADR-069
==================================================

Drives ``UserEntryProcessingService._run_extract_activities`` against a real
Neo4j container and asserts the graph contracts:

- created entities carry ``(created)-[:EXTRACTED_FROM {extracted_at,
  source_line_hash}]->(entry)`` provenance edges,
- resolved ``@ku()`` references write ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)``,
- the run summary lands in ``entry.metadata["activity_extraction"]``,
- guard 1 (completed-run metadata) makes re-processing a no-op,
- guard 2 (line-hash dedup) makes ``force`` re-runs duplicate-free,
- non-teacher ``@context(ku)`` creation lines are gated into creation_errors.

Entity creation itself goes through a thin graph-writing stub (the facade
create paths have their own suites); everything from the extractor outward —
parsing, hashing, provenance, edges, metadata — is the real code over real
Neo4j.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.services.dsl.activity_extractor import ActivityExtractorService
from core.services.user_entry.user_entry_processing_service import (
    UserEntryProcessingService,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry


class _GraphTasksStub:
    """Create-capable stand-in that writes real ``:Entity:Task`` nodes."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver
        self.created_uids: list[str] = []

    async def create_task(self, request: Any, user_uid: str) -> Result[Any]:
        uid = f"task:extract_it_{uuid4().hex[:8]}"
        async with self.driver.session() as session:
            await session.run(
                """
                CREATE (t:Entity:Task {uid: $uid, title: $title,
                        entity_type: 'task', user_uid: $user_uid,
                        created_at: datetime()})
                """,
                uid=uid,
                title=request.title,
                user_uid=user_uid,
            )
        self.created_uids.append(uid)
        return Result.ok(SimpleNamespace(uid=uid, title=request.title))


def _user_service(can_create_curriculum: bool) -> MagicMock:
    user = MagicMock()
    user.can_create_curriculum = MagicMock(return_value=can_create_curriculum)
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


async def _seed_ku(driver: Any, uid: str) -> str:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            ON CREATE SET k.title = $uid, k.entity_type = 'ku',
                          k.created_at = datetime()
            """,
            uid=uid,
        )
    return uid


async def _create_entry(user_entry_service: Any, user_uid: str, content: str) -> UserEntry:
    request = UserEntryCreateRequest(
        title="Extraction source",
        content=content,
        pipeline=Pipeline.EXTRACT_ACTIVITIES,
    )
    result = await user_entry_service.create_entry(request=request, user_uid=user_uid)
    assert result.is_ok, f"entry create failed: {result.error}"
    entry, _share = result.value
    return entry


@pytest.mark.integration
class TestExtractActivitiesPipeline:
    @pytest.mark.asyncio
    async def test_full_run_writes_entities_provenance_and_knowledge_edges(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_extract_{uuid4().hex[:6]}")
        ku_uid = await _seed_ku(neo4j_driver, f"ku_extract_it_{uuid4().hex[:6]}")

        content = (
            "Morning notes.\n\n"
            "- [ ] Call the bank @context(task) @priority(1)\n"
            f"- [ ] Practice decorators @context(task) @ku({ku_uid})\n"
            "- [ ] New concept @context(ku)\n"
        )
        entry = await _create_entry(user_entry_service, user_uid, content)

        tasks_stub = _GraphTasksStub(neo4j_driver)
        dispatcher = UserEntryProcessingService(
            entry_service=user_entry_service,
            activity_extractor=ActivityExtractorService(tasks_service=tasks_stub),
            user_service=_user_service(can_create_curriculum=False),
        )

        result = await dispatcher.process(entry)
        assert result.is_ok, f"process failed: {result.error}"
        updated = result.value

        # --- run summary persisted -------------------------------------------
        summary = (updated.metadata or {}).get("activity_extraction")
        assert isinstance(summary, dict), f"summary missing/unparsed: {summary!r}"
        assert summary["status"] == "completed"
        assert summary["tasks_created"] == 2
        # Non-teacher @context(ku) creation line gated, not created.
        assert summary["kus_created"] == 0
        assert any(
            "curriculum creation requires teacher/admin role" in e
            for e in summary["creation_errors"]
        )

        # --- EXTRACTED_FROM provenance edges ----------------------------------
        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (t:Task)-[r:EXTRACTED_FROM]->(e:UserEntry {uid: $uid})
                RETURN t.uid AS task_uid, r.source_line_hash AS line_hash,
                       r.extracted_at AS extracted_at
                """,
                uid=entry.uid,
            )
            rows = await res.data()
        assert len(rows) == 2
        assert {row["task_uid"] for row in rows} == set(tasks_stub.created_uids)
        for row in rows:
            assert len(row["line_hash"]) == 64
            assert row["extracted_at"] is not None

        # --- APPLIES_KNOWLEDGE edge for the @ku() reference --------------------
        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (e:UserEntry {uid: $uid})-[:APPLIES_KNOWLEDGE]->(k:Ku)
                RETURN k.uid AS ku_uid
                """,
                uid=entry.uid,
            )
            ku_rows = await res.data()
        assert [row["ku_uid"] for row in ku_rows] == [ku_uid]

    @pytest.mark.asyncio
    async def test_reprocess_is_noop_and_force_is_duplicate_free(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        user_uid = await seed_user(f"user_extract_{uuid4().hex[:6]}")
        content = "- [ ] One task @context(task)\n"
        entry = await _create_entry(user_entry_service, user_uid, content)

        tasks_stub = _GraphTasksStub(neo4j_driver)
        dispatcher = UserEntryProcessingService(
            entry_service=user_entry_service,
            activity_extractor=ActivityExtractorService(tasks_service=tasks_stub),
            user_service=_user_service(can_create_curriculum=False),
        )

        first = await dispatcher.process(entry)
        assert first.is_ok
        assert len(tasks_stub.created_uids) == 1
        completed_entry = first.value

        # Guard 1: re-process without force → no-op, nothing new created.
        second = await dispatcher.process(completed_entry)
        assert second.is_ok
        assert second.value is completed_entry
        assert len(tasks_stub.created_uids) == 1

        # Guard 2: force re-run → runs again but line-hash dedup skips the line.
        third = await dispatcher.process(completed_entry, force=True)
        assert third.is_ok
        assert len(tasks_stub.created_uids) == 1, "force re-run duplicated entities"
        summary = (third.value.metadata or {}).get("activity_extraction")
        assert isinstance(summary, dict)
        assert summary["lines_skipped_existing"] == 1

        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (:Task)-[r:EXTRACTED_FROM]->(e:UserEntry {uid: $uid})
                RETURN count(r) AS edges
                """,
                uid=entry.uid,
            )
            record = await res.single()
        assert record["edges"] == 1
