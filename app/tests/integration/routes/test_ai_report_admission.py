"""Who may have the AI reviewer read an entry — ``POST /api/exercises/report``.

The reviewer runs an exercise's instructions against an entry's content and hands
the result back to the caller, so admitting a request is a read of both. Two
callers are admitted (``EntryReportService.admit_report``), each only with the
exercise the entry FULFILLS:

- the entry's owner;
- a teacher the entry asks for feedback — it was ``SUBMITTED_TO_GROUP`` an active
  group the teacher owns (ADR-088 §2). Having the student in one of your groups is
  not enough: the entry has to have been sent to it.

Nobody else — review authority is the asked teacher's, so an ADMIN the entry does
not ask is refused like any other user (ADR-088 §2).

Every refusal is a 404 that reads the same as a uid naming nothing.

The world is built at the app's real doors: the teacher creates a group, adds the
student, assigns an exercise to the group; the student turns work in to that
group. The reviewer is FULL-tier and calls an LLM, so the route's tier gate is
forced to FULL and ``generate_report`` is replaced by a recording stub — a
refusal is "the stub was never reached", an admission is "it was, with exactly
this entry and exercise". Nothing calls a model.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

import adapters.inbound.exercises_api as exercises_api
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.user_enums import UserRole
from core.services.report.entry_report_service import AdmittedReport
from core.utils.result_simplified import Result
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

MARK = "zzzaireport"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
STUDENT_MARK = f"{MARK}s"
TEACHER_MARK = f"{MARK}t"
OUTSIDER_MARK = f"{MARK}o"
ADMIN_MARK = f"{MARK}a"
STUDENT = f"user_{STUDENT_MARK}"
TEACHER = f"user_{TEACHER_MARK}"  # owns the group the entry was submitted to
OUTSIDER = f"user_{OUTSIDER_MARK}"  # a teacher with the student in a group of their own
ADMIN = f"user_{ADMIN_MARK}"  # no tie to the student or the entry
ROLES = {STUDENT: "member", TEACHER: "teacher", OUTSIDER: "teacher", ADMIN: "admin"}
MISSING_ENTRY = f"ue_{MARK}_missing"
MISSING_EXERCISE = f"ex_{MARK}_missing"
REPORT = "/api/exercises/report"


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
    """Groups and exercises carry no mark in their generated uids — remove them by owner."""
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


def _uidless(body: str, *uids: str) -> str:
    for uid in uids:
        body = body.replace(uid, "<uid>")
    return re.sub(r'"timestamp":"[^"]*"', '"timestamp":"<t>"', body)


class World:
    def __init__(
        self,
        clients: dict[str, httpx.AsyncClient],
        entry: str,
        exercise: str,
        other_exercise: str,
    ) -> None:
        self.clients = clients
        self.entry = entry
        self.exercise = exercise  # the exercise the entry fulfils
        self.other_exercise = other_exercise  # the same teacher's, not fulfilled by the entry

    async def ask(self, caller: str, entry: str, exercise: str) -> httpx.Response:
        return await self.clients[caller].post(
            REPORT, json={"submission_uid": entry, "exercise_uid": exercise}
        )


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, STUDENT, STUDENT_MARK) as student,
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
        signed_in_client(skuel_app, OUTSIDER, OUTSIDER_MARK) as outsider,
        signed_in_client(skuel_app, ADMIN, ADMIN_MARK) as admin,
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
                    "file": ("essay.md", f"{MARK} the student's essay".encode(), "text/markdown")
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

            yield World(
                {STUDENT: student, TEACHER: teacher, OUTSIDER: outsider, ADMIN: admin},
                entry,
                exercise,
                other_exercise,
            )
        finally:
            await _delete_owned(driver, list(ROLES))


@pytest.fixture
def reviewer(
    skuel_app: Any,  # boundary: fasthtml-app
    monkeypatch: pytest.MonkeyPatch,
) -> list[AdmittedReport]:
    """Force the tier gate open and record every admission that reaches the reviewer."""
    calls: list[AdmittedReport] = []

    async def generate_report(
        admitted: AdmittedReport, temperature: float = 0.7, max_tokens: int = 4000
    ) -> Result[SimpleNamespace]:
        calls.append(admitted)
        return Result.ok(SimpleNamespace(uid=f"er_{MARK}_stub", content="stub feedback"))

    def full_tier(system_tier: IntelligenceTier, role: UserRole) -> IntelligenceTier:
        return IntelligenceTier.FULL

    monkeypatch.setattr(exercises_api, "get_user_intelligence_tier", full_tier)
    monkeypatch.setattr(skuel_app.state.services.entry_report, "generate_report", generate_report)
    return calls


def _reached(calls: list[AdmittedReport]) -> list[tuple[str, str, str]]:
    return [(c.entry.uid, c.exercise.uid, c.caller_uid) for c in calls]


async def test_the_teacher_the_entry_was_submitted_to_reaches_the_reviewer(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    response = await world.ask(TEACHER, world.entry, world.exercise)

    assert response.status_code == 200, response.text
    assert _reached(reviewer) == [(world.entry, world.exercise, TEACHER)]


async def test_the_owner_reaches_the_reviewer(world: World, reviewer: list[AdmittedReport]) -> None:
    response = await world.ask(STUDENT, world.entry, world.exercise)

    assert response.status_code == 200, response.text
    assert _reached(reviewer) == [(world.entry, world.exercise, STUDENT)]


async def test_a_teacher_the_entry_was_not_submitted_to_is_refused(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    """The outsider has the student in a group — the entry was sent to another one."""
    refused = await world.ask(OUTSIDER, world.entry, world.exercise)
    missing = await world.ask(OUTSIDER, MISSING_ENTRY, world.exercise)

    assert refused.status_code == 404, refused.text
    assert reviewer == []
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)


async def test_an_admin_the_entry_does_not_ask_is_refused(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    """Review authority is the asked teacher's; the role alone admits nobody (ADR-088 §2)."""
    refused = await world.ask(ADMIN, world.entry, world.exercise)
    missing = await world.ask(ADMIN, MISSING_ENTRY, world.exercise)

    assert refused.status_code == 404, refused.text
    assert reviewer == []
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)


@pytest.mark.parametrize("caller", [TEACHER, STUDENT])
async def test_an_exercise_the_entry_does_not_fulfil_is_refused(
    world: World, reviewer: list[AdmittedReport], caller: str
) -> None:
    refused = await world.ask(caller, world.entry, world.other_exercise)
    missing = await world.ask(caller, world.entry, MISSING_EXERCISE)

    assert refused.status_code == 404, refused.text
    assert reviewer == []
    assert _uidless(refused.text, world.other_exercise) == _uidless(missing.text, MISSING_EXERCISE)


async def test_a_refused_entry_says_nothing_about_the_exercise(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    """The exercise is looked at only once the entry is admitted: a foreign entry with
    a missing exercise answers as a missing entry, not as a missing exercise."""
    foreign = await world.ask(OUTSIDER, world.entry, MISSING_EXERCISE)
    missing = await world.ask(OUTSIDER, MISSING_ENTRY, MISSING_EXERCISE)

    assert foreign.status_code == 404, foreign.text
    assert reviewer == []
    assert _uidless(foreign.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)
