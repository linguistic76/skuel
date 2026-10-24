"""What a learner's own edges may point at — pins, PathStep learning state, and an
entry's PathStep context.

Each of these doors writes an edge from the caller (or the caller's Interaction) to a
uid the request names:

- ``POST /api/user/pins`` writes ``(user)-[:PINNED]->(far end)``. A published Ku or
  PathStep may be pinned, or an entity the caller owns.
- ``POST /api/path-steps/{uid}/{start,mark-read,bookmark}`` and
  ``POST /explore/ps/{uid}/{progress,bookmark}`` write ``IN_PROGRESS`` /
  ``MARKED_AS_READ`` / ``BOOKMARKED`` onto a published PathStep, and the step's detail
  fragment records ``VIEWED`` on one.
- An entry's ``about_path_step_uid`` becomes its turn-in Interaction's
  ``INTERACTION_DURING`` edge — a published PathStep, checked before the entry is
  written (``POST /api/user-entries``, ``/upload``).

Anything else — another user's Task, a draft, a node of another kind, the caller's own
Task where a PathStep is asked for — writes no edge and is answered exactly as a uid
that names nothing, so no refusal confirms that a node exists.

Tasks are made at the real create door; the Kus, PathSteps, LearningPath and the
curriculum exercise are seeded, since none has an HTTP create door.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    import httpx
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzlearneredge"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
OTHER = seed_user_uid(f"{OTHER_MARK}")
KU_PUBLISHED = f"ku.{LEARNER_MARK}.published"
KU_DRAFT = f"ku.{LEARNER_MARK}.draft"
PS_PUBLISHED = f"ps.{LEARNER_MARK}.published"
PS_DRAFT = f"ps.{LEARNER_MARK}.draft"
LP_PUBLISHED = f"lp.{LEARNER_MARK}.published"
EXERCISE = f"ex.{LEARNER_MARK}.curriculum"
MISSING = f"ps.{LEARNER_MARK}.missing"
LEARNER_EDGES = ("PINNED", "IN_PROGRESS", "MARKED_AS_READ", "BOOKMARKED", "VIEWED")


async def _seed(driver: AsyncDriver) -> None:
    # A draft is publication_state 'draft' — the property build_publication_clause reads.
    async with driver.session() as session:
        for uid, label, entity_type, state in (
            (KU_PUBLISHED, "Ku", "ku", None),
            (KU_DRAFT, "Ku", "ku", "draft"),
            (PS_PUBLISHED, "PathStep", "path_step", "published"),
            (PS_DRAFT, "PathStep", "path_step", "draft"),
            (LP_PUBLISHED, "LearningPath", "learning_path", "published"),
        ):
            await session.run(
                f"""
                CREATE (n:Entity:{label} {{uid: $uid, entity_type: $entity_type, title: $uid,
                                          status: 'active'}})
                SET n.publication_state = $state
                """,
                uid=uid,
                entity_type=entity_type,
                state=state,
            )
        # The exercise a learner in progress on the published step may turn in against.
        await session.run(
            """
            MATCH (s:PathStep {uid: $ps})
            CREATE (e:Entity:Exercise {uid: $ex, title: $ex, name: $ex, entity_type: 'exercise',
                                       scope: 'curriculum', status: 'active',
                                       instructions: 'curriculum instructions'})
            CREATE (s)-[:HAS_EXERCISE]->(e)
            """,
            ps=PS_PUBLISHED,
            ex=EXERCISE,
        )


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Generated uids carry no mark — remove what the users own by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )


def _refusal(response: httpx.Response, uid: str) -> tuple[int, str, object]:
    """A response as a client sees it, with the named uid and the clock taken out."""
    toast = response.headers.get("x-toast-message", "").replace(uid, "<uid>")
    if response.headers.get("content-type", "").startswith("application/json"):
        fields = {
            key: str(value).replace(uid, "<uid>")
            for key, value in response.json().items()
            if key != "timestamp"
        }
        return response.status_code, toast, fields
    return response.status_code, toast, response.text.replace(uid, "<uid>")


class World:
    def __init__(
        self, driver: AsyncDriver, learner: httpx.AsyncClient, learner_task: str, other_task: str
    ) -> None:
        self.driver = driver
        self.learner = learner
        self.learner_task = learner_task
        self.other_task = other_task

    def uid(self, name: str) -> str:
        return str(getattr(self, name, name))

    async def learner_edges(self, far_uid: str) -> set[str]:
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (:User {uid: $user})-[r]->({uid: $far}) RETURN type(r) AS type",
                user=LEARNER,
                far=far_uid,
            )
            return {row["type"] async for row in result}

    async def clear_learner_edges(self, far_uid: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                "MATCH (:User {uid: $user})-[r]->({uid: $far}) WHERE type(r) IN $types DELETE r",
                user=LEARNER,
                far=far_uid,
                types=list(LEARNER_EDGES),
            )

    async def entries_titled(self, title: str) -> int:
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (:User {uid: $user})-[:OWNS]->(e:UserEntry {title: $title}) "
                    "RETURN count(e) AS n",
                    user=LEARNER,
                    title=title,
                )
            ).single()
        assert record is not None
        return int(record["n"])

    async def interaction_context(self, far_uid: str) -> int:
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (i:Interaction {user_uid: $user})-[:INTERACTION_DURING]->({uid: $far}) "
                    "RETURN count(i) AS n",
                    user=LEARNER,
                    far=far_uid,
                )
            ).single()
        assert record is not None
        return int(record["n"])


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
    ):
        try:
            await _seed(driver)
            learner_task = await create(learner, "tasks", f"{MARK}-own-task")
            other_task = await create(other, "tasks", f"{MARK}-other-task")
            yield World(driver, learner, learner_task, other_task)
        finally:
            await _delete_owned(driver, [LEARNER, OTHER])


# --------------------------------------------------------------------------- pins


async def _pin(world: World, uid: str) -> httpx.Response:
    return await world.learner.post("/api/user/pins", json={"entity_uid": uid})


@pytest.mark.parametrize(
    "far",
    [KU_PUBLISHED, PS_PUBLISHED, "learner_task"],
    ids=["published-ku", "published-path-step", "own-task"],
)
async def test_a_published_ku_or_path_step_or_an_own_entity_is_pinned(
    world: World, far: str
) -> None:
    far_uid = world.uid(far)

    pinned = await _pin(world, far_uid)

    assert pinned.status_code == 200, pinned.text
    assert "PINNED" in await world.learner_edges(far_uid)
    unpinned = await world.learner.delete(f"/api/user/pins/{far_uid}")
    assert unpinned.status_code == 200, unpinned.text
    assert "PINNED" not in await world.learner_edges(far_uid)


@pytest.mark.parametrize(
    "far",
    ["other_task", KU_DRAFT, PS_DRAFT, LP_PUBLISHED],
    ids=["other-users-task", "draft-ku", "draft-path-step", "published-learning-path"],
)
async def test_anything_else_is_not_pinned_and_answers_as_missing(world: World, far: str) -> None:
    far_uid = world.uid(far)

    refused = await _pin(world, far_uid)
    missing = await _pin(world, MISSING)

    assert "PINNED" not in await world.learner_edges(far_uid)
    assert refused.status_code == 404, refused.text
    assert _refusal(refused, far_uid) == _refusal(missing, MISSING)
    assert "source_location" not in refused.text


async def test_unpinning_what_is_not_pinned_is_a_404_error(world: World) -> None:
    response = await world.learner.delete(f"/api/user/pins/{MISSING}")

    assert response.status_code == 404, response.text
    assert response.headers["content-type"].startswith("application/json")


# ----------------------------------------------------------- PathStep learning state

# (method path, form, the edge it writes)
STEP_DOORS = [
    ("/api/path-steps/{u}/start", None, "IN_PROGRESS"),
    ("/api/path-steps/{u}/mark-read", None, "MARKED_AS_READ"),
    ("/api/path-steps/{u}/bookmark", None, "BOOKMARKED"),
    ("/explore/ps/{u}/progress", {"state": "learning", "review": "true"}, "IN_PROGRESS"),
    ("/explore/ps/{u}/progress", {"state": "learning", "review": "false"}, "IN_PROGRESS"),
    ("/explore/ps/{u}/progress", {"state": "read"}, "MARKED_AS_READ"),
    ("/explore/ps/{u}/bookmark", {"on": "true"}, "BOOKMARKED"),
]
STEP_DOOR_IDS = [
    "start",
    "mark-read",
    "bookmark-toggle",
    "progress-review",
    "progress-enrol",
    "progress-read",
    "bookmark-set",
]


@pytest.mark.parametrize(("path", "form", "edge"), STEP_DOORS, ids=STEP_DOOR_IDS)
async def test_a_published_path_step_takes_the_learning_state(
    world: World, path: str, form: dict[str, str] | None, edge: str
) -> None:
    await world.clear_learner_edges(PS_PUBLISHED)

    response = await world.learner.post(path.format(u=PS_PUBLISHED), data=form)

    assert response.status_code == 200, response.text
    assert "Error" not in response.text
    assert edge in await world.learner_edges(PS_PUBLISHED)
    await world.clear_learner_edges(PS_PUBLISHED)


@pytest.mark.parametrize(("path", "form", "edge"), STEP_DOORS, ids=STEP_DOOR_IDS)
@pytest.mark.parametrize(
    "far",
    ["other_task", "learner_task", KU_PUBLISHED, PS_DRAFT],
    ids=["other-users-task", "own-task", "published-ku", "draft-path-step"],
)
async def test_anything_but_a_published_path_step_is_refused_as_missing(
    world: World, far: str, path: str, form: dict[str, str] | None, edge: str
) -> None:
    far_uid = world.uid(far)

    refused = await world.learner.post(path.format(u=far_uid), data=form)
    missing = await world.learner.post(path.format(u=MISSING), data=form)

    assert not (await world.learner_edges(far_uid)) & set(LEARNER_EDGES)
    assert _refusal(refused, far_uid) == _refusal(missing, MISSING)


async def test_opening_a_draft_step_records_no_view(world: World) -> None:
    await world.clear_learner_edges(PS_PUBLISHED)

    control = await world.learner.get(f"/explore/ps/{PS_PUBLISHED}/content")
    assert control.status_code == 200
    assert "VIEWED" in await world.learner_edges(PS_PUBLISHED)

    await world.learner.get(f"/explore/ps/{PS_DRAFT}/content")
    assert "VIEWED" not in await world.learner_edges(PS_DRAFT)
    await world.clear_learner_edges(PS_PUBLISHED)


# ------------------------------------------------------- an entry's PathStep context


async def _enrol(world: World) -> None:
    """In progress on the published step — what admits a turn-in against its exercise."""
    response = await world.learner.post(
        f"/explore/ps/{PS_PUBLISHED}/progress", data={"state": "learning", "review": "true"}
    )
    assert response.status_code == 200, response.text


async def _turn_in(world: World, title: str, about: str) -> httpx.Response:
    return await world.learner.post(
        "/api/user-entries",
        json={
            "title": title,
            "content": f"{MARK} worked answer",
            "pipeline": "extract_activities",
            "fulfills_exercise_uid": EXERCISE,
            "about_path_step_uid": about,
        },
    )


async def _upload(world: World, title: str, about: str) -> httpx.Response:
    return await world.learner.post(
        "/api/user-entries/upload",
        files={"file": ("answer.md", f"{MARK} uploaded answer".encode(), "text/markdown")},
        data={
            "title": title,
            "fulfills_exercise_uid": EXERCISE,
            "about_path_step_uid": about,
            "pipeline": "extract_activities",
        },
    )


# An entry door: (world, title, about_path_step_uid) -> its response.
type Door = Callable[[World, str, str], Awaitable[httpx.Response]]


@pytest.mark.parametrize("door", [_turn_in, _upload], ids=["json", "upload"])
async def test_a_published_path_step_is_the_turn_ins_context(world: World, door: Door) -> None:
    await _enrol(world)
    before = await world.interaction_context(PS_PUBLISHED)

    response = await door(world, f"{MARK} control {door.__name__}", PS_PUBLISHED)

    assert response.status_code == 201, response.text
    assert await world.interaction_context(PS_PUBLISHED) == before + 1


@pytest.mark.parametrize("door", [_turn_in, _upload], ids=["json", "upload"])
@pytest.mark.parametrize(
    "far",
    ["other_task", "learner_task", KU_PUBLISHED, PS_DRAFT],
    ids=["other-users-task", "own-task", "published-ku", "draft-path-step"],
)
async def test_any_other_context_refuses_the_entry_as_missing(
    world: World, far: str, door: Door
) -> None:
    await _enrol(world)
    far_uid = world.uid(far)
    title = f"{MARK} refused {door.__name__} {far}"

    refused = await door(world, title, far_uid)
    missing = await door(world, f"{title} missing", MISSING)

    assert refused.status_code == 404, refused.text
    assert _refusal(refused, far_uid) == _refusal(missing, MISSING)
    assert await world.entries_titled(title) == 0, "a refused entry is not written"
    assert await world.interaction_context(far_uid) == 0
