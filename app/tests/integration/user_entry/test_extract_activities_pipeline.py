"""
EXTRACT_ACTIVITIES pipeline integration — ADR-069
==================================================

Drives ``UserEntryProcessingService._run_extract_activities`` against a real
Neo4j container and asserts the graph contracts:

- created entities carry ``(created)-[:EXTRACTED_FROM {extracted_at,
  source_line_hash}]->(entry)`` provenance edges,
- resolved ``@ku()`` references write ``(entry)-[:APPLIES_KNOWLEDGE]->(ku)``,
- ``@link(ku:<uid>)`` — the multi-Ku door — resolves the same way: the id after
  the prefix is the stored uid, so the edge lands with no ``@ku()`` on the line,
- the run summary lands in ``entry.metadata["activity_extraction"]``,
- guard 1 (completed-run metadata) makes re-processing a no-op,
- guard 2 (line-hash dedup) makes ``force`` re-runs duplicate-free,
- guard 3 (semantic dedup, R3): a bridge that REWORDS its lines every run —
  the live LLM behavior that caused G8's duplicates — merges into the
  existing entity instead of duplicating,
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


class _GraphHabitsStub:
    """Create-capable stand-in that writes real ``:Entity:Habit`` nodes."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver
        self.created_uids: list[str] = []

    async def create_habit(self, request: Any, user_uid: str) -> Result[Any]:
        uid = f"habit:extract_it_{uuid4().hex[:8]}"
        async with self.driver.session() as session:
            await session.run(
                """
                CREATE (h:Entity:Habit {uid: $uid, title: $title,
                        entity_type: 'habit', user_uid: $user_uid,
                        created_at: datetime()})
                """,
                uid=uid,
                title=request.title,
                user_uid=user_uid,
            )
        self.created_uids.append(uid)
        return Result.ok(SimpleNamespace(uid=uid, title=request.title))


class _RewordingBridgeStub:
    """Bridge double reproducing the G8 signature: same semantic activity,
    differently-worded DSL line (→ different Guard-2 hash) on every call."""

    def __init__(self) -> None:
        self.calls = 0

    async def transform_with_context(
        self, text: str, user_uid: str | None = None, active_goals: Any = None
    ) -> Result[Any]:
        self.calls += 1
        return Result.ok(
            SimpleNamespace(activity_lines=[f"Meditate @context(habit) @priority({self.calls})"])
        )


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
    async def test_link_ku_reference_writes_the_knowledge_edge(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        """``@link(ku:<uid>)`` names a stored uid, so the reference resolves:
        the entry gets its APPLIES_KNOWLEDGE edge and the run reports no
        link error — with no ``@ku()`` on the line."""
        user_uid = await seed_user(f"user_link_{uuid4().hex[:6]}")
        ku_uid = await _seed_ku(neo4j_driver, f"ku_link_it_{uuid4().hex[:6]}")
        content = f"- [ ] Practice decorators @context(task) @link(ku:{ku_uid})\n"
        entry = await _create_entry(user_entry_service, user_uid, content)

        dispatcher = UserEntryProcessingService(
            entry_service=user_entry_service,
            activity_extractor=ActivityExtractorService(
                tasks_service=_GraphTasksStub(neo4j_driver)
            ),
            user_service=_user_service(can_create_curriculum=False),
        )
        result = await dispatcher.process(entry)
        assert result.is_ok, f"process failed: {result.error}"
        summary = (result.value.metadata or {}).get("activity_extraction")
        assert isinstance(summary, dict), f"summary missing/unparsed: {summary!r}"
        assert summary.get("link_errors", []) == [], summary.get("link_errors")

        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (e:UserEntry {uid: $uid})-[:APPLIES_KNOWLEDGE]->(k:Ku)
                RETURN k.uid AS ku_uid
                """,
                uid=entry.uid,
            )
            ku_rows = await res.data()
        assert [row["ku_uid"] for row in ku_rows] == [ku_uid], (
            "the @link(ku:…) reference must resolve to the stored uid and write the edge"
        )

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

    @pytest.mark.asyncio
    async def test_rewording_bridge_reruns_merge_instead_of_duplicating(
        self, neo4j_driver, user_entry_service, seed_user
    ):
        """Guard 3 (R3): twice over one entry, node count stays stable.

        The bridge stub rewords its generated line on every run (different
        Guard-2 hash, same semantic title) — exactly the live G8 signature
        that created "meditate" x3 from one entry.
        """
        user_uid = await seed_user(f"user_extract_{uuid4().hex[:6]}")
        entry = await _create_entry(
            user_entry_service, user_uid, "I want to build a meditation practice.\n"
        )

        habits_stub = _GraphHabitsStub(neo4j_driver)
        bridge_stub = _RewordingBridgeStub()
        dispatcher = UserEntryProcessingService(
            entry_service=user_entry_service,
            activity_extractor=ActivityExtractorService(habits_service=habits_stub),
            user_service=_user_service(can_create_curriculum=False),
            dsl_bridge=bridge_stub,
        )

        first = await dispatcher.process(entry)
        assert first.is_ok, f"first run failed: {first.error}"
        assert len(habits_stub.created_uids) == 1

        # Re-sync: the bridge rewords the line → Guard 2 misses, Guard 3 merges.
        second = await dispatcher.process(first.value, force=True)
        assert second.is_ok, f"second run failed: {second.error}"
        assert bridge_stub.calls == 2, "bridge did not run twice"
        assert len(habits_stub.created_uids) == 1, "re-sync duplicated the habit"

        summary = (second.value.metadata or {}).get("activity_extraction")
        assert isinstance(summary, dict)
        assert summary["habits_created"] == 0
        assert summary["lines_merged_existing"] == 1

        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (h:Habit)-[r:EXTRACTED_FROM]->(e:UserEntry {uid: $uid})
                RETURN count(h) AS habits, count(r) AS edges
                """,
                uid=entry.uid,
            )
            record = await res.single()
        assert record["habits"] == 1, "graph grew a duplicate habit"
        assert record["edges"] == 1, "provenance edge duplicated instead of merged"
