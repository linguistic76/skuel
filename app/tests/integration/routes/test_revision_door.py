"""The revision door is the review page, for the exercise's named teacher only.

ADR-091 N7, N8, N2: a revision request names an exercise, so work with no exercise
gets a report and no revision; only the teacher the exercise's vault file names
(``REVIEWED_BY``) may send one, even when another teacher holds the same work
through their group; and nothing edits, deletes or files a revision outside the
review page — the ``/api/revised-exercises`` CRUD doors are gone.

Each refusal writes nothing, and the review panel shows the same sentence in place
of the form. Controls: a report on the same no-exercise work lands, the named
teacher's revision lands, and the learner still reads it.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.inbound import teaching_api
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.services.report.teacher_review_service import (
    REVISION_NAMED_TEACHER_ONLY,
    REVISION_NEEDS_EXERCISE,
)
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client, sync_vault_exercises

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

MARK = "zzzrevisiondoor"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
NAMED_MARK = f"{MARK}n"
CLASS_MARK = f"{MARK}c"
LEARNER_MARK = f"{MARK}l"
NAMED = seed_user_uid(f"{NAMED_MARK}")  # the teacher the exercise's vault file names
CLASS_TEACHER = seed_user_uid(f"{CLASS_MARK}")  # owns a class the learner is in; not named
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
STEP = f"ps.{MARK}.step"
PRACTICE = f"ex.{MARK}.practice"
USERS = [NAMED, CLASS_TEACHER, LEARNER]


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


async def _upload(client: httpx.AsyncClient, title: str, **data: Any) -> str:  # boundary: form
    response = await client.post(
        "/api/user-entries/upload",
        files={"file": (f"{title}.md", f"{MARK} {title}".encode(), "text/markdown")},
        data={"pipeline": "teacher_review", **data},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user_entry"]["uid"])


async def _replies(driver: AsyncDriver, entry_uid: str) -> dict[str, Any]:  # boundary: graph row
    """What a review write changes on the entry: its status, reports and revisions."""
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (e:Entity {uid: $entry})
                RETURN e.status AS status,
                       COUNT { (:EntryReport)-[:REPORT_FOR]->(e) } AS reports,
                       COUNT {
                           (:RevisedExercise)-[:RESPONDS_TO_REPORT]->(:EntryReport)
                           -[:REPORT_FOR]->(e)
                       } AS revisions
                """,
                entry=entry_uid,
            )
        ).single()
    assert record is not None
    return dict(record)


async def _revisions(driver: AsyncDriver) -> list[list[Any]]:  # boundary: graph rows
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (rex:Entity:RevisedExercise)-[:REVISES_EXERCISE]->(:Entity {uid: $ex})
                OPTIONAL MATCH (owner:User)-[:OWNS]->(rex)
                WITH rex, owner ORDER BY rex.uid
                RETURN collect([rex.uid, rex.instructions, rex.student_uid, owner.uid]) AS rows
                """,
                ex=PRACTICE,
            )
        ).single()
    assert record is not None
    return list(record["rows"])


async def _request_revision(client: httpx.AsyncClient, entry_uid: str) -> str:
    response = await client.post(
        f"/api/teaching/review/{entry_uid}/revision",
        data={"instructions": f"{MARK} revise this", "fp_count": "0"},
    )
    assert response.status_code == 200, response.text
    return html.unescape(response.text)


async def _panel(client: httpx.AsyncClient, entry_uid: str) -> str:
    response = await client.get(f"/api/teaching/review/{entry_uid}/panel")
    assert response.status_code == 200, response.text
    return html.unescape(response.text)


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        clients: dict[str, httpx.AsyncClient],
        on_exercise: str,
        loose: str,
    ) -> None:
        self.driver = driver
        self.clients = clients
        self.on_exercise = on_exercise  # asks NAMED directly and CLASS_TEACHER's class
        self.loose = loose  # no exercise; asks CLASS_TEACHER's class


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    reports_dir: Path = tmp_path_factory.mktemp("reports")
    async with (
        signed_in_client(skuel_app, NAMED, NAMED_MARK) as named,
        signed_in_client(skuel_app, CLASS_TEACHER, CLASS_MARK) as class_teacher,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
    ):
        for uid in (NAMED, CLASS_TEACHER):
            await _set_role(driver, uid, "teacher")
        await _set_role(driver, LEARNER, "member")
        patch = pytest.MonkeyPatch()
        # The report door writes the feedback file to disk before it files the report.
        patch.setattr(teaching_api, "_REPORTS_DIR", reports_dir)
        try:
            await sync_vault_exercises(
                driver,
                tmp_path_factory.mktemp("content_vault"),
                step_uid=STEP,
                exercises={PRACTICE: f"{MARK} practice"},
                teacher_uid=NAMED,
            )
            group = await create(class_teacher, "groups", f"{MARK}-class", name=f"{MARK}-class")
            added = await class_teacher.post(
                f"/api/groups/{group}/members/add", json={"user_uid": LEARNER}
            )
            assert added.status_code == 200, added.text
            started = await learner.post(
                f"/explore/ps/{STEP}/progress", data={"state": "learning", "review": "true"}
            )
            assert started.status_code == 200, started.text

            on_exercise = await _upload(
                learner,
                "on-exercise",
                fulfills_exercise_uid=PRACTICE,
                audience=["teachers", f"teacher:{group}"],
            )
            loose = await _upload(learner, "loose", audience=f"teacher:{group}")
            yield World(
                driver,
                {NAMED: named, CLASS_TEACHER: class_teacher, LEARNER: learner},
                on_exercise,
                loose,
            )
        finally:
            patch.undo()
            async with driver.session() as session:
                await session.run(
                    "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n",
                    users=USERS,
                )
                await session.run(
                    "MATCH (n) WHERE n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark "
                    "DETACH DELETE n",
                    mark=MARK,
                )


# =============================================================================
# N7 — work with no exercise gets a report, never a revision
# =============================================================================


async def test_a_revision_on_work_with_no_exercise_is_refused_and_writes_nothing(
    world: World,
) -> None:
    before = await _replies(world.driver, world.loose)
    answered = await _request_revision(world.clients[CLASS_TEACHER], world.loose)
    assert REVISION_NEEDS_EXERCISE in answered, answered
    assert "Revision requested" not in answered
    assert await _replies(world.driver, world.loose) == before


async def test_the_panel_offers_a_report_and_says_why_there_is_no_revision(
    world: World,
) -> None:
    panel = await _panel(world.clients[CLASS_TEACHER], world.loose)
    assert REVISION_NEEDS_EXERCISE in panel
    assert 'name="instructions"' not in panel
    assert 'name="feedback_file"' in panel


async def test_a_report_on_the_same_work_lands(world: World) -> None:
    response = await world.clients[CLASS_TEACHER].post(
        f"/api/teaching/review/{world.loose}/report",
        files={"feedback_file": ("feedback.md", f"{MARK} feedback".encode(), "text/markdown")},
    )
    assert "Feedback submitted successfully." in response.text, response.text
    replies = await _replies(world.driver, world.loose)
    assert replies == {"status": "completed", "reports": 1, "revisions": 0}


# =============================================================================
# N8 — only the exercise's named teacher sends a revision
# =============================================================================


async def test_a_class_teacher_the_exercise_does_not_name_is_refused(world: World) -> None:
    before = await _replies(world.driver, world.on_exercise)
    answered = await _request_revision(world.clients[CLASS_TEACHER], world.on_exercise)
    assert REVISION_NAMED_TEACHER_ONLY in answered, answered
    assert "Revision requested" not in answered
    assert await _replies(world.driver, world.on_exercise) == before
    assert await _revisions(world.driver) == []


async def test_the_class_teachers_panel_says_why_and_the_named_teachers_offers_the_form(
    world: World,
) -> None:
    refused = await _panel(world.clients[CLASS_TEACHER], world.on_exercise)
    offered = await _panel(world.clients[NAMED], world.on_exercise)
    assert REVISION_NAMED_TEACHER_ONLY in refused
    assert 'name="instructions"' not in refused
    assert 'name="feedback_file"' in refused
    assert 'name="instructions"' in offered
    assert REVISION_NAMED_TEACHER_ONLY not in offered


async def test_the_named_teacher_sends_the_revision(world: World) -> None:
    answered = await _request_revision(world.clients[NAMED], world.on_exercise)
    assert "Revision requested." in answered, answered
    replies = await _replies(world.driver, world.on_exercise)
    assert replies == {"status": "revision_requested", "reports": 1, "revisions": 1}
    [[_uid, instructions, student, owner]] = await _revisions(world.driver)
    assert (instructions, student, owner) == (f"{MARK} revise this", LEARNER, NAMED)


# =============================================================================
# N2 — no door files, edits or deletes a revision outside the review page
# =============================================================================


async def _report_on(driver: AsyncDriver, entry_uid: str) -> str:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (r:EntryReport)-[:REPORT_FOR]->(:Entity {uid: $entry}) RETURN r.uid AS uid",
                entry=entry_uid,
            )
        ).single()
    assert record is not None
    return str(record["uid"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/revised-exercises/create"),
        ("POST", "/api/revised-exercises/update?uid={uid}"),
        ("POST", "/api/revised-exercises/delete?uid={uid}"),
        ("GET", "/api/revised-exercises/get?uid={uid}"),
        ("GET", "/api/revised-exercises/list"),
    ],
)
async def test_the_retired_revision_door_answers_nothing_and_writes_nothing(
    world: World, method: str, path: str
) -> None:
    """Asked by the revision's owner, with the body the retired doors accepted."""
    before = await _revisions(world.driver)
    [[uid, _instructions, _student, owner]] = before
    body = {
        "instructions": f"{MARK} edited",
        "original_exercise_uid": PRACTICE,
        "report_uid": await _report_on(world.driver, world.on_exercise),
        "student_uid": LEARNER,
    }
    client = world.clients[owner]
    url = path.format(uid=uid)
    response = await client.post(url, json=body) if method == "POST" else await client.get(url)
    assert response.status_code in (404, 405), (path, response.status_code, response.text)
    assert uid not in response.text, (path, response.text)
    assert await _revisions(world.driver) == before


async def test_the_learner_still_reads_the_revision(world: World) -> None:
    [[uid, *_rest]] = await _revisions(world.driver)
    response = await world.clients[LEARNER].get(f"/api/revised-exercises/view?uid={uid}")
    assert response.status_code == 200, response.text
    assert f"{MARK} revise this" in response.text
