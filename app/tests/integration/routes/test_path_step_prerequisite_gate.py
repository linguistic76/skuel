"""A learner starts a path step only once every published prerequisite in its chain is mastered.

The chain is what the step requires through REQUIRES_STEP or REQUIRES_KNOWLEDGE, directly
or through another prerequisite; met is the learner's MASTERED edge. A draft prerequisite
is withheld, so it neither shows nor blocks. Every door that starts a step asks the one
gate (``PsPrerequisiteGate``) — the start door, the step page's progress door, and both
engage doors — and the step page and the chain door read the same chain, so a step shown
as ready is a step every door admits.

The doors that start nothing — Mark as read, Review again, and recording progress on a
step's Kus — act only on a step the learner holds in progress, so none of them is a way
round the gate. A mastered step is not started again.

The curriculum is seeded (no HTTP door authors it); every write here goes through a real
door of the app.

    first ◀─REQUIRES_STEP── second ◀─REQUIRES_STEP── third       (a chain)
    draft ◀─REQUIRES_STEP── after_draft                         (a draft prerequisite)
    hidden: a draft step, with a Ku, that requires nothing

Third and Hidden each name a task template, so an engagement a door wrongly admits
spawns the learner a task rather than failing for want of templates.
"""

from __future__ import annotations

import html
import json
import re
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import EntityStatus
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.task_template import TaskTemplate
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client

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

MARK = "zzzprereqgate"
LEARNER = seed_user_uid(MARK)
FIRST = f"ps.{MARK}.first"
SECOND = f"ps.{MARK}.second"
THIRD = f"ps.{MARK}.third"
DRAFT = f"ps.{MARK}.draft"
AFTER_DRAFT = f"ps.{MARK}.after-draft"
HIDDEN = f"ps.{MARK}.hidden"
KU = f"ku.{MARK}.concept"
TEMPLATES = {THIRD: f"ttpl.{MARK}.third", HIDDEN: f"ttpl.{MARK}.hidden"}
MISSING = f"ps.{MARK}.missing"
STEPS = (FIRST, SECOND, THIRD, DRAFT, AFTER_DRAFT, HIDDEN)
LEARNER_EDGES = ("IN_PROGRESS", "MARKED_AS_READ", "MASTERED", "ENGAGED_WITH")

_SEED = """
UNWIND $steps AS step
CREATE (s:Entity:PathStep {uid: step.uid, entity_type: 'path_step', title: step.title,
                           status: 'active'})
SET s.publication_state = step.state
WITH collect(s) AS created
MATCH (first:PathStep {uid: $first}), (second:PathStep {uid: $second}),
      (third:PathStep {uid: $third}), (draft:PathStep {uid: $draft}),
      (after:PathStep {uid: $after_draft}), (hidden:PathStep {uid: $hidden})
CREATE (third)-[:REQUIRES_STEP]->(second)
CREATE (second)-[:REQUIRES_STEP]->(first)
CREATE (after)-[:REQUIRES_STEP]->(draft)
CREATE (ku:Entity:Ku {uid: $ku, entity_type: 'ku', title: 'Concept', status: 'active'})
// The Ku-progress door reads a step's Kus off CONTAINS_KNOWLEDGE (``LpService.get_step``).
CREATE (hidden)-[:CONTAINS_KNOWLEDGE]->(ku)
CREATE (third)-[:CONTAINS_KNOWLEDGE]->(ku)
"""


async def _seed(driver: AsyncDriver) -> None:
    task_templates = build_production_backends(driver)["task_template_backend"]
    for step_uid, template_uid in TEMPLATES.items():
        created = await task_templates.create(
            TaskTemplate(
                uid=template_uid,
                title=f"Practise {step_uid}",
                status=EntityStatus.ACTIVE,
                due_offset=RelativeOffset(days=7),
            )
        )
        assert created.is_ok, created
    steps = [
        {"uid": FIRST, "title": "First", "state": None},
        {"uid": SECOND, "title": "Second", "state": "published"},
        {"uid": THIRD, "title": "Third", "state": "published"},
        {"uid": DRAFT, "title": "Draft", "state": "draft"},
        {"uid": AFTER_DRAFT, "title": "After draft", "state": "published"},
        {"uid": HIDDEN, "title": "Hidden", "state": "draft"},
    ]
    async with driver.session() as session:
        await session.run(
            _SEED,
            steps=steps,
            first=FIRST,
            second=SECOND,
            third=THIRD,
            draft=DRAFT,
            after_draft=AFTER_DRAFT,
            hidden=HIDDEN,
            ku=KU,
        )
        await session.run(
            """
            UNWIND $pairs AS pair
            MATCH (s:PathStep {uid: pair.step}), (t:Entity {uid: pair.template})
            CREATE (s)-[:HAS_TASK_TEMPLATE]->(t)
            """,
            pairs=[{"step": step, "template": template} for step, template in TEMPLATES.items()],
        )


class World:
    def __init__(self, driver: AsyncDriver, learner: httpx.AsyncClient) -> None:
        self.driver = driver
        self.learner = learner

    async def edges(self, far_uid: str) -> set[str]:
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (:User {uid: $user})-[r]->({uid: $far}) RETURN type(r) AS type",
                user=LEARNER,
                far=far_uid,
            )
            return {row["type"] async for row in result}

    async def master(self, *uids: str) -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: $user}), (n:Entity) WHERE n.uid IN $uids
                MERGE (u)-[r:MASTERED]->(n)
                SET r.mastered_at = datetime(), r.mastery_score = 1.0, r.confidence = 1.0,
                    r.method = 'derived'
                """,
                user=LEARNER,
                uids=list(uids),
            )

    async def clear(self) -> None:
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (:User {uid: $user})-[r]->(n)
                WHERE type(r) IN $types AND n.uid IN $uids
                DELETE r
                """,
                user=LEARNER,
                types=list(LEARNER_EDGES),
                uids=[*STEPS, KU],
            )
            # What an engagement spawned.
            await session.run(
                "MATCH (:User {uid: $user})-[:OWNS]->(n) DETACH DELETE n", user=LEARNER
            )

    async def spawned(self) -> int:
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (:User {uid: $user})-[:OWNS]->(n:Task) RETURN count(n) AS n",
                    user=LEARNER,
                )
            ).single()
        assert record is not None
        return int(record["n"])


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: FastHTMLApp) -> AsyncIterator[World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, LEARNER, MARK) as learner:
        await _seed(driver)
        yield World(driver, learner)


@pytest_asyncio.fixture(loop_scope="session")
async def fresh(world: World) -> AsyncIterator[World]:
    await world.clear()
    yield world
    await world.clear()


async def _progress(world: World, uid: str, **form: str) -> httpx.Response:
    return await world.learner.post(f"/explore/ps/{uid}/progress", data=form)


# The doors that start a step: (path, form).
START_DOORS = [
    ("/explore/ps/{u}/progress", {"state": "learning", "review": "false"}),
    ("/api/path-steps/{u}/start", None),
    ("/api/ps/{u}/engage", None),
    ("/explore/ps/{u}/engage", None),
]
START_DOOR_IDS = ["progress", "start", "api-engage", "explore-engage"]


@pytest.mark.parametrize(("path", "form"), START_DOORS, ids=START_DOOR_IDS)
async def test_no_door_starts_a_step_whose_chain_is_unmastered(
    fresh: World, path: str, form: dict[str, str] | None
) -> None:
    """Third requires Second, which requires First. Mastering Second alone is not enough:
    the chain still holds First, unmastered."""
    await fresh.master(SECOND)

    response = await fresh.learner.post(path.format(u=THIRD), data=form)

    assert not (await fresh.edges(THIRD)) & {"IN_PROGRESS", "ENGAGED_WITH"}
    assert await fresh.spawned() == 0
    if path == "/api/path-steps/{u}/start":
        assert "Prerequisites to clear" in response.text
    elif path == "/explore/ps/{u}/engage":
        # The engage group re-renders as it was: nothing was engaged.
        assert "Engage with this Path Step" in response.text
    else:
        assert response.status_code == 422, response.text
        assert response.headers["x-toast-message"] == "Master First before starting this step."


@pytest.mark.parametrize(("path", "form"), START_DOORS, ids=START_DOOR_IDS)
async def test_a_step_starts_once_its_whole_chain_is_mastered(
    fresh: World, path: str, form: dict[str, str] | None
) -> None:
    await fresh.master(FIRST, SECOND)

    response = await fresh.learner.post(path.format(u=THIRD), data=form)

    assert response.status_code == 200, response.text
    if "engage" in path:
        assert "ENGAGED_WITH" in await fresh.edges(THIRD)
        assert await fresh.spawned() == 1
    else:
        assert "IN_PROGRESS" in await fresh.edges(THIRD)


async def test_a_draft_prerequisite_does_not_block(fresh: World) -> None:
    """Nobody can master what no reader names."""
    response = await _progress(fresh, AFTER_DRAFT, state="learning")

    assert response.status_code == 200, response.text
    assert "IN_PROGRESS" in await fresh.edges(AFTER_DRAFT)


@pytest.mark.parametrize(("path", "form"), START_DOORS, ids=START_DOOR_IDS)
async def test_a_draft_step_is_refused_as_missing_at_every_start_door(
    fresh: World, path: str, form: dict[str, str] | None
) -> None:
    refused = await fresh.learner.post(path.format(u=HIDDEN), data=form)
    missing = await fresh.learner.post(path.format(u=MISSING), data=form)

    assert not await fresh.edges(HIDDEN)
    assert await fresh.spawned() == 0
    assert refused.status_code == missing.status_code
    assert refused.headers.get("x-toast-message", "").replace(HIDDEN, "<uid>") == (
        missing.headers.get("x-toast-message", "").replace(MISSING, "<uid>")
    )


# ------------------------------------------------- the doors that start nothing


@pytest.mark.parametrize(
    "form",
    [{"state": "read"}, {"state": "learning", "review": "true"}],
    ids=["mark-read", "review-again"],
)
async def test_a_step_never_started_cannot_be_marked_or_reviewed(
    fresh: World, form: dict[str, str]
) -> None:
    """Marking an unstarted step read, then Review again, would start it past the gate."""
    response = await _progress(fresh, THIRD, **form)

    assert response.status_code == 422, response.text
    assert not await fresh.edges(THIRD)


async def test_the_api_mark_read_door_leaves_a_step_never_started_alone(fresh: World) -> None:
    response = await fresh.learner.post(f"/api/path-steps/{THIRD}/mark-read")

    assert "Error" in response.text
    assert not await fresh.edges(THIRD)


async def test_read_then_review_again_keeps_one_hold(fresh: World) -> None:
    assert (await _progress(fresh, FIRST, state="learning")).status_code == 200
    assert (await _progress(fresh, FIRST, state="read")).status_code == 200
    assert await fresh.edges(FIRST) == {"IN_PROGRESS", "MARKED_AS_READ"}

    response = await _progress(fresh, FIRST, state="learning", review="true")

    assert response.status_code == 200, response.text
    assert await fresh.edges(FIRST) == {"IN_PROGRESS"}


@pytest.mark.parametrize(
    "form",
    [
        {"state": "learning", "review": "true"},
        {"state": "learning", "review": "false"},
        {"state": "read"},
    ],
    ids=["review-again", "start", "mark-read"],
)
async def test_a_mastered_step_takes_no_hold_back(fresh: World, form: dict[str, str]) -> None:
    """Mastery is terminal: no door puts an in-progress hold, or an enrollment slot, back on it."""
    await fresh.master(FIRST)

    response = await _progress(fresh, FIRST, **form)

    assert response.status_code == 422, response.text
    assert await fresh.edges(FIRST) == {"MASTERED"}


async def test_progress_on_a_steps_kus_needs_the_step_started(fresh: World) -> None:
    """Self-reported mastery of a step's Kus reaches only a step its learner was admitted to."""
    body = {"step_uid": THIRD, "mastery_level": 0.9, "completed": True}

    refused = await fresh.learner.post("/api/pathways/progress", json=body)

    assert refused.status_code == 422, refused.text
    assert "MASTERED" not in await fresh.edges(KU)

    await fresh.master(FIRST, SECOND)
    assert (await _progress(fresh, THIRD, state="learning")).status_code == 200

    admitted = await fresh.learner.post("/api/pathways/progress", json=body)

    assert admitted.status_code == 201, admitted.text
    assert "MASTERED" in await fresh.edges(KU)


async def test_progress_on_a_draft_steps_kus_is_refused_as_missing(fresh: World) -> None:
    body = {"step_uid": HIDDEN, "mastery_level": 0.9, "completed": True}

    response = await fresh.learner.post("/api/pathways/progress", json=body)

    assert response.status_code == 404, response.text
    assert "MASTERED" not in await fresh.edges(KU)


# -------------------------------------------------- the page and the chain door


def _blocking(page: str) -> list[dict[str, object]]:
    match = re.search(r"""x-data=(['"])pathstep\((.*?)\)\1""", page, re.DOTALL)
    assert match, "the page carries no pathstep seed"
    blocking: list[dict[str, object]] = json.loads(html.unescape(match.group(2)))["blocking"]
    return blocking


async def test_the_page_and_the_chain_door_read_the_chain_the_gate_reads(fresh: World) -> None:
    await fresh.master(SECOND)

    page = await fresh.learner.get(f"/explore/ps/{THIRD}/content")
    chain = await fresh.learner.get(f"/api/path-steps/prerequisites?step_uid={THIRD}")
    start = await _progress(fresh, THIRD, state="learning")

    assert page.status_code == 200, page.text
    assert [(row["uid"], row["status"], row["earlier"]) for row in _blocking(page.text)] == [
        (SECOND, "completed", False),
        (FIRST, "blocked", True),
    ]
    assert chain.status_code == 200, chain.text
    assert chain.json()["unmet_count"] == 1
    assert start.status_code == 422

    await fresh.master(FIRST)

    page = await fresh.learner.get(f"/explore/ps/{THIRD}/content")
    chain = await fresh.learner.get(f"/api/path-steps/prerequisites?step_uid={THIRD}")
    start = await _progress(fresh, THIRD, state="learning")

    assert {row["status"] for row in _blocking(page.text)} == {"completed"}
    assert chain.json()["unmet_count"] == 0
    assert start.status_code == 200, start.text
