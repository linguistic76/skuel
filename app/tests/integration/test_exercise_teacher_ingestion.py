"""
Integration: an exercise file names its teacher, or the sync refuses it by name.

Every exercise names its teacher in its vault file (ADR-091 S3). The ``teacher`` field
holds one user uid and becomes ``(Exercise)-[:REVIEWED_BY]->(User)`` — never ``OWNS``.
Both ingest doors refuse, before anything is written, a file that:

- has no ``teacher`` (a required field — the file is reported with the reason);
- names a uid that is no user, or a user without the TEACHER role or higher (a sync
  error naming the file).

The edge is the file's own: it rides the file's authored-edge fingerprint, so a changed
``teacher`` retracts the old edge on the next sync.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import pytest_asyncio

from core.services.ingestion.types import IncrementalStats
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER
from tests.helpers.production_backends import build_ingestion_service, build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

    from core.services.ingestion import UnifiedIngestionService

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MARK = "zzzexteachingest"
_TEACHER = seed_user_uid(f"{_MARK}_teacher")
_SECOND_TEACHER = seed_user_uid(f"{_MARK}_second")
_MEMBER = seed_user_uid(f"{_MARK}_member")
_UNKNOWN = seed_user_uid(f"{_MARK}_nobody")


def _exercise_file(vault: Path, name: str, *, teacher: str | None) -> Path:
    lines = [
        "type: exercise",
        f"uid: ex.{_MARK}.{name}",
        f"title: Teacher {name}",
        "instructions: Describe one thing you noticed.",
    ]
    if teacher is not None:
        lines.append(f"teacher: {teacher}")
    path = vault / f"{name}.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\n")
    return path


async def _exercise(
    neo4j_driver: AsyncDriver, name: str
) -> dict[str, Any] | None:  # boundary: a raw neo4j row
    """The exercise node's teachers and owners, or None when no node was written."""
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (ex:Entity:Exercise {uid: $uid})
                RETURN [(ex)-[:REVIEWED_BY]->(t:User) | t.uid] AS teachers,
                       [(o:User)-[:OWNS]->(ex) | o.uid] AS owners,
                       ex.teacher AS teacher_property
                """,
                uid=f"ex.{_MARK}.{name}",
            )
        ).single()
    return dict(record) if record else None


def _errors_for(
    stats: IncrementalStats, name: str
) -> list[dict[str, Any]]:  # boundary: IngestionError dicts
    return [
        error for error in stats.errors or [] if Path(str(error.get("file"))).name == f"{name}.md"
    ]


@pytest_asyncio.fixture
async def service(neo4j_driver: AsyncDriver) -> AsyncIterator[UnifiedIngestionService]:
    async with neo4j_driver.session() as session:
        for uid, role in (
            (_TEACHER, "teacher"),
            (_SECOND_TEACHER, "admin"),
            (_MEMBER, "member"),
        ):
            await session.run("MERGE (u:User {uid: $uid}) SET u.role = $role", uid=uid, role=role)
    yield build_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=build_production_backends(neo4j_driver)["ingestion_backend"],
        default_user_uid=INGESTION_TEST_OWNER,
    )
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark OR n.uid IN $users
            DETACH DELETE n
            """,
            mark=_MARK,
            users=[_TEACHER, _SECOND_TEACHER, _MEMBER],
        )


async def _sync(service: UnifiedIngestionService, vault: Path) -> IncrementalStats:
    result = await service.ingest_directory(vault, ingestion_mode="smart")
    assert result.is_ok, f"sync failed: {result}"
    return cast("IncrementalStats", result.value)


@pytest.mark.integration
class TestExerciseTeacherIngestion:
    async def test_a_named_teacher_becomes_the_reviewed_by_edge_and_no_owner(
        self, service: UnifiedIngestionService, neo4j_driver: AsyncDriver, tmp_path: Path
    ) -> None:
        _exercise_file(tmp_path, "named", teacher=_TEACHER)
        _exercise_file(tmp_path, "admin", teacher=_SECOND_TEACHER)

        stats = await _sync(service, tmp_path)

        assert not stats.errors, stats.errors
        assert await _exercise(neo4j_driver, "named") == {
            "teachers": [_TEACHER],
            "owners": [],
            "teacher_property": None,
        }
        admin = await _exercise(neo4j_driver, "admin")
        assert admin is not None and admin["teachers"] == [_SECOND_TEACHER]

    async def test_a_file_without_a_teacher_is_refused_by_name(
        self, service: UnifiedIngestionService, neo4j_driver: AsyncDriver, tmp_path: Path
    ) -> None:
        _exercise_file(tmp_path, "teacherless", teacher=None)
        _exercise_file(tmp_path, "control", teacher=_TEACHER)

        stats = await _sync(service, tmp_path)

        [error] = _errors_for(stats, "teacherless")
        assert error["stage"] == "validation", error
        assert "File teacherless.md" in error["error"], error
        assert "'teacher'" in error["error"], error
        assert await _exercise(neo4j_driver, "teacherless") is None
        assert await _exercise(neo4j_driver, "control") is not None

    @pytest.mark.parametrize(
        ("teacher", "says"),
        [(_UNKNOWN, "names no user"), (_MEMBER, "has the 'member' role")],
    )
    async def test_a_teacher_who_is_not_a_teacher_is_a_sync_error_naming_the_file(
        self,
        service: UnifiedIngestionService,
        neo4j_driver: AsyncDriver,
        tmp_path: Path,
        teacher: str,
        says: str,
    ) -> None:
        _exercise_file(tmp_path, "refused", teacher=teacher)
        _exercise_file(tmp_path, "control", teacher=_TEACHER)

        stats = await _sync(service, tmp_path)

        [error] = _errors_for(stats, "refused")
        assert error["stage"] == "exercise_teacher", error
        assert error["error"].startswith("File refused.md:"), error
        assert says in error["error"], error
        assert await _exercise(neo4j_driver, "refused") is None
        assert await _exercise(neo4j_driver, "control") is not None

    async def test_the_single_file_door_refuses_a_non_teacher_and_admits_a_teacher(
        self, service: UnifiedIngestionService, neo4j_driver: AsyncDriver, tmp_path: Path
    ) -> None:
        refused = await service.ingest_file(_exercise_file(tmp_path, "single", teacher=_MEMBER))
        assert refused.is_error
        assert "File single.md:" in (refused.expect_error().user_message or "")
        assert await _exercise(neo4j_driver, "single") is None

        admitted = await service.ingest_file(_exercise_file(tmp_path, "single", teacher=_TEACHER))
        assert admitted.is_ok, admitted
        single = await _exercise(neo4j_driver, "single")
        assert single is not None and single["teachers"] == [_TEACHER]

    async def test_a_changed_teacher_retracts_the_old_edge(
        self, service: UnifiedIngestionService, neo4j_driver: AsyncDriver, tmp_path: Path
    ) -> None:
        path = _exercise_file(tmp_path, "moved", teacher=_TEACHER)
        await _sync(service, tmp_path)

        _exercise_file(tmp_path, "moved", teacher=_SECOND_TEACHER)
        future = path.stat().st_mtime + 10
        os.utime(path, (future, future))
        stats = await _sync(service, tmp_path)

        assert not stats.errors, stats.errors
        moved = await _exercise(neo4j_driver, "moved")
        assert moved is not None and moved["teachers"] == [_SECOND_TEACHER]
