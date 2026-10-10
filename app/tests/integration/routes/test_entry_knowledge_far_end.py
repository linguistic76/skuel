"""What an entry's knowledge reference may link — ``@ku()`` / ``@link(ku:…|ps:…)``
processed through ``POST /api/user-entries/process``.

A reference writes ``(entry)-[:APPLIES_KNOWLEDGE]->(far end)`` and credits the far end's
``times_reflected_in_entries`` (``KnowledgeReflectedInEntry`` → ``KuBackend.increment_substance``).
So the far end must be shared curriculum a learner can read — a published Ku or
PathStep (``UserEntryService.link_applied_knowledge``). Anything else — another user's
Task or exercise, the caller's own Task, a draft, a uid that names nothing — writes no
edge, credits nothing, and lands in the run's ``link_errors`` as the same line a missing
uid gets, so the summary does not tell a foreign node from an absent one.

Entries and the other user's Task and exercise are made at the real create doors; the
Kus and PathSteps are seeded, since neither has an HTTP create door.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

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

MARK = "zzzentryknow"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = f"user_{LEARNER_MARK}"  # a member who writes the entries
OTHER = f"user_{OTHER_MARK}"  # a teacher, so it owns an exercise through the create door
ROLES = {LEARNER: "member", OTHER: "teacher"}
KU_PUBLISHED = f"ku.{LEARNER_MARK}.published"
KU_DRAFT = f"ku.{LEARNER_MARK}.draft"
PS_PUBLISHED = f"ps.{LEARNER_MARK}.published"
PS_DRAFT = f"ps.{LEARNER_MARK}.draft"
MISSING = f"ku.{LEARNER_MARK}.missing"
COUNTER = "times_reflected_in_entries"


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


async def _seed(driver: AsyncDriver) -> None:
    # A draft is publication_state 'draft' — the property build_publication_clause reads.
    async with driver.session() as session:
        for uid, label, entity_type, state in (
            (KU_PUBLISHED, "Ku", "ku", None),
            (KU_DRAFT, "Ku", "ku", "draft"),
            (PS_PUBLISHED, "PathStep", "path_step", "published"),
            (PS_DRAFT, "PathStep", "path_step", "draft"),
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


async def _delete_owned(driver: AsyncDriver, users: list[str]) -> None:
    """Generated uids carry no mark — remove what the users own by owner."""
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User)-[:OWNS]->(n) WHERE u.uid IN $users DETACH DELETE n", users=users
        )


class World:
    def __init__(
        self,
        driver: AsyncDriver,
        learner: httpx.AsyncClient,
        learner_task: str,
        other_task: str,
        other_exercise: str,
    ) -> None:
        self.driver = driver
        self.learner = learner
        self.learner_task = learner_task
        self.other_task = other_task
        self.other_exercise = other_exercise

    async def reflect(self, link: str) -> tuple[str, list[str]]:
        """Write and process one entry whose line references ``link``; returns the
        entry uid and the run's ``link_errors``."""
        created = await self.learner.post(
            "/api/user-entries",
            json={
                "title": f"{MARK} entry {link}",
                "content": f"- [ ] {MARK} reflection @context(task) @link({link})\n",
                "pipeline": "extract_activities",
            },
        )
        assert created.status_code == 201, created.text
        entry_uid = str(created.json()["user_entry"]["uid"])
        processed = await self.learner.post(
            "/api/user-entries/process",
            json={"uid": entry_uid, "pipeline": "extract_activities"},
        )
        assert processed.status_code == 200, processed.text
        summary = processed.json()["user_entry"]["metadata"]["activity_extraction"]
        return entry_uid, list(summary["link_errors"])

    async def counter(self, uid: str) -> int:
        async with self.driver.session() as session:
            record = await (
                await session.run(
                    f"MATCH (n:Entity {{uid: $uid}}) RETURN coalesce(n.{COUNTER}, 0) AS n",
                    uid=uid,
                )
            ).single()
        assert record is not None, uid
        return int(record["n"])

    async def applies(self, entry_uid: str, far_uid: str) -> bool:
        edges = await edges_between(self.driver, entry_uid, far_uid)
        return any(e.type == "APPLIES_KNOWLEDGE" and e.source == entry_uid for e in edges)


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
    ):
        for uid, role in ROLES.items():
            await _set_role(driver, uid, role)
        try:
            await _seed(driver)
            learner_task = await create(learner, "tasks", f"{MARK}-own-task")
            other_task = await create(other, "tasks", f"{MARK}-other-task")
            other_exercise = await create(
                other, "exercises", f"{MARK}-essay", name=f"{MARK}-essay", instructions="essay"
            )
            yield World(driver, learner, learner_task, other_task, other_exercise)
        finally:
            await _delete_owned(driver, list(ROLES))


@pytest.mark.parametrize(
    ("prefix", "far_uid"),
    [("ku", KU_PUBLISHED), ("ps", PS_PUBLISHED)],
    ids=["published-ku", "published-path-step"],
)
async def test_a_published_ku_or_path_step_is_linked_and_credited(
    world: World, prefix: str, far_uid: str
) -> None:
    before = await world.counter(far_uid)

    entry_uid, link_errors = await world.reflect(f"{prefix}:{far_uid}")

    assert link_errors == []
    assert await world.applies(entry_uid, far_uid)
    assert await world.counter(far_uid) == before + 1


def _refusal_line(link_errors: list[str], entry_uid: str, far_uid: str) -> str:
    assert len(link_errors) == 1, link_errors
    return link_errors[0].replace(entry_uid, "<entry>").replace(far_uid, "<uid>")


@pytest.mark.parametrize(
    "far",
    ["other_task", "other_exercise", "learner_task", KU_DRAFT, PS_DRAFT],
    ids=["other-users-task", "other-users-exercise", "own-task", "draft-ku", "draft-path-step"],
)
async def test_anything_else_is_refused_like_a_missing_uid(world: World, far: str) -> None:
    far_uid = getattr(world, far, far)
    before = await world.counter(far_uid)

    entry_uid, link_errors = await world.reflect(f"ku:{far_uid}")
    missing_entry, missing_errors = await world.reflect(f"ku:{MISSING}")

    assert not await world.applies(entry_uid, far_uid)
    assert await world.counter(far_uid) == before, "a refused reference credits nothing"
    assert _refusal_line(link_errors, entry_uid, far_uid) == _refusal_line(
        missing_errors, missing_entry, MISSING
    )
