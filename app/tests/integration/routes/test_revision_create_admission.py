"""Who may file a revision on a student's report — ``POST /api/revised-exercises/create``.

A RevisedExercise answers one EntryReport on one student's entry: it is written
``RESPONDS_TO_REPORT`` that report, ``REVISES_EXERCISE`` the exercise, and shared
into the student's own inbox (``SHARES_WITH``). So filing one is a write into
another user's space, admitted by the writing service
(``RevisedExerciseService.admit_revision``) only for:

- a teacher the entry asks for feedback — it was ``SUBMITTED_TO_GROUP`` an active
  group the teacher owns (ADR-088 §2). Having the student in one of your groups is
  not enough: the entry has to have been sent to it;
- with the student who owns that entry, and the exercise that entry FULFILLS.

Every refusal is a 404 that reads the same as a report uid naming nothing, and the
exercise is looked at only once the entry is admitted.

The world is built at the app's real doors: the teacher creates a group, adds the
student, assigns two exercises to the group; the student turns work in to that
group against one of them; the teacher files a feedback report on it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

import adapters.inbound.teaching_api as teaching_api
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import create, edges_between, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzrevadmit"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
STUDENT_MARK = f"{MARK}s"
TEACHER_MARK = f"{MARK}t"
OUTSIDER_MARK = f"{MARK}o"
STUDENT = f"user_{STUDENT_MARK}"
TEACHER = f"user_{TEACHER_MARK}"  # owns the group the entry was submitted to
OUTSIDER = f"user_{OUTSIDER_MARK}"  # a teacher with the student in a group of their own
ROLES = {STUDENT: "member", TEACHER: "teacher", OUTSIDER: "teacher"}
MISSING_REPORT = f"er_{MARK}_missing"
MISSING_EXERCISE = f"ex_{MARK}_missing"
CREATE = "/api/revised-exercises/create"


async def _set_role(driver: AsyncDriver, uid: str, role: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = $role, u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
            role=role,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Groups, exercises and reports carry no mark in their generated uids — remove
    them by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )


async def _group_with_student(client: httpx.AsyncClient, name: str) -> str:
    group = await create(client, "groups", name, name=name)
    added = await client.post(f"/api/groups/{group}/members/add", json={"user_uid": STUDENT})
    assert added.status_code == 200, added.text
    return group


async def _assigned_exercise(client: httpx.AsyncClient, group: str, name: str) -> str:
    return await create(
        client,
        "exercises",
        name,
        name=name,
        instructions=f"{name} instructions",
        scope="assigned",
        group_uid=group,
    )


async def _report_on(driver: AsyncDriver, entry: str) -> str:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (r:EntryReport)-[:REPORT_FOR]->(:UserEntry {uid: $entry}) RETURN r.uid AS uid",
                entry=entry,
            )
        ).single()
    assert record is not None, entry
    return str(record["uid"])


async def _revisions(driver: AsyncDriver) -> set[tuple[str, str, str | None]]:
    """Every revision targeting the student: (uid, owner, the exercise it revises)."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (re:RevisedExercise {student_uid: $student})
            OPTIONAL MATCH (re)-[:REVISES_EXERCISE]->(ex)
            RETURN re.uid AS uid, re.user_uid AS owner, ex.uid AS exercise
            """,
            student=STUDENT,
        )
        return {(row["uid"], row["owner"], row["exercise"]) async for row in result}


def _uidless(body: str, *uids: str) -> str:
    for uid in uids:
        body = body.replace(uid, "<uid>")
    return re.sub(r'"timestamp":"[^"]*"', '"timestamp":"<t>"', body)


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        clients: dict[str, httpx.AsyncClient],
        report: str,
        exercise: str,
        other_exercise: str,
    ) -> None:
        self.driver = driver
        self.clients = clients
        self.report = report  # the teacher's report on the student's entry
        self.exercise = exercise  # the exercise the entry fulfils
        self.other_exercise = other_exercise  # the same teacher's, not fulfilled by the entry

    async def file(
        self, caller: str, report: str, exercise: str, student: str = STUDENT
    ) -> httpx.Response:
        return await self.clients[caller].post(
            CREATE,
            json={
                "report_uid": report,
                "student_uid": student,
                "original_exercise_uid": exercise,
                "instructions": f"{MARK} revise the opening",
            },
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    with pytest.MonkeyPatch.context() as patch:
        # The report door writes the feedback file to disk before it files the report.
        patch.setattr(teaching_api, "_REPORTS_DIR", tmp_path_factory.mktemp("reports"))
        async with (
            signed_in_client(skuel_app, STUDENT, STUDENT_MARK) as student,
            signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
            signed_in_client(skuel_app, OUTSIDER, OUTSIDER_MARK) as outsider,
        ):
            for uid, role in ROLES.items():
                await _set_role(driver, uid, role)
            try:
                group = await _group_with_student(teacher, f"{MARK}-class")
                await _group_with_student(outsider, f"{MARK}-other-class")
                exercise = await _assigned_exercise(teacher, group, f"{MARK}-essay")
                other_exercise = await _assigned_exercise(teacher, group, f"{MARK}-quiz")

                turned_in = await student.post(
                    "/api/user-entries/upload",
                    files={
                        "file": (
                            "essay.md",
                            f"{MARK} the student's essay".encode(),
                            "text/markdown",
                        )
                    },
                    data={
                        "pipeline": "teacher_review",
                        "fulfills_exercise_uid": exercise,
                        "audience": f"teacher:{group}",
                    },
                )
                assert turned_in.status_code == 201, turned_in.text
                entry = str(turned_in.json()["user_entry"]["uid"])
                sent_to = {e.type for e in await edges_between(driver, entry, group)}
                assert "SUBMITTED_TO_GROUP" in sent_to, sent_to

                reported = await teacher.post(
                    f"/api/teaching/review/{entry}/report",
                    files={"feedback_file": ("feedback.md", b"Say more.", "text/markdown")},
                )
                assert "Feedback submitted" in reported.text, reported.text
                report = await _report_on(driver, entry)

                yield World(
                    driver,
                    {STUDENT: student, TEACHER: teacher, OUTSIDER: outsider},
                    report,
                    exercise,
                    other_exercise,
                )
            finally:
                await _delete_owned(driver, list(ROLES))


async def test_the_teacher_the_entry_was_submitted_to_files_a_revision(world: World) -> None:
    response = await world.file(TEACHER, world.report, world.exercise)

    assert response.status_code == 201, response.text
    revision = str(response.json()["uid"])
    assert (revision, TEACHER, world.exercise) in await _revisions(world.driver)
    responds = {e.type for e in await edges_between(world.driver, revision, world.report)}
    assert "RESPONDS_TO_REPORT" in responds, responds
    shared = {e.type for e in await edges_between(world.driver, revision, STUDENT)}
    assert "SHARES_WITH" in shared, shared
    inbox = await world.clients[STUDENT].get("/api/revised-exercises/my-revisions")
    assert revision in inbox.text, inbox.text


async def test_a_teacher_the_entry_was_not_submitted_to_is_refused(world: World) -> None:
    """The outsider has the student in a group — the entry was sent to another one."""
    refused = await world.file(OUTSIDER, world.report, world.exercise)
    missing = await world.file(OUTSIDER, MISSING_REPORT, world.exercise)

    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, world.report) == _uidless(missing.text, MISSING_REPORT)
    assert {owner for _, owner, _ in await _revisions(world.driver)} <= {TEACHER}
    inbox = await world.clients[STUDENT].get("/api/revised-exercises/my-revisions")
    assert OUTSIDER not in inbox.text, inbox.text


async def test_a_student_who_does_not_own_the_entry_is_refused(world: World) -> None:
    refused = await world.file(TEACHER, world.report, world.exercise, student=OUTSIDER)
    missing = await world.file(TEACHER, MISSING_REPORT, world.exercise, student=OUTSIDER)

    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, world.report) == _uidless(missing.text, MISSING_REPORT)
    async with world.driver.session() as session:
        stray = await (
            await session.run(
                "MATCH (re:RevisedExercise {student_uid: $other}) RETURN count(re) AS n",
                other=OUTSIDER,
            )
        ).single()
    assert stray is not None and stray["n"] == 0


async def test_an_exercise_the_entry_does_not_fulfil_is_refused(world: World) -> None:
    refused = await world.file(TEACHER, world.report, world.other_exercise)
    missing = await world.file(TEACHER, world.report, MISSING_EXERCISE)

    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, world.other_exercise) == _uidless(missing.text, MISSING_EXERCISE)
    assert world.other_exercise not in {ex for _, _, ex in await _revisions(world.driver)}


async def test_a_refused_entry_says_nothing_about_the_exercise(world: World) -> None:
    """The exercise is looked at only once the entry is admitted: a foreign report
    with a missing exercise answers as a missing report, not as a missing exercise."""
    foreign = await world.file(OUTSIDER, world.report, MISSING_EXERCISE)
    missing = await world.file(OUTSIDER, MISSING_REPORT, MISSING_EXERCISE)

    assert foreign.status_code == 404, foreign.text
    assert _uidless(foreign.text, world.report) == _uidless(missing.text, MISSING_REPORT)
