"""Exercises are authored only in the content vault — the in-app doors answer nothing.

ADR-091 S4: there is no other way to create or edit an exercise. The CRUD API
(``/api/exercises/create|update|delete|get|list``), the authoring pages (``/exercises``,
``/exercises/new``, ``/exercises/{uid}/edit``, ``/exercises/{uid}/view``) and the
requirement doors (``/api/exercises/require-knowledge``, ``/unrequire-knowledge``) are
gone, so each answers 404 or 405 and writes nothing — even for the teacher who owns an
exercise the retired create door once wrote.

The scopes those doors wrote go with them. An owned PERSONAL exercise anchored to a
published step no longer routes a feedback request to its owner (the owner route,
ADR-088 §9, is retired by S3), and an exercise shared with a group no longer admits the
group's members or files their requests with the group (group assignment, ADR-040).
Both are seeded here as the retired create door wrote them.

Controls: a learner in progress on the step still opens, downloads and turns in on the
vault exercise, and the request reaches the teacher its file names; a learner with no
tie to it is refused and nothing is written.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
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

MARK = "zzzexvaultonly"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
NAMED_MARK = f"{MARK}n"
AUTHOR_MARK = f"{MARK}a"
LEARNER_MARK = f"{MARK}l"
IDLE_MARK = f"{MARK}i"
NAMED = f"user_{NAMED_MARK}"  # the teacher the vault exercise names
AUTHOR = f"user_{AUTHOR_MARK}"  # a teacher who owns what the retired create door wrote
LEARNER = f"user_{LEARNER_MARK}"  # in progress on the step, member of AUTHOR's class
IDLE = f"user_{IDLE_MARK}"  # no tie to any exercise
STEP = f"ps.{MARK}.step"
KU = f"ku.{MARK}.idea"
PRACTICE = f"ex.{MARK}.practice"
# What the retired create door wrote: owned, uid-generated, carrying its scope.
ANCHORED = f"ex_{AUTHOR_MARK}_anchored"
ASSIGNED = f"ex_{AUTHOR_MARK}_assigned"
DOOMED = f"ex_{AUTHOR_MARK}_doomed"
CLASS = f"group_{AUTHOR_MARK}_class"
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


def _write(vault: Path, name: str, text: str) -> None:
    path = vault / f"{name}.md"
    path.write_text(text)
    touch_forward(path)


def _vault(vault: Path) -> None:
    _write(vault, "idea", f"---\ntype: ku\nuid: {KU}\ntitle: {MARK} idea\n---\nAn idea.\n")
    _write(
        vault,
        "step",
        f"---\ntype: ps\nuid: {STEP}\ntitle: {MARK} step\nexercise_uids:\n  - {PRACTICE}\n"
        "---\nThe step's lesson.\n",
    )
    _write(
        vault,
        "practice",
        f"---\ntype: exercise\nuid: {PRACTICE}\ntitle: {MARK} practice\nscope: curriculum\n"
        f"instructions: Describe one thing you noticed.\nteacher: {NAMED}\n---\n",
    )


async def _seed_retired_door_shapes(driver: AsyncDriver) -> None:
    """Three exercises as the retired create door wrote them: the node with its scope and
    ``owner_uid``, the owner's ``OWNS`` edge, the anchored one's ``path_step_uid`` dual
    write with the step's ``HAS_EXERCISE``, and the assigned one's ``group_uid`` with its
    ``SHARED_WITH_GROUP`` share to the author's class. The anchored one requires the Ku,
    as the retired requirement door wrote it."""
    async with driver.session() as session:
        await session.run(
            """
            MATCH (author:User {uid: $author}), (learner:User {uid: $learner})
            MATCH (step:Entity:PathStep {uid: $step}), (ku:Entity:Ku {uid: $ku})
            MERGE (g:Group {uid: $group})
            SET g.name = $group, g.is_active = true, g.owner_uid = $author
            MERGE (author)-[:OWNS]->(g)
            MERGE (learner)-[:MEMBER_OF]->(g)
            WITH author, step, ku, g
            UNWIND [
                {uid: $anchored, scope: 'personal', ps: $step, group: null},
                {uid: $assigned, scope: 'assigned', ps: null, group: $group},
                {uid: $doomed, scope: 'personal', ps: null, group: null}
            ] AS row
            MERGE (ex:Entity:Exercise {uid: row.uid})
            SET ex.entity_type = 'exercise', ex.title = row.uid, ex.scope = row.scope,
                ex.instructions = row.uid + ' instructions', ex.model = 'claude-sonnet-4-6',
                ex.status = 'active', ex.owner_uid = $author, ex.path_step_uid = row.ps,
                ex.group_uid = row.group, ex.created_at = datetime(), ex.updated_at = datetime()
            MERGE (author)-[:OWNS]->(ex)
            WITH ex, row, step, ku, g
            CALL (ex, row, ku) {
                WITH ex, row, ku WHERE row.uid = $anchored
                MERGE (ex)-[:REQUIRES_KNOWLEDGE]->(ku)
            }
            CALL (ex, row, step) {
                WITH ex, row, step WHERE row.ps IS NOT NULL
                MERGE (step)-[:HAS_EXERCISE]->(ex)
            }
            CALL (ex, row, g) {
                WITH ex, row, g WHERE row.group IS NOT NULL
                MERGE (ex)-[:SHARED_WITH_GROUP {shared_at: datetime()}]->(g)
            }
            """,
            author=AUTHOR,
            learner=LEARNER,
            step=STEP,
            ku=KU,
            group=CLASS,
            anchored=ANCHORED,
            assigned=ASSIGNED,
            doomed=DOOMED,
        )


async def _exercise_state(driver: AsyncDriver) -> dict[str, Any]:  # boundary: raw graph read
    """What a successful authoring request would change: titles, requirements, count."""
    async with driver.session() as session:
        record = await (
            await session.run(
                """
                MATCH (ex:Entity {entity_type: 'exercise'})
                WHERE ex.uid CONTAINS $mark
                OPTIONAL MATCH (ex)-[r:REQUIRES_KNOWLEDGE]->()
                WITH ex, count(r) AS requirements
                ORDER BY ex.uid
                RETURN collect([ex.uid, ex.title, requirements]) AS rows
                """,
                mark=MARK,
            )
        ).single()
    assert record is not None
    return {"rows": record["rows"]}


async def _entries(driver: AsyncDriver, owner: str) -> int:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:User {uid: $owner})-[:OWNS]->(e:Entity:UserEntry) RETURN count(e) AS n",
                owner=owner,
            )
        ).single()
    assert record is not None
    return int(record["n"])


async def _feedback_edges(driver: AsyncDriver, entry_uid: str) -> set[tuple[str, str]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Entity {uid: $entry})-[r:SUBMITTED_TO_TEACHER|SUBMITTED_TO_GROUP]->(x)
            RETURN type(r) AS type, x.uid AS far
            """,
            entry=entry_uid,
        )
        return {(record["type"], record["far"]) async for record in result}


async def _turn_in(client: httpx.AsyncClient, exercise_uid: str) -> httpx.Response:
    return await client.post(
        "/api/user-entries/upload",
        files={"file": ("work.md", f"{MARK} work".encode(), "text/markdown")},
        data={"pipeline": "teacher_review", "fulfills_exercise_uid": exercise_uid},
    )


class World:
    def __init__(self, driver: AsyncDriver, clients: dict[str, httpx.AsyncClient]) -> None:
        self.driver = driver
        self.clients = clients


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(
    skuel_app: Any,  # boundary: fasthtml-app
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    vault = tmp_path_factory.mktemp("content_vault")
    async with (
        signed_in_client(skuel_app, NAMED, NAMED_MARK) as named,
        signed_in_client(skuel_app, AUTHOR, AUTHOR_MARK) as author,
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, IDLE, IDLE_MARK) as idle,
    ):
        try:
            for uid in (NAMED, AUTHOR):
                await _set_role(driver, uid, "teacher")
            for uid in (LEARNER, IDLE):
                await _set_role(driver, uid, "member")
            _vault(vault)
            await sync_vault(driver, vault)
            await _seed_retired_door_shapes(driver)
            started = await learner.post(
                f"/explore/ps/{STEP}/progress", data={"state": "learning", "review": "true"}
            )
            assert started.status_code == 200, started.text
            yield World(driver, {NAMED: named, AUTHOR: author, LEARNER: learner, IDLE: idle})
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


# =============================================================================
# The authoring doors are gone — each asked by the teacher who owns the exercise
# =============================================================================

_RETIRED_DOORS: list[tuple[str, str, dict[str, Any] | None]] = [  # boundary: JSON bodies
    ("POST", "/api/exercises/create", {"name": f"{MARK} new", "instructions": "x"}),
    ("POST", f"/api/exercises/update?uid={ANCHORED}", {"name": f"{MARK} renamed"}),
    ("POST", f"/api/exercises/delete?uid={DOOMED}", None),
    ("POST", "/api/exercises/require-knowledge", {"exercise_uid": ASSIGNED, "curriculum_uid": KU}),
    (
        "POST",
        "/api/exercises/unrequire-knowledge",
        {"exercise_uid": ANCHORED, "curriculum_uid": KU},
    ),
    ("GET", f"/api/exercises/get?uid={ANCHORED}", None),
    ("GET", "/api/exercises/list", None),
    ("GET", "/exercises", None),
    ("GET", "/exercises/content", None),
    ("GET", "/exercises/new", None),
    ("GET", f"/exercises/{ANCHORED}/edit", None),
    ("GET", f"/exercises/{ANCHORED}/view", None),
]


@pytest.mark.parametrize(("method", "path", "body"), _RETIRED_DOORS)
async def test_the_retired_authoring_door_answers_nothing_and_writes_nothing(
    world: World,
    method: str,
    path: str,
    body: dict[str, Any] | None,  # boundary: JSON body
) -> None:
    before = await _exercise_state(world.driver)
    client = world.clients[AUTHOR]
    response = await client.post(path, json=body) if method == "POST" else await client.get(path)
    assert response.status_code in (404, 405), (path, response.status_code, response.text)
    assert ANCHORED not in response.text, (path, response.text)
    assert await _exercise_state(world.driver) == before


# =============================================================================
# The retired scopes route nothing
# =============================================================================


async def test_an_owned_anchored_exercise_no_longer_reaches_its_owner(world: World) -> None:
    before = await _entries(world.driver, LEARNER)
    refused = await _turn_in(world.clients[LEARNER], ANCHORED)
    assert refused.status_code == 400, refused.text
    assert NO_TEACHER in refused.text
    assert await _entries(world.driver, LEARNER) == before


async def test_an_exercise_shared_with_a_group_admits_nobody_through_it(world: World) -> None:
    before = await _entries(world.driver, LEARNER)
    refused = await _turn_in(world.clients[LEARNER], ASSIGNED)
    assert refused.status_code == 403, refused.text
    assert await _entries(world.driver, LEARNER) == before


# =============================================================================
# Controls — the vault exercise is read and answered as before
# =============================================================================


async def test_the_learner_opens_and_downloads_the_vault_exercise(world: World) -> None:
    page = await world.clients[LEARNER].get(f"/exercises/get/content?uid={PRACTICE}")
    worksheet = await world.clients[LEARNER].get(f"/api/exercises/md?uid={PRACTICE}")
    assert page.status_code == 200, page.text
    assert f"{MARK} practice" in page.text
    assert worksheet.status_code == 200, worksheet.text
    assert "Describe one thing you noticed." in worksheet.text


async def test_the_learner_turns_in_and_the_named_teacher_is_asked(world: World) -> None:
    turned_in = await _turn_in(world.clients[LEARNER], PRACTICE)
    assert turned_in.status_code == 201, turned_in.text
    entry = str(turned_in.json()["user_entry"]["uid"])
    assert await _feedback_edges(world.driver, entry) == {("SUBMITTED_TO_TEACHER", NAMED)}
    queue = await world.clients[NAMED].get("/api/teaching/review-queue")
    assert entry in [str(item["submission_uid"]) for item in queue.json()]


async def test_a_learner_with_no_tie_is_refused_and_nothing_is_written(world: World) -> None:
    refused = await _turn_in(world.clients[IDLE], PRACTICE)
    assert refused.status_code == 403, refused.text
    assert await _entries(world.driver, IDLE) == 0
