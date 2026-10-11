"""A feedback request on an anchored PERSONAL exercise reaches the teacher who owns it.

A teacher who anchors a PERSONAL exercise to a published PathStep contributes it to the
step: every learner on the step may turn in against it. A ``teacher_review`` turn-in is
a feedback request, and the exercise belongs to no group — so it is filed to the
exercise's owner directly, ``(entry)-[:SUBMITTED_TO_TEACHER {submitted_at}]->(teacher)``
(ADR-088 §9). That teacher reads it everywhere a group's teacher reads a request sent to
their group: the review queue, the review detail, the exercise's submission list, the
AI-report door and the revision door. Any other teacher — here one who has the learner
in two classes of their own — is refused exactly as for an entry that does not exist.

The direct target is the anchored-PERSONAL route only. An unanchored PERSONAL exercise
is its owner's alone; one anchored to a draft step has no audience; an ASSIGNED exercise
reaches its group's teacher and a CURRICULUM one the learner's default group, as before;
an owner turning in against their own exercise has nobody to ask, and an owner without
the teacher role is nobody's reviewer.

Every exercise and the group are made at the real create doors; the learner starts the
step at the real progress door and turns in at the real upload door.
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
from core.models.group.group import DEFAULT_GROUP_UID_PREFIX
from core.services.report.entry_report_service import AdmittedReport
from core.utils.result_simplified import Result
from tests.integration._activity_link_rig import (
    create,
    edges_between,
    seed_published_path_step,
    signed_in_client,
    write_edge,
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
TEACHER = f"user_{TEACHER_MARK}"  # owns the anchored PERSONAL exercises
LEARNER = f"user_{LEARNER_MARK}"  # no tie to TEACHER
OUTSIDER = f"user_{OUTSIDER_MARK}"  # a teacher with the learner in two classes of their own
DEMOTED = f"user_{DEMOTED_MARK}"  # authored an anchored exercise, no longer a teacher
ROLES = {TEACHER: "teacher", LEARNER: "member", OUTSIDER: "teacher", DEMOTED: "member"}
PS_PUBLISHED = f"ps.{TEACHER_MARK}.published"
PS_DRAFT = f"ps.{TEACHER_MARK}.draft"
CURRICULUM_EX = f"ex.{OUTSIDER_MARK}.curriculum"
DEFAULT_GROUP = f"{DEFAULT_GROUP_UID_PREFIX}{OUTSIDER_MARK}"
MISSING_ENTRY = f"ue_{MARK}_missing"
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


async def _seed_draft_path_step(driver: AsyncDriver, uid: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (s:Entity:PathStep {uid: $uid})
            SET s.title = $uid, s.entity_type = 'path_step', s.status = 'active',
                s.publication_state = 'draft'
            """,
            uid=uid,
        )


async def _seed_curriculum_route(driver: AsyncDriver) -> None:
    """A vault-authored CURRICULUM exercise on the published step (no door creates one),
    and the learner's default group — the curriculum fallback's target."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (ex:Entity:Exercise {uid: $ex})
            SET ex.title = $ex, ex.entity_type = 'exercise', ex.scope = 'curriculum',
                ex.instructions = $ex + ' instructions', ex.status = 'active'
            WITH ex
            MATCH (s:Entity:PathStep {uid: $ps})
            MERGE (s)-[:HAS_EXERCISE]->(ex)
            WITH s
            MATCH (owner:User {uid: $owner}), (learner:User {uid: $learner})
            MERGE (g:Group {uid: $group})
            SET g.name = $group, g.is_active = true, g.owner_uid = $owner
            MERGE (owner)-[:OWNS]->(g)
            MERGE (learner)-[:MEMBER_OF]->(g)
            """,
            ex=CURRICULUM_EX,
            ps=PS_PUBLISHED,
            owner=OUTSIDER,
            learner=LEARNER,
            group=DEFAULT_GROUP,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Groups, exercises and entries carry no mark in their generated uids — remove them by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
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


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        clients: dict[str, httpx.AsyncClient],
        exercises: dict[str, str],
        group: str,
        entry: str,
    ) -> None:
        self.driver = driver
        self.clients = clients
        self.exercises = exercises
        self.group = group  # OUTSIDER's class with the learner in it
        self.entry = entry  # the learner's turn-in on the anchored exercise

    async def queue(self, caller: str) -> list[str]:
        response = await self.clients[caller].get("/api/teaching/review-queue")
        assert response.status_code == 200, response.text
        return [str(item["submission_uid"]) for item in response.json()]


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, TEACHER, TEACHER_MARK) as teacher,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OUTSIDER, OUTSIDER_MARK) as outsider,
        signed_in_client(skuel_app, DEMOTED, DEMOTED_MARK) as demoted,
    ):
        for uid in (TEACHER, OUTSIDER, DEMOTED):
            await _set_role(driver, uid, "teacher")
        await _set_role(driver, LEARNER, "member")
        await seed_published_path_step(driver, PS_PUBLISHED, f"{MARK} published step")
        await _seed_draft_path_step(driver, PS_DRAFT)
        try:

            async def personal(client: httpx.AsyncClient, name: str, **anchor: str) -> str:
                return await create(
                    client,
                    "exercises",
                    f"{MARK}-{name}",
                    name=f"{MARK}-{name}",
                    instructions=f"{MARK} {name} instructions",
                    **anchor,
                )

            exercises = {
                "anchored": await personal(teacher, "anchored", path_step_uid=PS_PUBLISHED),
                "unanchored": await personal(teacher, "unanchored"),
                "draft": await personal(teacher, "draft", path_step_uid=PS_DRAFT),
                "demoted": await personal(demoted, "demoted", path_step_uid=PS_PUBLISHED),
            }
            await _set_role(driver, DEMOTED, ROLES[DEMOTED])

            group = await create(outsider, "groups", f"{MARK}-class", name=f"{MARK}-class")
            added = await outsider.post(
                f"/api/groups/{group}/members/add", json={"user_uid": LEARNER}
            )
            assert added.status_code == 200, added.text
            exercises["assigned"] = await create(
                outsider,
                "exercises",
                f"{MARK}-assigned",
                name=f"{MARK}-assigned",
                instructions=f"{MARK} assigned instructions",
                scope="assigned",
                group_uid=group,
            )
            await _seed_curriculum_route(driver)

            started = await learner.post(
                f"/explore/ps/{PS_PUBLISHED}/progress",
                data={"state": "learning", "review": "true"},
            )
            assert started.status_code == 200, started.text
            # The draft step's control isolates the audience rule: the learner is in
            # progress on it, so only the step's publication can refuse the request.
            await write_edge(driver, LEARNER, "IN_PROGRESS", PS_DRAFT)

            turned_in = await _turn_in(learner, exercises["anchored"], "anchored")
            assert turned_in.status_code == 201, turned_in.text
            entry = str(turned_in.json()["user_entry"]["uid"])

            yield World(
                driver,
                {TEACHER: teacher, LEARNER: learner, OUTSIDER: outsider, DEMOTED: demoted},
                exercises,
                group,
                entry,
            )
        finally:
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
# The request reaches the exercise's owner — and no one else
# =============================================================================


async def test_the_request_is_filed_to_the_exercises_owner(world: World) -> None:
    assert await _feedback_edges(world.driver, world.entry) == {("SUBMITTED_TO_TEACHER", TEACHER)}
    edges = [e for e in await edges_between(world.driver, world.entry, TEACHER) if e.type != "OWNS"]
    assert len(edges) == 1 and edges[0].properties.get("submitted_at") is not None, edges


async def test_the_owner_reads_it_in_the_review_queue_and_no_other_teacher_does(
    world: World,
) -> None:
    assert world.entry in await world.queue(TEACHER)
    assert world.entry not in await world.queue(OUTSIDER)


async def test_the_owner_opens_the_review_detail_and_another_teacher_gets_not_found(
    world: World,
) -> None:
    opened = await world.clients[TEACHER].get(f"/api/teaching/review/{world.entry}")
    refused = await world.clients[OUTSIDER].get(f"/api/teaching/review/{world.entry}")
    missing = await world.clients[OUTSIDER].get(f"/api/teaching/review/{MISSING_ENTRY}")

    assert opened.status_code == 200, opened.text
    assert refused.status_code == 404, refused.text
    assert _uidless(refused.text, world.entry) == _uidless(missing.text, MISSING_ENTRY)


async def test_the_owner_lists_it_under_the_exercise(world: World) -> None:
    listed = await world.clients[TEACHER].get(
        f"/api/teaching/exercises/{world.exercises['anchored']}/submissions"
    )
    assert listed.status_code == 200, listed.text
    assert world.entry in listed.text


async def test_the_owner_reaches_the_ai_reviewer_and_another_teacher_is_refused(
    world: World, reviewer: list[AdmittedReport]
) -> None:
    exercise = world.exercises["anchored"]
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


async def test_an_unanchored_personal_exercise_takes_no_turn_in(world: World) -> None:
    refused = await _turn_in(world.clients[LEARNER], world.exercises["unanchored"], "unanchored")
    assert refused.status_code == 403, refused.text
    assert await _entries_for(world.driver, LEARNER, world.exercises["unanchored"]) == 0


async def test_an_exercise_anchored_to_a_draft_step_reaches_no_teacher(world: World) -> None:
    refused = await _turn_in(world.clients[LEARNER], world.exercises["draft"], "draft")
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries_for(world.driver, LEARNER, world.exercises["draft"]) == 0


async def test_an_owner_without_the_teacher_role_is_nobodys_reviewer(world: World) -> None:
    refused = await _turn_in(world.clients[LEARNER], world.exercises["demoted"], "demoted")
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries_for(world.driver, LEARNER, world.exercises["demoted"]) == 0


async def test_an_owner_turning_in_on_their_own_exercise_has_nobody_to_ask(world: World) -> None:
    refused = await _turn_in(world.clients[TEACHER], world.exercises["anchored"], "own")
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries_for(world.driver, TEACHER, world.exercises["anchored"]) == 0


async def test_an_assigned_exercise_still_reaches_its_group(world: World) -> None:
    turned_in = await _turn_in(world.clients[LEARNER], world.exercises["assigned"], "assigned")
    assert turned_in.status_code == 201, turned_in.text
    entry = str(turned_in.json()["user_entry"]["uid"])
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_GROUP", world.group)}
    assert entry in await world.queue(OUTSIDER)
    assert entry not in await world.queue(TEACHER)


async def test_a_curriculum_exercise_still_reaches_the_default_group(world: World) -> None:
    turned_in = await _turn_in(world.clients[LEARNER], CURRICULUM_EX, "curriculum")
    assert turned_in.status_code == 201, turned_in.text
    entry = str(turned_in.json()["user_entry"]["uid"])
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_GROUP", DEFAULT_GROUP)}


# =============================================================================
# The revision door — last: it moves the entry out of the pending queue
# =============================================================================


async def test_the_owner_requests_a_revision_and_another_teacher_gets_not_found(
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
