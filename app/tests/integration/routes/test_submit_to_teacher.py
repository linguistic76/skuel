"""A feedback request on an exercise reaches the teacher its vault file names, directly.

Every exercise names its teacher in its content-vault file (``REVIEWED_BY``, ADR-091
S3). A ``teacher_review`` turn-in with no other target is a feedback request filed to
that teacher directly, ``(entry)-[:SUBMITTED_TO_TEACHER {submitted_at}]->(teacher)``
(ADR-088 §9). That teacher reads it everywhere a group's teacher reads a request sent to
their group: the review queue, the review detail, the exercise's submission list, the
AI-report door, the revision door, the exchange thread and the report download. Any
other teacher — here one who has the learner in two classes of their own — is refused
exactly as for an entry that does not exist.

The learner is not thereby that teacher's student: the student page, its knowledge tab
and the students list stay with the classroom, so a teacher reached only by a direct
request finds the learner in none of them (ruled with ADR-088 §9). The exchange thread
opens for them, scoped to the entries that asked them — never the learner's other work.

A learner who sends the work to a class instead (``teacher:<group_uid>``) reaches the
class's teacher, as before; a request on an exercise never reaches the learner's
default group; the named teacher turning in against their own exercise has nobody to
ask, and a named teacher without the teacher role is nobody's reviewer.

The exercises enter through the content-vault sync, their one door, and the group at
its real create door; the learner starts the step at the real progress door and turns
in at the real upload door.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

import adapters.inbound.exercises_api as exercises_api
import adapters.inbound.teaching_api as teaching_api
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.user_enums import UserRole
from core.models.group.group import default_group_uid
from core.services.report.entry_report_service import AdmittedReport
from core.utils.result_simplified import Result
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    signed_in_client,
    sync_vault_exercises,
)

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

MARK = "zzzsubmitteacher"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
TEACHER_MARK = f"{MARK}t"
LEARNER_MARK = f"{MARK}l"
OUTSIDER_MARK = f"{MARK}o"
DEMOTED_MARK = f"{MARK}d"
STRANGER_MARK = f"{MARK}x"
TEACHER = f"user_{TEACHER_MARK}"  # the teacher the exercises' vault files name
LEARNER = f"user_{LEARNER_MARK}"  # no tie to TEACHER
OUTSIDER = f"user_{OUTSIDER_MARK}"  # a teacher with the learner in two classes of their own
DEMOTED = f"user_{DEMOTED_MARK}"  # named by an exercise, no longer a teacher
STRANGER = f"user_{STRANGER_MARK}"  # a teacher with no tie to the learner at all
ROLES = {
    TEACHER: "teacher",
    LEARNER: "member",
    OUTSIDER: "teacher",
    DEMOTED: "member",
    STRANGER: "teacher",
}
PS_PUBLISHED = f"ps.{TEACHER_MARK}.published"
CURRICULUM_EX = f"ex.{OUTSIDER_MARK}.curriculum"
DEFAULT_GROUP = default_group_uid(OUTSIDER)
MISSING_ENTRY = f"ue_{MARK}_missing"
MISSING_STUDENT = f"user_{MARK}missing"
MISSING_REPORT = f"er_{MARK}_missing"
NO_TEACHER = "reached no teacher"


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


async def _seed_curriculum_route(driver: AsyncDriver) -> None:
    """A vault-authored CURRICULUM exercise on the published step, naming STRANGER its
    teacher as the vault door writes it (``REVIEWED_BY``), and the learner's default
    group — which a request on the exercise does not reach."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (ex:Entity:Exercise {uid: $ex})
            SET ex.title = $ex, ex.entity_type = 'exercise', ex.scope = 'curriculum',
                ex.instructions = $ex + ' instructions', ex.status = 'active'
            WITH ex
            MATCH (s:Entity:PathStep {uid: $ps})
            MERGE (s)-[:HAS_EXERCISE]->(ex)
            WITH ex
            MATCH (named:User {uid: $named})
            MERGE (ex)-[:REVIEWED_BY]->(named)
            WITH ex
            MATCH (owner:User {uid: $owner}), (learner:User {uid: $learner})
            MERGE (g:Group {uid: $group})
            SET g.name = $group, g.is_active = true, g.is_default = true, g.owner_uid = $owner
            MERGE (owner)-[:OWNS]->(g)
            MERGE (learner)-[:MEMBER_OF]->(g)
            """,
            ex=CURRICULUM_EX,
            ps=PS_PUBLISHED,
            named=STRANGER,
            owner=OUTSIDER,
            learner=LEARNER,
            group=DEFAULT_GROUP,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Groups and entries carry no mark in their generated uids — remove them by owner;
    the vault's step, exercises and tracker rows carry the mark."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )
        await session.run(
            "MATCH (n) WHERE n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark DETACH DELETE n",
            mark=MARK,
        )


def _uidless(body: str, *uids: str) -> str:
    for uid in uids:
        body = body.replace(uid, "<uid>")
    body = re.sub(r'"timestamp":"[^"]*"', '"timestamp":"<t>"', body)
    return re.sub(r"-[0-9a-f]{8}\b", "-<id>", body)


async def _turn_in(
    client: httpx.AsyncClient, exercise_uid: str, title: str, **data: str
) -> httpx.Response:
    return await client.post(
        "/api/user-entries/upload",
        files={"file": (f"{title}.md", f"{MARK} {title}".encode(), "text/markdown")},
        data={"pipeline": "teacher_review", "fulfills_exercise_uid": exercise_uid, **data},
    )


async def _feedback_edges(driver: AsyncDriver, entry_uid: str) -> set[tuple[str, str]]:
    """Every feedback request the entry carries, as ``(edge type, far uid)``."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Entity {uid: $entry})-[r:SUBMITTED_TO_TEACHER|SUBMITTED_TO_GROUP]->(x)
            RETURN type(r) AS type, x.uid AS far
            """,
            entry=entry_uid,
        )
        return {(record["type"], record["far"]) async for record in result}


async def _entries_for(driver: AsyncDriver, owner: str, exercise_uid: str) -> int:
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (:User {uid: $owner})-[:OWNS]->(e:Entity:UserEntry)
                WHERE e.turn_in_exercise_uid = $ex
                RETURN count(e) AS n
                """,
                owner=owner,
                ex=exercise_uid,
            )
        ).single()
    assert record is not None
    return int(record["n"])


async def _report_on(driver: AsyncDriver, entry_uid: str) -> str:
    """The uid of the teacher's uploaded-feedback report on the entry."""
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (r:Entity:EntryReport)-[:REPORT_FOR]->(:Entity {uid: $entry})
                WHERE r.report_file_path IS NOT NULL
                RETURN r.uid AS uid
                """,
                entry=entry_uid,
            )
        ).single()
    assert record is not None, entry_uid
    return str(record["uid"])


async def _upload_feedback(client: httpx.AsyncClient, entry_uid: str) -> None:
    response = await client.post(
        f"/api/teaching/review/{entry_uid}/report",
        files={"feedback_file": ("feedback.md", f"{MARK} feedback".encode(), "text/markdown")},
    )
    assert "Feedback submitted successfully." in response.text, response.text


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        clients: dict[str, httpx.AsyncClient],
        exercises: dict[str, str],
        group: str,
        entries: dict[str, str],
        reports: dict[str, str],
    ) -> None:
        self.driver = driver
        self.clients = clients
        self.exercises = exercises
        self.group = group  # OUTSIDER's class with the learner in it
        self.entries = entries  # the learner's turn-ins, by exercise key
        self.entry = entries["named"]  # the turn-in the review doors act on
        self.reports = reports  # uploaded-feedback reports, by exercise key

    async def exchange(self, caller: str, exercise: str, student: str) -> httpx.Response:
        return await self.clients[caller].get(
            "/exchange", params={"exercise": exercise, "student": student}
        )

    async def queue(self, caller: str) -> list[str]:
        response = await self.clients[caller].get("/api/teaching/review-queue")
        assert response.status_code == 200, response.text
        return [str(item["submission_uid"]) for item in response.json()]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    reports_dir: Path = tmp_path_factory.mktemp("reports")
    async with (
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OUTSIDER, OUTSIDER_MARK) as outsider,
        signed_in_client(skuel_app, DEMOTED, DEMOTED_MARK) as demoted,
        signed_in_client(skuel_app, STRANGER, STRANGER_MARK) as stranger,
    ):
        for uid in (TEACHER, OUTSIDER, DEMOTED, STRANGER):
            await _set_role(driver, uid, "teacher")
        await _set_role(driver, LEARNER, "member")
        patch = pytest.MonkeyPatch()
        # The report door writes the feedback file to disk before it files the report.
        patch.setattr(teaching_api, "_REPORTS_DIR", reports_dir)
        try:
            exercises = {
                # A uid segment joins words with hyphens (the uid grammar).
                key: f"ex.{MARK}.{key.replace('_', '-')}"
                for key in ("named", "reported", "demoted", "classroom", "classroom_reported")
            }
            await sync_vault_exercises(
                driver,
                tmp_path_factory.mktemp("content_vault"),
                step_uid=PS_PUBLISHED,
                exercises={uid: f"{MARK} {key}" for key, uid in exercises.items()},
                teacher_uid=TEACHER,
                teacher_of={
                    exercises["demoted"]: DEMOTED,
                    exercises["classroom"]: OUTSIDER,
                    exercises["classroom_reported"]: OUTSIDER,
                },
            )
            await _set_role(driver, DEMOTED, ROLES[DEMOTED])

            group = await create(outsider, "groups", f"{MARK}-class", name=f"{MARK}-class")
            added = await outsider.post(
                f"/api/groups/{group}/members/add", json={"user_uid": LEARNER}
            )
            assert added.status_code == 200, added.text
            await _seed_curriculum_route(driver)

            for client in (learner, teacher):
                started = await client.post(
                    f"/explore/ps/{PS_PUBLISHED}/progress",
                    data={"state": "learning", "review": "true"},
                )
                assert started.status_code == 200, started.text

            entries: dict[str, str] = {}
            for key in ("named", "reported"):
                turned_in = await _turn_in(learner, exercises[key], key)
                assert turned_in.status_code == 201, turned_in.text
                entries[key] = str(turned_in.json()["user_entry"]["uid"])
            for key in ("classroom", "classroom_reported"):
                turned_in = await _turn_in(
                    learner, exercises[key], key, audience=f"teacher:{group}"
                )
                assert turned_in.status_code == 201, turned_in.text
                entries[key] = str(turned_in.json()["user_entry"]["uid"])

            # Each reviewer uploads feedback on one entry asked of them.
            await _upload_feedback(teacher, entries["reported"])
            await _upload_feedback(outsider, entries["classroom_reported"])
            reports = {
                "reported": await _report_on(driver, entries["reported"]),
                "classroom_reported": await _report_on(driver, entries["classroom_reported"]),
            }

            yield World(
                driver,
                {
                    TEACHER: teacher,
                    LEARNER: learner,
                    OUTSIDER: outsider,
                    DEMOTED: demoted,
                    STRANGER: stranger,
                },
                exercises,
                group,
                entries,
                reports,
            )
        finally:
            patch.undo()
            await _delete_owned(driver, list(ROLES))


@pytest.fixture
def reviewer(
    skuel_app: Any,  # boundary: fasthtml-app
    monkeypatch: pytest.MonkeyPatch,
) -> list[AdmittedReport]:
    """Force the tier gate open and record every admission that reaches the AI reviewer."""
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


# =============================================================================
# The request reaches the exercise's named teacher — and no one else
# =============================================================================


async def test_the_request_is_filed_to_the_exercises_named_teacher(world: World) -> None:
    assert await _feedback_edges(world.driver, world.entry) == {("SUBMITTED_TO_TEACHER", TEACHER)}
    edges = [e for e in await edges_between(world.driver, world.entry, TEACHER) if e.type != "OWNS"]
    assert len(edges) == 1 and edges[0].properties.get("submitted_at") is not None, edges


async def test_the_named_teacher_reads_it_in_the_review_queue_and_no_other_teacher_does(
    world: World,
) -> None:
    assert world.entry in await world.queue(TEACHER)
    assert world.entry not in await world.queue(OUTSIDER)


async def test_the_named_teacher_opens_the_review_detail_and_another_teacher_gets_not_found(
    world: World,
) -> None:
    opened = await world.clients[TEACHER].get(f"/api/teaching/review/{world.entry}")
    refused = await world.clients[OUTSIDER].get(f"/api/teaching/review/{world.entry}")
    missing = await world.clients[OUTSIDER].get(f"/api/teaching/review/{MISSING_ENTRY}")

    assert opened.status_code == 200, opened.text
    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)


async def test_the_named_teacher_lists_it_under_the_exercise(world: World) -> None:
    listed = await world.clients[TEACHER].get(
        f"/api/teaching/exercises/{world.exercises['named']}/submissions"
    )
    assert listed.status_code == 200, listed.text
    assert world.entry in listed.text


async def test_the_named_teacher_reaches_the_ai_reviewer_and_another_teacher_is_refused(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    exercise = world.exercises["named"]
    admitted = await world.clients[TEACHER].post(
        "/api/exercises/report", json={"submission_uid": world.entry, "exercise_uid": exercise}
    )
    assert admitted.status_code == 200, admitted.text
    assert [(c.entry.uid, c.exercise.uid, c.caller_uid) for c in reviewer] == [
        (world.entry, exercise, TEACHER)
    ]

    reviewer.clear()
    refused = await world.clients[OUTSIDER].post(
        "/api/exercises/report", json={"submission_uid": world.entry, "exercise_uid": exercise}
    )
    missing = await world.clients[OUTSIDER].post(
        "/api/exercises/report", json={"submission_uid": MISSING_ENTRY, "exercise_uid": exercise}
    )
    assert refused.status_code == 404, refused.text
    assert reviewer == []
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)


# =============================================================================
# Controls — every other route is unchanged
# =============================================================================


async def test_a_named_teacher_without_the_teacher_role_is_nobodys_reviewer(world: World) -> None:
    refused = await _turn_in(world.clients[LEARNER], world.exercises["demoted"], "demoted")
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries_for(world.driver, LEARNER, world.exercises["demoted"]) == 0


async def test_the_named_teacher_turning_in_on_their_own_exercise_has_nobody_to_ask(
    world: World,
) -> None:
    refused = await _turn_in(world.clients[TEACHER], world.exercises["named"], "own")
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries_for(world.driver, TEACHER, world.exercises["named"]) == 0


async def test_a_request_sent_to_a_class_still_reaches_its_group(world: World) -> None:
    entry = world.entries["classroom"]
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_GROUP", world.group)}
    assert entry in await world.queue(OUTSIDER)
    assert entry not in await world.queue(TEACHER)


async def test_a_curriculum_exercise_reaches_its_named_teacher_not_the_default_group(
    world: World,
) -> None:
    turned_in = await _turn_in(world.clients[LEARNER], CURRICULUM_EX, "curriculum")
    assert turned_in.status_code == 201, turned_in.text
    entry = str(turned_in.json()["user_entry"]["uid"])
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_TEACHER", STRANGER)}
    assert entry in await world.queue(STRANGER)
    assert entry not in await world.queue(OUTSIDER)


# =============================================================================
# The exchange thread — the requests sent to the viewer, nothing else
# =============================================================================


async def test_the_named_teacher_opens_the_exchange_on_the_requests_sent_to_them(
    world: World,
) -> None:
    opened = await world.exchange(TEACHER, world.exercises["named"], LEARNER)
    assert opened.status_code == 200, opened.text
    assert "Exchange not found" not in opened.text


async def test_the_named_teacher_never_opens_the_learners_other_exchanges(world: World) -> None:
    """The learner's work for another teacher's exercise asked this teacher nothing."""
    refused = await world.exchange(TEACHER, world.exercises["classroom"], LEARNER)
    missing = await world.exchange(TEACHER, world.exercises["classroom"], MISSING_STUDENT)
    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, LEARNER) == _uidless(missing.text, MISSING_STUDENT)


async def test_the_classroom_teacher_opens_their_own_requests_only(world: World) -> None:
    opened = await world.exchange(OUTSIDER, world.exercises["classroom"], LEARNER)
    refused = await world.exchange(OUTSIDER, world.exercises["named"], LEARNER)
    assert opened.status_code == 200, opened.text
    assert refused.status_code == 404, refused.text


async def test_an_unrelated_teacher_gets_the_exchange_not_found(world: World) -> None:
    refused = await world.exchange(STRANGER, world.exercises["named"], LEARNER)
    missing = await world.exchange(STRANGER, world.exercises["named"], MISSING_STUDENT)
    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, LEARNER) == _uidless(missing.text, MISSING_STUDENT)


# =============================================================================
# The report download — the reports on the entries asked of the teacher
# =============================================================================


async def _download(world: World, caller: str, report_uid: str) -> httpx.Response:
    return await world.clients[caller].get(f"/api/reports/{report_uid}/download")


async def test_the_named_teacher_downloads_the_report_on_a_request_sent_to_them(
    world: World,
) -> None:
    downloaded = await _download(world, TEACHER, world.reports["reported"])
    assert downloaded.status_code == 200, downloaded.text
    assert f"{MARK} feedback" in downloaded.text


async def test_the_named_teacher_never_downloads_a_report_on_another_teachers_request(
    world: World,
) -> None:
    refused = await _download(world, TEACHER, world.reports["classroom_reported"])
    missing = await _download(world, TEACHER, MISSING_REPORT)
    assert refused.status_code == 404, refused.text
    assert refused.text == missing.text


async def test_the_classroom_teacher_downloads_their_students_reports(world: World) -> None:
    for report in world.reports.values():
        downloaded = await _download(world, OUTSIDER, report)
        assert downloaded.status_code == 200, (report, downloaded.text)


async def test_an_unrelated_teacher_gets_the_download_not_found(world: World) -> None:
    refused = await _download(world, STRANGER, world.reports["reported"])
    missing = await _download(world, STRANGER, MISSING_REPORT)
    assert refused.status_code == 404, refused.text
    assert refused.text == missing.text


# =============================================================================
# The student-level surfaces stay with the classroom
# =============================================================================


async def _students(world: World, caller: str) -> list[str]:
    response = await world.clients[caller].get("/api/teaching/students")
    assert response.status_code == 200, response.text
    return [str(row["student_uid"]) for row in response.json()]


async def test_a_direct_request_alone_does_not_list_the_learner_as_a_student(
    world: World,
) -> None:
    assert LEARNER not in await _students(world, TEACHER)
    assert LEARNER not in await _students(world, STRANGER)
    assert LEARNER in await _students(world, OUTSIDER)


async def test_the_student_page_opens_for_the_classroom_teacher_only(world: World) -> None:
    async def page(caller: str, student: str) -> httpx.Response:
        return await world.clients[caller].get(f"/api/teaching/students/{student}/submissions")

    opened = await page(OUTSIDER, LEARNER)
    assert opened.status_code == 200, opened.text
    assert world.entries["classroom"] in opened.text
    for caller in (TEACHER, STRANGER):
        refused = await page(caller, LEARNER)
        missing = await page(caller, MISSING_STUDENT)
        assert refused.status_code == missing.status_code != 200, refused.text
        assert _uidless(refused.text, LEARNER) == _uidless(missing.text, MISSING_STUDENT)


async def test_the_knowledge_tab_gate_is_the_classroom(
    skuel_app: Any,  # boundary: fasthtml-app
    world: World,
) -> None:
    """The KU tab opens on ``verify_teacher_authority`` — the classroom gate, which a
    direct request does not satisfy; its fragment then reads as a missing student."""
    review = skuel_app.state.services.teacher_review
    assert (await review.verify_teacher_authority(OUTSIDER, LEARNER)).is_ok
    for caller in (TEACHER, STRANGER):
        assert (await review.verify_teacher_authority(caller, LEARNER)).is_error
        refused = await world.clients[caller].get(f"/api/teaching/students/{LEARNER}/ku/preview")
        missing = await world.clients[caller].get(
            f"/api/teaching/students/{MISSING_STUDENT}/ku/preview"
        )
        assert _uidless(refused.text, LEARNER) == _uidless(missing.text, MISSING_STUDENT)


async def test_the_dashboard_counts_the_request_but_not_a_student(
    skuel_app: Any,  # boundary: fasthtml-app
    world: World,
) -> None:
    stats = await skuel_app.state.services.teacher_review.get_dashboard_stats(TEACHER)
    assert stats.is_ok, stats
    assert stats.value["pending_count"] >= 1
    assert stats.value["total_students"] == 0


# =============================================================================
# The revision door — last: it moves the entry out of the pending queue
# =============================================================================


async def test_the_named_teacher_requests_a_revision_and_another_teacher_gets_not_found(
    world: World,
) -> None:
    form = {"instructions": f"{MARK} revise this", "fp_count": "0"}
    refused = await world.clients[OUTSIDER].post(
        f"/api/teaching/review/{world.entry}/revision", data=form
    )
    missing = await world.clients[OUTSIDER].post(
        f"/api/teaching/review/{MISSING_ENTRY}/revision", data=form
    )
    assert "Submission not found." in refused.text, refused.text
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)

    requested = await world.clients[TEACHER].post(
        f"/api/teaching/review/{world.entry}/revision", data=form
    )
    assert "Revision requested." in requested.text, requested.text
    async with world.driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (e:Entity {uid: $entry})<-[:REPORT_FOR]-(:EntryReport)
                      <-[:RESPONDS_TO_REPORT]-(rex:RevisedExercise)
                RETURN rex.student_uid AS student, e.status AS status
                """,
                entry=world.entry,
            )
        ).single()
    assert record is not None
    assert record["student"] == LEARNER
    assert record["status"] == "revision_requested"
