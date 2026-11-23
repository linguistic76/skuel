"""The stored-value census names every field a read would refuse, and only those.

Over the testcontainer: a task whose ``status`` no ``EntityStatus`` names, a Ku whose
``complexity`` no ``KuComplexity`` names, a user whose ``preferences`` blob is not
JSON, a task holding no ``title`` (which a Task requires), and a clean task beside
them. The census reads each through the mapper's own rule, so it names the four —
each read through its backend fails the same way — and not the clean one. Strays are stored by raw Cypher, as a migration, a retired enum
member or an unchecked property patch would leave them.

The same read names each stored key no read reads — neither a field nor registered
node state of the node's class — and no key that is either.
"""

from __future__ import annotations

import pytest

from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = seed_user_uid("zzzstoredvalue")
STRAY_TASK = "task_5f0e1d2c3b4a6978"
CLEAN_TASK = "task_6a7b8c9d0e1f2a3b"
UNTITLED_TASK = "task_7c8d9e0f1a2b3c4d"
STRAY_KU = "ku.test.stored-value-stray"
KEYED_TASK = "task_8d9e0f1a2b3c4d5e"
KEYED_KU = "ku.test.stored-key-stray"
KEYED_USER = seed_user_uid("zzzstoredkey")


def _ours(refusals: list) -> set[tuple[str, object, str]]:
    return {
        (refusal.entity_class, refusal.uid, refusal.field)
        for refusal in refusals
        if refusal.uid in {STRAY_TASK, CLEAN_TASK, UNTITLED_TASK, STRAY_KU, OWNER}
    }


@pytest.mark.stores_unreadable_value("the strays the census names")
async def test_the_census_names_each_unreadable_value_and_nothing_else(
    clean_neo4j, neo4j_driver
) -> None:
    backends = build_production_backends(neo4j_driver)
    census = backends["stored_value_census_backend"]

    before = await census.read_unreadable()
    assert before.is_ok, before
    assert _ours(before.value) == set()

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $owner}) SET u.title = $owner, u.preferences = '{not json'
            CREATE (:Entity:Task {uid: $stray, title: 'Stray', entity_type: 'task',
                                  user_uid: $owner, status: 'no-such-status'})
            CREATE (:Entity:Task {uid: $clean, title: 'Clean', entity_type: 'task',
                                  user_uid: $owner, status: 'active'})
            CREATE (:Entity:Task {uid: $untitled, entity_type: 'task', user_uid: $owner,
                                  status: 'active'})
            CREATE (:Entity:Ku {uid: $ku, title: 'Stray', entity_type: 'ku',
                                complexity: 'no-such-complexity'})
            """,
            owner=OWNER,
            stray=STRAY_TASK,
            clean=CLEAN_TASK,
            untitled=UNTITLED_TASK,
            ku=STRAY_KU,
        )
    try:
        after = await census.read_unreadable()
        assert after.is_ok, after
        assert _ours(after.value) == {
            ("Task", STRAY_TASK, "status"),
            ("Task", UNTITLED_TASK, "title"),
            ("Ku", STRAY_KU, "complexity"),
            ("User", OWNER, "preferences"),
        }

        # Each one the census names, its backend's read refuses; the clean one reads.
        assert (await backends["tasks_backend"].get(STRAY_TASK)).is_error
        assert (await backends["tasks_backend"].get(UNTITLED_TASK)).is_error
        assert (await backends["ku_backend"].get(STRAY_KU)).is_error
        assert (await backends["users_backend"].get_user_by_uid(OWNER)).is_error
        clean = await backends["tasks_backend"].get(CLEAN_TASK)
        assert clean.is_ok and clean.value is not None

        summary = await census.read_summary(10)
        assert summary.is_ok, summary
        assert summary.value.unreadable.count == len(after.value)
        assert f"Task {STRAY_TASK}.status" in summary.value.unreadable.sample
    finally:
        async with neo4j_driver.session() as session:
            await session.run("MATCH (u:User {uid: $owner}) DETACH DELETE u", owner=OWNER)


def _our_keys(found: list) -> set[tuple[str, object, str]]:
    return {
        (key.entity_class, key.uid, key.key)
        for key in found
        if key.uid in {KEYED_TASK, KEYED_KU, KEYED_USER}
    }


async def test_the_census_names_each_key_no_read_reads_and_no_registered_one(
    clean_neo4j, neo4j_driver
) -> None:
    census = build_production_backends(neo4j_driver)["stored_value_census_backend"]

    before = await census.read_undeclared()
    assert before.is_ok, before
    assert _our_keys(before.value) == set()

    # Each node holds fields, registered node state, and one key that is neither.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $user}) SET u.title = $user, u.task_duration_ratio = 1.2,
                                            u.recently_viewed_knowledge = [$ku]
            CREATE (:Entity:Task {uid: $task, title: 'Keyed', entity_type: 'task',
                                  user_uid: $user, status: 'active', titel: 'typo',
                                  grounded_at: datetime(), embedding_text_hash: 'h',
                                  predicted_duration_minutes: 30})
            CREATE (:Entity:Ku {uid: $ku, title: 'Keyed', entity_type: 'ku',
                                times_applied_in_tasks: 2, hub_score: 4, heading: 'h'})
            """,
            user=KEYED_USER,
            task=KEYED_TASK,
            ku=KEYED_KU,
        )
    try:
        after = await census.read_undeclared()
        assert after.is_ok, after
        assert _our_keys(after.value) == {
            ("Task", KEYED_TASK, "titel"),
            ("Ku", KEYED_KU, "heading"),
            ("User", KEYED_USER, "recently_viewed_knowledge"),
        }

        summary = await census.read_summary(100)
        assert summary.is_ok, summary
        assert summary.value.undeclared.count == len(after.value)
        assert f"Task {KEYED_TASK}.titel" in summary.value.undeclared.sample
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.uid IN [$task, $ku] DETACH DELETE n",
                task=KEYED_TASK,
                ku=KEYED_KU,
            )
            await session.run("MATCH (u:User {uid: $user}) DETACH DELETE u", user=KEYED_USER)
