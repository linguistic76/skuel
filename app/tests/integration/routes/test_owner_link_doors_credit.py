"""Every door that writes an owner's knowledge link credits the links its write created.

Over the bootstrapped app (CORE tier, the app's bus and its substance subscribers):

- ``POST /api/habits/link-knowledge`` credits a newly linked Ku once
  (``times_built_into_habits`` +1); re-linking it, or linking the Ku the habit was
  created with, credits nothing, and the door answers ``{"linked": true}`` each time.
- ``POST /goals/generate-tasks`` credits a generated knowledge task's subject Ku once:
  the task's entity door writes no knowledge link, so the link door's write creates it.
- A vault sync of an Activity file's knowledge field (``connections.applies_knowledge``
  on a task, ``reinforces_knowledge`` on a habit, ``informed_by_knowledge`` on a choice)
  credits each link its first ingest writes, once. A second sync of the unchanged file
  and a ``--force`` sync credit nothing; a target added to the file credits only it; a
  dangling target writes and credits nothing; a pair grounding inferred becomes the
  file's link and is not credited again.
- An Event file's ``applies_knowledge`` credits nothing at the link: the event's
  knowledge is credited as practice when it is completed, once.

Each credit is read twice: the substance events the bus carried, and the counter on
the Ku the subscriber wrote.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events.knowledge_substance_events import (
    KnowledgeAppliedInTask,
    KnowledgeBuiltIntoHabit,
    KnowledgeBulkAppliedInTask,
    KnowledgeBulkBuiltIntoHabit,
    KnowledgeBulkInformedChoice,
    KnowledgeInformedChoice,
    KnowledgePracticedInEvent,
)
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    published,
    signed_in_client,
    sync_vault,
    write_vault_file,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp
    from core.events.base import BaseEvent
    from services_bootstrap import Services

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "ownerlinkcredit"
OWNER = seed_user_uid(f"{MARK}_owner")


def _ku(slug: str) -> str:
    return f"ku.{MARK}.{slug}"


KUS = [
    _ku(slug)
    for slug in (
        "habit-new",
        "habit-relink",
        "habit-at-create",
        "goal-subject",
        "vault-one",
        "vault-two",
        "vault-three",
        "vault-force",
        "vault-habit",
        "vault-choice",
        "vault-event",
        "vault-inferred",
        "vault-named",
    )
]

SUBSTANCE_EVENTS = (
    KnowledgeAppliedInTask,
    KnowledgeBulkAppliedInTask,
    KnowledgeBuiltIntoHabit,
    KnowledgeBulkBuiltIntoHabit,
    KnowledgeInformedChoice,
    KnowledgeBulkInformedChoice,
    KnowledgePracticedInEvent,
)


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Services
    driver: AsyncDriver


@dataclass(frozen=True)
class Credit:
    """One substance event: its class, the activity it names and the Kus it credits."""

    event: str
    source_uid: str
    knowledge_uids: tuple[str, ...]


def _credit(event: BaseEvent) -> Credit:
    """Read the activity and the Kus off whichever substance event this is."""
    match event:
        case KnowledgeAppliedInTask():
            return Credit(type(event).__name__, event.task_uid, (event.knowledge_uid,))
        case KnowledgeBulkAppliedInTask():
            return Credit(type(event).__name__, event.task_uid, event.knowledge_uids)
        case KnowledgeBuiltIntoHabit():
            return Credit(type(event).__name__, event.habit_uid, (event.knowledge_uid,))
        case KnowledgeBulkBuiltIntoHabit():
            return Credit(type(event).__name__, event.habit_uid, event.knowledge_uids)
        case KnowledgeInformedChoice():
            return Credit(type(event).__name__, event.choice_uid, (event.knowledge_uid,))
        case KnowledgeBulkInformedChoice():
            return Credit(type(event).__name__, event.choice_uid, event.knowledge_uids)
        case KnowledgePracticedInEvent():
            return Credit(type(event).__name__, event.event_uid, (event.knowledge_uid,))
    raise AssertionError(f"not a substance event: {event!r}")


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    services: Services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with signed_in_client(skuel_app, OWNER, MARK) as client:
        async with driver.session() as session:
            await session.run(
                """
                UNWIND $kus AS ku
                MERGE (k:Entity:Ku {uid: ku})
                SET k.title = ku, k.entity_type = 'ku', k.publication_state = 'published'
                """,
                kus=KUS,
            )
        yield Env(client=client, services=services, driver=driver)


async def _count(env: Env, ku_uid: str, counter: str) -> int:
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (k:Ku {uid: $uid}) RETURN coalesce(k[$counter], 0) AS n",
                uid=ku_uid,
                counter=counter,
            )
        ).single()
    assert record is not None, ku_uid
    return int(record["n"])


async def _link_habit(env: Env, habit: str, ku_uid: str) -> tuple[object, list[Credit]]:
    """Post one link at the habit door; returns its JSON answer and what it credited."""
    bus = env.services.event_bus
    assert bus is not None
    with published(bus, *SUBSTANCE_EVENTS) as seen:
        response = await env.client.post(
            "/api/habits/link-knowledge", json={"habit_uid": habit, "knowledge_uid": ku_uid}
        )
    assert response.status_code == 200, response.text
    return response.json(), [_credit(event) for event in seen]


async def _sync(env: Env, vault: Path, *, force: bool = False) -> list[Credit]:
    """One smart sync of ``vault`` on the app's bus; returns what it credited."""
    bus = env.services.event_bus
    assert bus is not None
    with published(bus, *SUBSTANCE_EVENTS) as seen:
        await sync_vault(env.driver, vault, force=force, event_bus=bus)
    return [_credit(event) for event in seen]


def _file(
    vault: Path,
    name: str,
    entity_type: str,
    field: str,
    targets: list[str],
    *extra: str,
) -> str:
    """One Activity file naming ``targets`` in its ``connections.{field}``; returns its uid."""
    uid = f"{entity_type}.{MARK}.{name}"
    write_vault_file(
        vault,
        name,
        entity_type=entity_type,
        uid=uid,
        owner=OWNER,
        connections={field: targets},
        extra=extra,
    )
    return uid


async def _applies(env: Env, source_uid: str) -> dict[str, bool]:
    """Each Ku ``source_uid`` applies -> whether the link is inferred (vs its owner's)."""
    async with env.driver.session() as session:
        result = await session.run(
            """
            MATCH (:Entity {uid: $uid})-[r:APPLIES_KNOWLEDGE]->(k:Ku)
            RETURN k.uid AS ku, coalesce(r.inferred, false) AS inferred
            """,
            uid=source_uid,
        )
        return {record["ku"]: bool(record["inferred"]) async for record in result}


# ---------------------------------------------------------------------------
# POST /api/habits/link-knowledge
# ---------------------------------------------------------------------------


async def test_linking_a_new_ku_to_a_habit_credits_it_once(env: Env) -> None:
    habit = await create(env.client, "habits", f"{MARK} breathe daily")
    ku = _ku("habit-new")
    before = await _count(env, ku, "times_built_into_habits")

    answer, credits = await _link_habit(env, habit, ku)

    assert answer == {"linked": True}
    assert credits == [Credit("KnowledgeBuiltIntoHabit", habit, (ku,))]
    assert await _count(env, ku, "times_built_into_habits") == before + 1


async def test_relinking_the_same_ku_to_a_habit_credits_nothing(env: Env) -> None:
    habit = await create(env.client, "habits", f"{MARK} stretch daily")
    ku = _ku("habit-relink")
    await _link_habit(env, habit, ku)
    before = await _count(env, ku, "times_built_into_habits")

    answer, credits = await _link_habit(env, habit, ku)

    assert answer == {"linked": True}
    assert credits == []
    assert await _count(env, ku, "times_built_into_habits") == before


async def test_linking_the_ku_a_habit_was_created_with_credits_nothing(env: Env) -> None:
    ku = _ku("habit-at-create")
    before = await _count(env, ku, "times_built_into_habits")
    habit = await create(env.client, "habits", f"{MARK} walk daily", linked_knowledge_uids=[ku])
    # The create door credited it.
    assert await _count(env, ku, "times_built_into_habits") == before + 1

    answer, credits = await _link_habit(env, habit, ku)

    assert answer == {"linked": True}
    assert credits == []
    assert await _count(env, ku, "times_built_into_habits") == before + 1


# ---------------------------------------------------------------------------
# POST /goals/generate-tasks
# ---------------------------------------------------------------------------


async def test_a_generated_knowledge_task_credits_its_subject_ku_once(env: Env) -> None:
    ku = _ku("goal-subject")
    goal = await create(env.client, "goals", f"{MARK} learn the subject")
    linked = await env.client.post(
        "/api/goals/link-knowledge", json={"goal_uid": goal, "knowledge_uid": ku}
    )
    assert linked.status_code == 200, linked.text
    before = await _count(env, ku, "times_applied_in_tasks")
    bus = env.services.event_bus
    assert bus is not None

    with published(bus, *SUBSTANCE_EVENTS) as seen:
        response = await env.client.post(f"/goals/generate-tasks?uid={goal}&auto_create=true")

    assert response.status_code == 200, response.text
    learn = [task["uid"] for task in response.json() if task["title"] == f"Learn: {ku}"]
    assert len(learn) == 1, response.json()
    assert [_credit(event) for event in seen] == [Credit("KnowledgeAppliedInTask", learn[0], (ku,))]
    assert await _count(env, ku, "times_applied_in_tasks") == before + 1
    assert await _applies(env, learn[0]) == {ku: False}


# ---------------------------------------------------------------------------
# Vault sync of an Activity file's knowledge field
# ---------------------------------------------------------------------------


async def test_a_first_sync_credits_each_link_it_writes_once(env: Env, tmp_path: Path) -> None:
    one, two = _ku("vault-one"), _ku("vault-two")
    counts = [await _count(env, ku, "times_applied_in_tasks") for ku in (one, two)]
    task = _file(
        tmp_path, "first-sync", "task", "applies_knowledge", [one, _ku("missing"), two, one]
    )

    credits = await _sync(env, tmp_path)

    # The dangling uid writes no edge; the repeated one is one link.
    assert credits == [Credit("KnowledgeBulkAppliedInTask", task, (one, two))]
    assert [await _count(env, ku, "times_applied_in_tasks") for ku in (one, two)] == [
        count + 1 for count in counts
    ]
    assert await _applies(env, task) == {one: False, two: False}


async def test_a_resync_of_the_unchanged_file_and_a_forced_one_credit_nothing(
    env: Env, tmp_path: Path
) -> None:
    ku = _ku("vault-force")
    _file(tmp_path, "unchanged", "task", "applies_knowledge", [ku])
    assert len(await _sync(env, tmp_path)) == 1
    before = await _count(env, ku, "times_applied_in_tasks")

    assert await _sync(env, tmp_path) == []
    assert await _sync(env, tmp_path, force=True) == []
    assert await _count(env, ku, "times_applied_in_tasks") == before


async def test_a_target_added_to_the_file_credits_only_it(env: Env, tmp_path: Path) -> None:
    one, three = _ku("vault-one"), _ku("vault-three")
    task = _file(tmp_path, "added", "task", "applies_knowledge", [one])
    await _sync(env, tmp_path)
    one_before = await _count(env, one, "times_applied_in_tasks")
    three_before = await _count(env, three, "times_applied_in_tasks")

    _file(tmp_path, "added", "task", "applies_knowledge", [one, three])
    credits = await _sync(env, tmp_path)

    assert credits == [Credit("KnowledgeAppliedInTask", task, (three,))]
    assert await _count(env, one, "times_applied_in_tasks") == one_before
    assert await _count(env, three, "times_applied_in_tasks") == three_before + 1


async def test_a_habit_file_and_a_choice_file_credit_their_own_channels(
    env: Env, tmp_path: Path
) -> None:
    habit_ku, choice_ku = _ku("vault-habit"), _ku("vault-choice")
    habit_before = await _count(env, habit_ku, "times_built_into_habits")
    choice_before = await _count(env, choice_ku, "choices_informed_count")
    habit = _file(tmp_path, "vault-habit", "habit", "reinforces_knowledge", [habit_ku])
    choice = _file(
        tmp_path,
        "vault-choice",
        "choice",
        "informed_by_knowledge",
        [choice_ku],
        "description: which way to go",
    )

    credits = await _sync(env, tmp_path)

    assert sorted(credits, key=repr) == sorted(
        [
            Credit("KnowledgeBuiltIntoHabit", habit, (habit_ku,)),
            Credit("KnowledgeInformedChoice", choice, (choice_ku,)),
        ],
        key=repr,
    )
    assert await _count(env, habit_ku, "times_built_into_habits") == habit_before + 1
    assert await _count(env, choice_ku, "choices_informed_count") == choice_before + 1


async def test_a_pair_grounding_inferred_becomes_the_files_link_uncredited(
    env: Env, tmp_path: Path
) -> None:
    named, inferred = _ku("vault-named"), _ku("vault-inferred")
    task = _file(tmp_path, "inferred", "task", "applies_knowledge", [named])
    await _sync(env, tmp_path)
    async with env.driver.session() as session:
        await session.run(
            """
            MATCH (t:Task {uid: $task}), (k:Ku {uid: $ku})
            CREATE (t)-[:APPLIES_KNOWLEDGE {inferred: true, confidence: 0.81,
                                            grounded_at: datetime()}]->(k)
            """,
            task=task,
            ku=inferred,
        )
    assert await _applies(env, task) == {named: False, inferred: True}
    before = await _count(env, inferred, "times_applied_in_tasks")

    _file(tmp_path, "inferred", "task", "applies_knowledge", [named, inferred])
    credits = await _sync(env, tmp_path)

    assert credits == []
    assert await _count(env, inferred, "times_applied_in_tasks") == before
    assert await _applies(env, task) == {named: False, inferred: False}


async def test_an_event_files_link_credits_nothing_until_the_event_is_completed(
    env: Env, tmp_path: Path
) -> None:
    ku = _ku("vault-event")
    practiced = await _count(env, ku, "times_practiced_in_events")
    applied = await _count(env, ku, "times_applied_in_tasks")
    event = _file(tmp_path, "practice", "event", "applies_knowledge", [ku], "status: scheduled")

    assert await _sync(env, tmp_path) == []
    assert await _applies(env, event) == {ku: False}
    assert await _count(env, ku, "times_practiced_in_events") == practiced

    _file(tmp_path, "practice", "event", "applies_knowledge", [ku], "status: completed")
    assert await _sync(env, tmp_path) == []
    assert await _count(env, ku, "times_practiced_in_events") == practiced + 1
    assert await _count(env, ku, "times_applied_in_tasks") == applied
