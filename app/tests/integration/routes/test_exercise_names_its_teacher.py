"""A feedback request on a vault exercise reaches the teacher its file names — and no one else.

Every exercise names its teacher in its vault file (ADR-091 S3): the ``teacher`` field,
written as ``(Exercise)-[:REVIEWED_BY]->(User)``. A learner's ``teacher_review`` turn-in
on the exercise is filed to that teacher directly,
``(entry)-[:SUBMITTED_TO_TEACHER]->(teacher)``, and reaches that teacher's review queue
and exercise list — never another teacher's, and never the learner's default group.
Work on a revision of the exercise goes to the same teacher (N8). Changing the file's
``teacher`` moves the edge on the next sync, and the next request with it.

The PathStep and the exercise enter through the content-vault sync (the one door for
curriculum); the learner starts the step at the real progress door and turns in at the
real upload door; the teacher requests the revision at the real review door.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client, sync_vault, touch_forward

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

MARK = "zzzexteacher"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
NAMED_MARK = f"{MARK}n"
OTHER_MARK = f"{MARK}o"
LEARNER_MARK = f"{MARK}l"
NAMED = seed_user_uid(f"{NAMED_MARK}")  # the teacher the exercise files name
OTHER = seed_user_uid(f"{OTHER_MARK}")  # a second teacher, named by no file until the handover
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
STEP = f"ps.{MARK}.step"
PRACTICE = f"ex.{MARK}.practice"
HANDOVER = f"ex.{MARK}.handover"


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


def _step_file(vault: Path) -> Path:
    path = vault / "step.md"
    path.write_text(
        "---\n"
        f"type: ps\nuid: {STEP}\ntitle: {MARK} step\n"
        f"exercise_uids:\n  - {PRACTICE}\n  - {HANDOVER}\n"
        "---\nThe step's lesson.\n"
    )
    touch_forward(path)
    return path


def _exercise_file(vault: Path, name: str, uid: str, teacher: str) -> Path:
    path = vault / f"{name}.md"
    path.write_text(
        "---\n"
        f"type: exercise\nuid: {uid}\ntitle: {MARK} {name}\nscope: curriculum\n"
        f"instructions: Describe one {name} you noticed.\nteacher: {teacher}\n"
        "---\n"
    )
    touch_forward(path)
    return path


async def _turn_in(client: httpx.AsyncClient, exercise_uid: str, title: str) -> str:
    response = await client.post(
        "/api/user-entries/upload",
        files={"file": (f"{title}.md", f"{MARK} {title}".encode(), "text/markdown")},
        data={"pipeline": "teacher_review", "fulfills_exercise_uid": exercise_uid},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["user_entry"]["uid"])


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


async def _teachers_of(driver: AsyncDriver, exercise_uid: str) -> set[str]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $ex})-[:REVIEWED_BY]->(t:User) RETURN t.uid AS uid",
            ex=exercise_uid,
        )
        return {record["uid"] async for record in result}


async def _queue(client: httpx.AsyncClient) -> list[str]:
    response = await client.get("/api/teaching/review-queue")
    assert response.status_code == 200, response.text
    return [str(item["submission_uid"]) for item in response.json()]


async def _exercise_list(client: httpx.AsyncClient) -> list[str]:
    response = await client.get("/api/teaching/exercises")
    assert response.status_code == 200, response.text
    return [str(item["uid"]) for item in response.json()]


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        vault: Path,
        clients: dict[str, httpx.AsyncClient],
        entry: str,
    ) -> None:
        self.driver = driver
        self.vault = vault
        self.clients = clients
        self.entry = entry  # the learner's turn-in on PRACTICE


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    vault = tmp_path_factory.mktemp("content_vault")
    async with (
        signed_in_client(skuel_app, NAMED, NAMED_MARK) as named,
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
    ):
        try:
            await _set_role(driver, NAMED, "teacher")
            await _set_role(driver, OTHER, "teacher")
            await _set_role(driver, LEARNER, "member")
            _step_file(vault)
            _exercise_file(vault, "practice", PRACTICE, NAMED)
            _exercise_file(vault, "handover", HANDOVER, NAMED)
            await sync_vault(driver, vault)

            started = await learner.post(
                f"/explore/ps/{STEP}/progress", data={"state": "learning", "review": "true"}
            )
            assert started.status_code == 200, started.text
            entry = await _turn_in(learner, PRACTICE, "practice")
            yield World(driver, vault, {NAMED: named, OTHER: other, LEARNER: learner}, entry)
        finally:
            async with driver.session() as session:
                await session.run(
                    """
                    MATCH (n)
                    WHERE n.uid CONTAINS $mark OR n.entity_uid CONTAINS $mark
                    DETACH DELETE n
                    """,
                    mark=MARK,
                )


async def test_the_vault_file_names_the_teacher_and_owns_nothing(world: World) -> None:
    assert await _teachers_of(world.driver, PRACTICE) == {NAMED}
    async with world.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (ex:Entity {uid: $ex}) RETURN COUNT { (:User)-[:OWNS]->(ex) } AS owners",
                ex=PRACTICE,
            )
        ).single()
    assert record is not None and record["owners"] == 0


async def test_the_request_is_filed_to_the_named_teacher(world: World) -> None:
    assert await _feedback_edges(world.driver, world.entry) == {("SUBMITTED_TO_TEACHER", NAMED)}


async def test_the_named_teacher_reads_it_in_the_queue_and_the_other_teacher_does_not(
    world: World,
) -> None:
    assert world.entry in await _queue(world.clients[NAMED])
    assert world.entry not in await _queue(world.clients[OTHER])


async def test_the_named_teacher_lists_the_exercise_and_the_other_teacher_does_not(
    world: World,
) -> None:
    assert PRACTICE in await _exercise_list(world.clients[NAMED])
    assert PRACTICE not in await _exercise_list(world.clients[OTHER])


async def test_a_changed_teacher_moves_the_edge_and_the_next_request(world: World) -> None:
    _exercise_file(world.vault, "handover", HANDOVER, OTHER)
    await sync_vault(world.driver, world.vault)
    assert await _teachers_of(world.driver, HANDOVER) == {OTHER}

    entry = await _turn_in(world.clients[LEARNER], HANDOVER, "handover")
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_TEACHER", OTHER)}
    assert entry in await _queue(world.clients[OTHER])
    assert entry not in await _queue(world.clients[NAMED])


async def test_work_on_a_revision_goes_to_the_exercises_teacher(world: World) -> None:
    """Last: the revision moves the first entry out of the pending queue."""
    requested = await world.clients[NAMED].post(
        f"/api/teaching/review/{world.entry}/revision",
        data={"instructions": f"{MARK} revise this", "fp_count": "0"},
    )
    assert "Revision requested." in requested.text, requested.text
    async with world.driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (rex:Entity:RevisedExercise)-[:REVISES_EXERCISE]->(:Entity {uid: $ex})
                WHERE rex.student_uid = $learner
                RETURN rex.uid AS uid
                """,
                ex=PRACTICE,
                learner=LEARNER,
            )
        ).single()
    assert record is not None
    revision = str(record["uid"])

    entry = await _turn_in(world.clients[LEARNER], revision, "revised")
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_TEACHER", NAMED)}
    assert entry in await _queue(world.clients[NAMED])
    assert entry not in await _queue(world.clients[OTHER])
