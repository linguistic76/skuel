"""The Ku page's two learner writes land on a published Ku only.

``POST /api/ku/{uid}/mark-studying`` writes ``(user)-[:IN_PROGRESS]->(Ku)`` and
``POST /api/ku/{uid}/mark-understood`` writes ``(user)-[:MASTERED]->(Ku)``. Each is a
learner's own self-report, and the uid is the request's. The write's own MATCH admits
the far end — a published Ku — so a draft Ku, a PathStep, the caller's own Task,
another user's Task and a uid that names nothing write no edge and are answered
exactly alike: the fragment a refusal renders names no state, so no refusal confirms
that a node exists.

Tasks are made at the real create door; the Kus and the PathStep are seeded, since
none has an HTTP create door.
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

MARK = "zzzkulearn"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = seed_user_uid(f"{LEARNER_MARK}")
OTHER = seed_user_uid(f"{OTHER_MARK}")
KU_PUBLISHED = f"ku.{LEARNER_MARK}.published"
KU_DRAFT = f"ku.{LEARNER_MARK}.draft"
PS_PUBLISHED = f"ps.{LEARNER_MARK}.published"
MISSING = f"ku.{LEARNER_MARK}.missing"

DOORS = {"mark-studying": "IN_PROGRESS", "mark-understood": "MASTERED"}


async def _seed(driver: AsyncDriver) -> None:
    # The published Ku carries no publication_state — the NULL-tolerant case the
    # predicate must keep; the draft is marked 'draft', the property it reads.
    async with driver.session() as session:
        for uid, label, entity_type, state in (
            (KU_PUBLISHED, "Ku", "ku", None),
            (KU_DRAFT, "Ku", "ku", "draft"),
            (PS_PUBLISHED, "PathStep", "path_step", "published"),
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

    async def post(self, door: str, uid: str) -> httpx.Response:
        return await self.learner.post(f"/api/ku/{uid}/{door}")

    async def learning_states(self, far_uid: str) -> set[str]:
        """The learner's learning-state edges onto ``far_uid`` (the OWNS edge on the
        learner's own Task is not one)."""
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (:User {uid: $user})-[r]->({uid: $far}) WHERE type(r) IN $states "
                "RETURN type(r) AS type",
                user=LEARNER,
                far=far_uid,
                states=list(DOORS.values()),
            )
            return {row["type"] async for row in result}


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
    ):
        await _seed(driver)
        learner_task = await create(learner, "tasks", f"{MARK}-own-task")
        other_task = await create(other, "tasks", f"{MARK}-other-task")
        yield World(driver, learner, learner_task, other_task)


def _fragment(response: httpx.Response, uid: str) -> tuple[int, str]:
    return response.status_code, response.text.replace(uid, "<uid>")


async def test_a_published_ku_takes_both_learning_states(world: World) -> None:
    """Positive control: studying writes IN_PROGRESS, understood writes MASTERED."""
    for door, edge in DOORS.items():
        response = await world.post(door, KU_PUBLISHED)
        assert response.status_code == 200, (door, response.text)
        assert edge in await world.learning_states(KU_PUBLISHED), door


@pytest.mark.parametrize("door", list(DOORS))
@pytest.mark.parametrize(
    "far",
    [KU_DRAFT, PS_PUBLISHED, "learner_task", "other_task", MISSING],
    ids=["draft-ku", "published-path-step", "own-task", "other-task", "missing"],
)
async def test_anything_but_a_published_ku_is_refused_as_missing(
    world: World, door: str, far: str
) -> None:
    """No edge is written, and the fragment is the one a uid that names nothing gets."""
    far_uid = world.uid(far)

    response = await world.post(door, far_uid)

    assert _fragment(response, far_uid) == _fragment(await world.post(door, MISSING), MISSING)
    assert await world.learning_states(far_uid) == set()
