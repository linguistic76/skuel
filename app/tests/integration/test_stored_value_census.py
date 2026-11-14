"""The stored-value census names every stored value a read would refuse, and only those.

Over the testcontainer: a task whose ``status`` no ``EntityStatus`` names, a Ku whose
``complexity`` no ``KuComplexity`` names, a user whose ``preferences`` blob is not
JSON, and a clean task beside them. The census reads each through the mapper's own
rule, so it names the three — each read through its backend fails the same way —
and not the clean one. Strays are stored by raw Cypher, as a migration, a retired enum
member or an unchecked property patch would leave them.
"""

from __future__ import annotations

import pytest

from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

OWNER = seed_user_uid("zzzstoredvalue")
STRAY_TASK = "task_5f0e1d2c3b4a6978"
CLEAN_TASK = "task_6a7b8c9d0e1f2a3b"
STRAY_KU = "ku.test.stored-value-stray"


def _ours(refusals: list) -> set[tuple[str, object, str]]:
    return {
        (refusal.entity_class, refusal.uid, refusal.field)
        for refusal in refusals
        if refusal.uid in {STRAY_TASK, CLEAN_TASK, STRAY_KU, OWNER}
    }


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
            CREATE (:Entity:Ku {uid: $ku, title: 'Stray', entity_type: 'ku',
                                complexity: 'no-such-complexity'})
            """,
            owner=OWNER,
            stray=STRAY_TASK,
            clean=CLEAN_TASK,
            ku=STRAY_KU,
        )
    try:
        after = await census.read_unreadable()
        assert after.is_ok, after
        assert _ours(after.value) == {
            ("Task", STRAY_TASK, "status"),
            ("Ku", STRAY_KU, "complexity"),
            ("User", OWNER, "preferences"),
        }

        # Each one the census names, its backend's read refuses; the clean one reads.
        assert (await backends["tasks_backend"].get(STRAY_TASK)).is_error
        assert (await backends["ku_backend"].get(STRAY_KU)).is_error
        assert (await backends["users_backend"].get_user_by_uid(OWNER)).is_error
        clean = await backends["tasks_backend"].get(CLEAN_TASK)
        assert clean.is_ok and clean.value is not None

        summary = await census.read_summary(10)
        assert summary.is_ok, summary
        assert summary.value.count == len(after.value)
        assert f"Task {STRAY_TASK}.status" in summary.value.sample
    finally:
        async with neo4j_driver.session() as session:
            await session.run("MATCH (u:User {uid: $owner}) DETACH DELETE u", owner=OWNER)
