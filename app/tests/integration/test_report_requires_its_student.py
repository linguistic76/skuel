"""A report is addressed to the student whose submission it answers, or it is not written.

Both report-writing statements (``EntryReportBackend.create_report_node`` and
``create_report_and_revised_exercise``) find the submission's student before they
write anything. A submission no ``:User`` ``OWNS`` — a shape the owner invariant
forbids — gets no row back and keeps its status, and no EntryReport or
RevisedExercise is left behind: not owned by the teacher, not owned by nobody.
Each statement is shown beside its owned twin, which lands and is the student's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.exercise_backends import EntryReportBackend
from core.models.enums import EntityType
from core.models.exercises.revised_exercise import RevisedExercise
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

_TEACHER = seed_user_uid("report_owner_teacher")
_STUDENT = seed_user_uid("report_owner_student")
_EXERCISE = "ex.report-owner-exercise"
_OWNED = "ue.report-owner-owned"
_UNOWNED = "ue.report-owner-unowned"
_USERS = [_TEACHER, _STUDENT]


def _backend(driver: AsyncDriver) -> EntryReportBackend:
    backend = build_production_backends(driver)["entry_report_backend"]
    assert isinstance(backend, EntryReportBackend)
    return backend


@pytest_asyncio.fixture(loop_scope="session")
async def graph(neo4j_driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    """A teacher's exercise, and two turn-ins of it: one the student owns, one nobody does."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (teacher:User {uid: $teacher}) SET teacher.title = 'Report teacher'
            MERGE (student:User {uid: $student}) SET student.title = 'Report student'
            CREATE (ex:Entity:Exercise {uid: $exercise, entity_type: 'exercise',
                                        title: 'Owner exercise', status: 'active'})
            CREATE (ex)-[:REVIEWED_BY]->(teacher)
            WITH student, ex
            UNWIND [$owned, $unowned] AS uid
            CREATE (entry:Entity:UserEntry {uid: uid, entity_type: 'user_entry',
                                            title: 'Turn-in', user_uid: $student,
                                            status: 'submitted', pipeline: 'teacher_review'})
            CREATE (entry)-[:FULFILLS_EXERCISE]->(ex)
            WITH student, entry WHERE entry.uid = $owned
            CREATE (student)-[:OWNS]->(entry)
            """,
            teacher=_TEACHER,
            student=_STUDENT,
            exercise=_EXERCISE,
            owned=_OWNED,
            unowned=_UNOWNED,
        )
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $users OR n.user_uid IN $users "
            "OR n.uid STARTS WITH 'er.report-owner' OR n.uid STARTS WITH 're.report-owner' "
            "OR n.uid = $exercise DETACH DELETE n",
            users=_USERS,
            exercise=_EXERCISE,
        )


def _params(submission_uid: str, report_uid: str, **extra: object) -> dict[str, object]:
    return {
        "report_uid": submission_uid,
        "report_entity_uid": report_uid,
        "author_uid": _TEACHER,
        "feedback": "feedback",
        "report_file_path": None,
        "title_prefix": "Feedback on",
        "entity_type": EntityType.ENTRY_REPORT.value,
        "submission_status": "completed",
        "completed_status": "completed",
        "processor_type": "human",
        "assessment_outcome": "approved",
        "allowed_from_statuses": ["submitted"],
        "reviewing_teacher_uid": _TEACHER,
        "now": "2026-11-20T10:00:00",
        **extra,
    }


def _ai_params(submission_uid: str, report_uid: str) -> dict[str, object]:
    return _params(
        submission_uid,
        report_uid,
        author_uid=None,
        processor_type="llm",
        submission_status=None,
        allowed_from_statuses=None,
        reviewing_teacher_uid=None,
    )


async def _revise(
    driver: AsyncDriver, submission_uid: str, suffix: str
) -> list[Any]:  # boundary: rows
    revision = RevisedExercise(
        uid=f"re.report-owner-{suffix}",
        entity_type=EntityType.REVISED_EXERCISE,
        title="",
        user_uid=_TEACHER,
        original_exercise_uid=_EXERCISE,
        report_uid=f"er.report-owner-rev-{suffix}",
        instructions="revise",
    )
    result = await _backend(driver).create_report_and_revised_exercise(
        _params(
            submission_uid,
            f"er.report-owner-rev-{suffix}",
            submission_status="revision_requested",
            assessment_outcome="needs_revision",
            re_uid=f"re.report-owner-{suffix}",
            original_exercise_uid=_EXERCISE,
        ),
        revision,
    )
    assert result.is_ok, result
    return list(result.value)


async def _scalar(driver: AsyncDriver, query: str, **params: object) -> object:
    async with driver.session() as session:
        record = await (await session.run(query, **params)).single()
    assert record is not None
    return record[0]


async def _written(driver: AsyncDriver) -> list[str]:
    """Every report or revision node this module's writes left, by uid."""
    rows = await _scalar(
        driver,
        "MATCH (n:Entity) WHERE n.uid STARTS WITH 'er.report-owner' "
        "OR n.uid STARTS WITH 're.report-owner' RETURN collect(n.uid)",
    )
    assert isinstance(rows, list)
    return sorted(rows)


async def _status(driver: AsyncDriver, uid: str) -> object:
    return await _scalar(driver, "MATCH (n:Entity {uid: $uid}) RETURN n.status", uid=uid)


async def _report_owner(driver: AsyncDriver, report_uid: str) -> list[object]:
    return [
        await _scalar(
            driver,
            "MATCH (o:User)-[:OWNS]->(r:EntryReport {uid: $uid}) RETURN collect(o.uid)",
            uid=report_uid,
        ),
        await _scalar(
            driver, "MATCH (r:EntryReport {uid: $uid}) RETURN r.user_uid", uid=report_uid
        ),
    ]


class TestASubmissionNobodyOwnsGetsNoReport:
    async def test_an_ai_report(self, graph: AsyncDriver) -> None:
        result = await _backend(graph).create_report_node(
            _ai_params(_UNOWNED, "er.report-owner-ai")
        )

        assert result.is_ok and result.value == []
        assert await _written(graph) == []

    async def test_a_teacher_report(self, graph: AsyncDriver) -> None:
        result = await _backend(graph).create_report_node(
            _params(_UNOWNED, "er.report-owner-teacher")
        )

        assert result.is_ok and result.value == []
        assert await _written(graph) == []
        assert await _status(graph, _UNOWNED) == "submitted"

    async def test_a_revision(self, graph: AsyncDriver) -> None:
        assert await _revise(graph, _UNOWNED, "unowned") == []
        assert await _written(graph) == []
        assert await _status(graph, _UNOWNED) == "submitted"


class TestAnOwnedSubmissionsReportIsTheStudents:
    async def test_an_ai_report(self, graph: AsyncDriver) -> None:
        result = await _backend(graph).create_report_node(
            _ai_params(_OWNED, "er.report-owner-ai-owned")
        )

        assert result.is_ok and len(result.value) == 1
        assert await _report_owner(graph, "er.report-owner-ai-owned") == [[_STUDENT], _STUDENT]

    async def test_a_revision(self, graph: AsyncDriver) -> None:
        [row] = await _revise(graph, _OWNED, "owned")

        assert row["student_uid"] == _STUDENT
        assert await _report_owner(graph, "er.report-owner-rev-owned") == [[_STUDENT], _STUDENT]
        assert (
            await _scalar(
                graph,
                "MATCH (:User {uid: $student})-[:SHARES_WITH]->(re:RevisedExercise {uid: $uid}) "
                "RETURN count(re)",
                student=_STUDENT,
                uid="re.report-owner-owned",
            )
            == 1
        )
