"""Classroom-scoping for the teacher-gated revision-chain read.

``GET /api/revised-exercises/chain`` was scoped by ``@require_teacher``
alone — the role gate answers "may you review at all", never "whose
revisions" (the #887 blind spot; template PR #893). The *write* that mints a
revision is narrower: ``request_revision`` runs
``verify_teacher_has_group_access``, so only a teacher sharing an active
group with the student may author one. These tests pin the chain read to
that same audience: a teacher sees an exercise's revisions only for students
in active groups they OWN, with an optional in-classroom ``student_uid``
filter.

They also pin ``revision_number`` to per-(exercise, student). Both writers —
``RevisedExerciseService.create`` and the atomic
``create_report_and_revised_exercise`` Cypher — must mint
``max(existing for the pair) + 1``: not a global per-exercise count (which
numbers one student's first revision by the whole classroom's total), and
not ``len + 1`` (which collides with legacy gap-numbered chains; the seeds
here carry gaps on purpose).

Run against a real Neo4j container: the scoping resolves against persisted
``:OWNS`` / ``:MEMBER_OF`` / ``:REVISES_EXERCISE`` edges, which a mocked
backend would only assert were queried, not that they gate. Refusals are
404-equivalent (OWNERSHIP_VERIFICATION.md): an out-of-classroom teacher's
read is byte-identical to a nonexistent exercise's — an empty chain, so a
denied read cannot be told from a missing exercise.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from adapters.inbound.revised_exercises_api import create_revised_exercises_api_routes
from adapters.persistence.neo4j.backends.exercise_backends import (
    EntryReportBackend,
    RevisedExerciseBackend,
)
from core.models.enums import UserRole
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import ReportSource
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.report.entry_report import EntryReport
from core.models.user.user import User
from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService
from core.utils.result_simplified import Errors, Result

STUDENT_A = "user_rcs_student_a"  # in the group IN_TEACHER owns
STUDENT_B = "user_rcs_student_b"  # in the group OUT_TEACHER owns
IN_TEACHER = "user_rcs_in_teacher"
OUT_TEACHER = "user_rcs_out_teacher"
LONE_TEACHER = "user_rcs_lone_teacher"  # a TEACHER with no classroom at all
GROUP_A = "group_rcs_a"
GROUP_B = "group_rcs_b"

EXERCISE_UID = "ex_rcs_original"
RE_A2 = "re_rcs_a2"  # STUDENT_A, revision_number 2 (legacy global numbering)
RE_A5 = "re_rcs_a5"  # STUDENT_A, revision_number 5 (gap on purpose)
RE_B4 = "re_rcs_b4"  # STUDENT_B, revision_number 4
SECRET_TITLE_B = "RCS_SECRET_OTHER_CLASSROOM_TITLE_7e2a"

SUB_B = "ue_rcs_sub_b"  # STUDENT_B submission for the service-create path
SUB_B2 = "ue_rcs_sub_b2"  # STUDENT_B submission for the atomic path
REPORT_B = "er_rcs_report_b"

CHAIN_PATH = "/api/revised-exercises/chain"

ROLES = {
    STUDENT_A: UserRole.MEMBER,
    STUDENT_B: UserRole.MEMBER,
    IN_TEACHER: UserRole.TEACHER,
    OUT_TEACHER: UserRole.TEACHER,
    LONE_TEACHER: UserRole.TEACHER,
}


def _user_service() -> Any:
    """Real ``User`` records so ``@require_teacher`` runs its hierarchy check."""

    async def get_user(user_uid: str) -> Result[User]:
        role = ROLES.get(user_uid)
        if role is None:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(User(uid=user_uid, title=user_uid, role=role))

    return SimpleNamespace(get_user=get_user)


def _make_request(user_uid: str, **query_params: str) -> Any:
    """Minimal session-backed request stub for the auth guards."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path=CHAIN_PATH),
        query_params=query_params,
        cookies={},
        headers={},
    )


def _collector() -> tuple[Any, dict[str, Any]]:
    """A stand-in app/rt pair that records path → registered handler."""
    registered: dict[str, Any] = {}

    def rt(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    app = SimpleNamespace(get=rt, post=rt, route=rt)
    return (app, rt), registered


@pytest.fixture
def revised_service(neo4j_driver) -> RevisedExerciseService:
    backend = RevisedExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.REVISED_EXERCISE,
        entity_class=RevisedExercise,
        base_label=NeoLabel.ENTITY,
    )
    return RevisedExerciseService(backend=backend)


@pytest.fixture
def report_backend(neo4j_driver) -> EntryReportBackend:
    return EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )


@pytest.fixture
def api_handlers(revised_service) -> dict[str, Any]:
    (app, rt), registered = _collector()
    create_revised_exercises_api_routes(app, rt, revised_service, user_service=_user_service())
    return registered


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    """Seed two classrooms revising the same original exercise.

    STUDENT_A (IN_TEACHER's group) holds revisions {2, 5}; STUDENT_B
    (OUT_TEACHER's group) holds revision {4}. The gaps are deliberate:
    they distinguish max+1 from len+1 in the ordinal tests, and the
    interleaved numbers distinguish per-student from global counting.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (sa:User {uid: $student_a})
            MERGE (sb:User {uid: $student_b})
            MERGE (inT:User {uid: $in_teacher})
            MERGE (outT:User {uid: $out_teacher})
            MERGE (loneT:User {uid: $lone_teacher})
            MERGE (ga:Group {uid: $group_a}) SET ga.is_active = true
            MERGE (gb:Group {uid: $group_b}) SET gb.is_active = true
            MERGE (inT)-[:OWNS]->(ga)
            MERGE (outT)-[:OWNS]->(gb)
            MERGE (sa)-[:MEMBER_OF]->(ga)
            MERGE (sb)-[:MEMBER_OF]->(gb)
            CREATE (ex:Entity:Exercise {
                uid: $exercise, entity_type: 'exercise', title: 'Original exercise',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (a2:Entity:RevisedExercise {
                uid: $re_a2, entity_type: 'revised_exercise', title: 'Revision 2',
                revision_number: 2, student_uid: $student_a, user_uid: $in_teacher,
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (a5:Entity:RevisedExercise {
                uid: $re_a5, entity_type: 'revised_exercise', title: 'Revision 5',
                revision_number: 5, student_uid: $student_a, user_uid: $in_teacher,
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (b4:Entity:RevisedExercise {
                uid: $re_b4, entity_type: 'revised_exercise', title: $secret_title,
                revision_number: 4, student_uid: $student_b, user_uid: $out_teacher,
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            MERGE (a2)-[:REVISES_EXERCISE]->(ex)
            MERGE (a5)-[:REVISES_EXERCISE]->(ex)
            MERGE (b4)-[:REVISES_EXERCISE]->(ex)
            MERGE (inT)-[:OWNS]->(a2)
            MERGE (inT)-[:OWNS]->(a5)
            MERGE (outT)-[:OWNS]->(b4)
            CREATE (subB:Entity:UserEntry {
                uid: $sub_b, entity_type: 'user_entry', title: 'B submission',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (subB2:Entity:UserEntry {
                uid: $sub_b2, entity_type: 'user_entry', title: 'B submission 2',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime(), updated_at: datetime()
            })
            MERGE (sb)-[:OWNS]->(subB)
            MERGE (sb)-[:OWNS]->(subB2)
            MERGE (subB)-[:FULFILLS_EXERCISE]->(ex)
            MERGE (subB2)-[:FULFILLS_EXERCISE]->(ex)
            CREATE (repB:Entity:EntryReport {
                uid: $report_b, entity_type: 'entry_report', title: 'Feedback for B',
                status: 'completed', processor_type: 'human', user_uid: $student_b,
                created_at: datetime(), updated_at: datetime()
            })
            MERGE (repB)-[:REPORT_FOR]->(subB)
            MERGE (sb)-[:OWNS]->(repB)
            """,
            student_a=STUDENT_A,
            student_b=STUDENT_B,
            in_teacher=IN_TEACHER,
            out_teacher=OUT_TEACHER,
            lone_teacher=LONE_TEACHER,
            group_a=GROUP_A,
            group_b=GROUP_B,
            exercise=EXERCISE_UID,
            re_a2=RE_A2,
            re_a5=RE_A5,
            re_b4=RE_B4,
            secret_title=SECRET_TITLE_B,
            sub_b=SUB_B,
            sub_b2=SUB_B2,
            report_b=REPORT_B,
        )


async def _chain(handlers: dict[str, Any], user_uid: str, **params: str) -> list[dict[str, Any]]:
    response = await handlers[CHAIN_PATH](_make_request(user_uid, **params))
    assert getattr(response, "status_code", None) == 200
    payload = json.loads(response.body)
    assert isinstance(payload, list)
    return payload


# ============================================================================
# Scope — GET /api/revised-exercises/chain
# ============================================================================


class TestRevisionChainScope:
    """The chain read is classroom-scoped, not merely teacher-gated."""

    async def test_in_classroom_teacher_sees_their_students_chain(
        self, api_handlers, seeded
    ) -> None:
        rows = await _chain(api_handlers, IN_TEACHER, exercise_uid=EXERCISE_UID)
        assert {row["uid"] for row in rows} == {RE_A2, RE_A5}, (
            "the classroom's teacher must still see their students' revisions"
        )
        assert [row["revision_number"] for row in rows] == [2, 5]

    async def test_other_classrooms_rows_never_leak(self, api_handlers, seeded) -> None:
        body = json.dumps(await _chain(api_handlers, IN_TEACHER, exercise_uid=EXERCISE_UID))
        assert SECRET_TITLE_B not in body, (
            "another classroom's revision titles must not leak through the chain"
        )
        assert STUDENT_B not in body, "another classroom's student UIDs must not leak"

    async def test_out_teacher_sees_only_their_classroom(self, api_handlers, seeded) -> None:
        rows = await _chain(api_handlers, OUT_TEACHER, exercise_uid=EXERCISE_UID)
        assert {row["uid"] for row in rows} == {RE_B4}

    async def test_classroomless_teacher_refusal_matches_missing_exercise(
        self, api_handlers, seeded
    ) -> None:
        """The refusal is indistinguishable from a genuinely missing exercise."""
        denied = await _chain(api_handlers, LONE_TEACHER, exercise_uid=EXERCISE_UID)
        missing = await _chain(api_handlers, IN_TEACHER, exercise_uid="ex_does_not_exist")
        assert denied == missing == []

    async def test_student_filter_stays_inside_the_classroom(self, api_handlers, seeded) -> None:
        own = await _chain(
            api_handlers, IN_TEACHER, exercise_uid=EXERCISE_UID, student_uid=STUDENT_A
        )
        assert {row["uid"] for row in own} == {RE_A2, RE_A5}
        cross = await _chain(
            api_handlers, IN_TEACHER, exercise_uid=EXERCISE_UID, student_uid=STUDENT_B
        )
        assert cross == [], "filtering by another classroom's student must refuse, not leak"


# ============================================================================
# Ordinal — revision_number is per-(exercise, student), max+1
# ============================================================================


class TestRevisionOrdinalPerStudent:
    """Both revision writers mint max(pair) + 1, never a global count."""

    async def test_service_create_mints_per_student_max_plus_one(
        self, revised_service, seeded
    ) -> None:
        """STUDENT_B's chain is {4}: the next ordinal is 5.

        A global count would mint 4 (three existing revisions on the
        exercise); a per-student len+1 would mint 2. Both are wrong.
        """
        entity = RevisedExercise(
            uid="re_rcs_new_service",
            entity_type=EntityType.REVISED_EXERCISE,
            title="",
            user_uid=OUT_TEACHER,
            student_uid=STUDENT_B,
            report_uid=REPORT_B,
            original_exercise_uid=EXERCISE_UID,
            instructions="Address the gaps",
        )
        result = await revised_service.create(entity)
        assert result.is_ok, f"create failed: {result}"
        assert result.value.revision_number == 5
        assert result.value.title == "Revision 5"

    async def test_atomic_create_mints_per_student_max_plus_one(
        self, report_backend, seeded
    ) -> None:
        """The atomic report+revision Cypher numbers the same way."""
        re_entity = RevisedExercise(
            uid="re_rcs_new_atomic",
            entity_type=EntityType.REVISED_EXERCISE,
            title="",
            user_uid=OUT_TEACHER,
            student_uid=STUDENT_B,
            report_uid="er_rcs_atomic",
            original_exercise_uid=EXERCISE_UID,
            instructions="Atomic revision notes",
        )
        result = await report_backend.create_report_and_revised_exercise(
            {
                "report_uid": SUB_B2,
                "report_entity_uid": "er_rcs_atomic",
                "author_uid": OUT_TEACHER,
                "feedback": "Atomic revision notes",
                "report_file_path": None,
                # Composed backend-side into "Revision requested on '{subject}'" (C3).
                "title_prefix": "Revision requested on",
                "entity_type": EntityType.ENTRY_REPORT.value,
                "submission_status": EntityStatus.REVISION_REQUESTED.value,
                "completed_status": EntityStatus.COMPLETED.value,
                "processor_type": ReportSource.HUMAN.value,
                "assessment_outcome": AssessmentOutcome.NEEDS_REVISION.value,
                "allowed_from_statuses": [
                    EntityStatus.SUBMITTED.value,
                    EntityStatus.ACTIVE.value,
                ],
                "now": datetime.now().isoformat(),
                "re_uid": "re_rcs_new_atomic",
                "original_exercise_uid": EXERCISE_UID,
            },
            re_entity,
        )
        assert result.is_ok, f"atomic create failed: {result}"
        records = result.value
        assert records, "the status guard should have admitted the submitted entry"
        assert records[0]["revision_number"] == 5
