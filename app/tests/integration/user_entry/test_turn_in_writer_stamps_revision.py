"""
The turn-in writer mints the version, stamps it, and titles an untitled turn-in.

``create_with_exercise_link`` writes the entry, its ``FULFILLS_EXERCISE {revision}``
edge and the snapshot ``turn_in_revision`` in one statement, and decides the
revision in it: one more than the highest the owner's entries on that root exercise
already carry. A turn-in handed in with an empty title is titled "<root title> v<N>";
a title the student typed is kept verbatim. A revision target names the ROOT
exercise in both the snapshot and the default title, and counts on the root's
sequence.
"""

import asyncio
from datetime import datetime

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.utils.result_simplified import ErrorCategory

_STUDENT = "user_writer_student"
_OTHER_STUDENT = "user_writer_other_student"
_ROOT = "ex.writer.root"
_REVISION = "re_writer_revision"


@pytest.fixture
async def root_and_revision(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (student:User {uid: $student})
            MERGE (other:User {uid: $other})
            CREATE (root:Entity:Exercise {uid: $root, entity_type: 'exercise', title: 'Root'})
            CREATE (re:Entity:RevisedExercise {uid: $revision, entity_type: 'revised_exercise',
                                               title: 'Revision 1', student_uid: $student,
                                               original_exercise_uid: $root})
            CREATE (re)-[:REVISES_EXERCISE]->(root)
            RETURN count(root) AS seeded
            """,
            student=_STUDENT,
            other=_OTHER_STUDENT,
            root=_ROOT,
            revision=_REVISION,
        )
        seeded = await result.single()
        assert seeded is not None and seeded["seeded"] == 1


def _entry(uid: str, title: str, owner: str = _STUDENT) -> UserEntry:
    now = datetime.now()
    return UserEntry(
        uid=uid,
        title=title,
        entity_type=EntityType.USER_ENTRY,
        user_uid=owner,
        created_by=owner,
        pipeline=Pipeline.TEACHER_REVIEW,
        created_at=now,
        updated_at=now,
    )


async def _stored(driver: AsyncDriver, uid: str) -> dict:
    async with driver.session() as session:
        row = await (
            await session.run(
                """
                MATCH (e:Entity {uid: $uid})
                OPTIONAL MATCH (e)-[r:FULFILLS_EXERCISE]->(ex:Entity:Exercise)
                RETURN e.title AS title, e.turn_in_revision AS turn_in_revision,
                       e.turn_in_exercise_uid AS root_uid, e.turn_in_exercise_title AS root_title,
                       r.revision AS edge_revision, ex.uid AS edge_target,
                       e.revision_number AS stray_revision_number
                """,
                uid=uid,
            )
        ).single()
    assert row is not None
    return dict(row)


async def _exists(driver: AsyncDriver, uid: str) -> bool:
    async with driver.session() as session:
        row = await (
            await session.run("MATCH (e:Entity {uid: $uid}) RETURN count(e) AS found", uid=uid)
        ).single()
    return row is not None and row["found"] == 1


@pytest.mark.asyncio
async def test_an_untitled_turn_in_is_titled_from_the_root_and_the_version_is_stamped(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.create_with_exercise_link(_entry("ue_writer_1", ""), _ROOT)

    assert result.is_ok, result.error
    assert result.value.title == "Root v1"
    assert result.value.turn_in_revision == 1
    assert result.value.turn_in_exercise_uid == _ROOT
    assert result.value.turn_in_exercise_title == "Root"
    stored = await _stored(neo4j_driver, "ue_writer_1")
    assert stored["title"] == "Root v1"
    assert stored["turn_in_revision"] == 1
    assert stored["edge_revision"] == 1
    assert stored["stray_revision_number"] is None


@pytest.mark.asyncio
async def test_the_students_title_is_kept_verbatim(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    backend = UserEntryBackend(neo4j_driver)
    first = await backend.create_with_exercise_link(_entry("ue_writer_first", ""), _ROOT)
    assert first.is_ok, first.error

    result = await backend.create_with_exercise_link(_entry("ue_writer_2", "My own words"), _ROOT)

    assert result.is_ok, result.error
    assert result.value.title == "My own words"
    assert result.value.turn_in_revision == 2
    stored = await _stored(neo4j_driver, "ue_writer_2")
    assert stored["title"] == "My own words"
    assert stored["turn_in_revision"] == 2
    assert stored["edge_revision"] == 2


@pytest.mark.asyncio
async def test_a_revision_target_counts_on_the_root_and_is_titled_from_it(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """A revision is titled "Revision N"; the default names the root the snapshot holds."""
    backend = UserEntryBackend(neo4j_driver)
    first = await backend.create_with_exercise_link(_entry("ue_writer_first", ""), _ROOT)
    assert first.is_ok, first.error

    result = await backend.create_with_exercise_link(_entry("ue_writer_3", ""), _REVISION)

    assert result.is_ok, result.error
    assert result.value.title == "Root v2"
    stored = await _stored(neo4j_driver, "ue_writer_3")
    assert stored["root_uid"] == _ROOT
    assert stored["root_title"] == "Root"
    assert stored["turn_in_revision"] == 2
    assert stored["edge_revision"] == 2
    assert stored["edge_target"] == _ROOT


@pytest.mark.asyncio
async def test_each_owner_has_their_own_sequence_on_an_exercise(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    backend = UserEntryBackend(neo4j_driver)

    mine_1 = await backend.create_with_exercise_link(_entry("ue_mine_1", ""), _ROOT)
    mine_2 = await backend.create_with_exercise_link(_entry("ue_mine_2", ""), _ROOT)
    theirs = await backend.create_with_exercise_link(
        _entry("ue_theirs_1", "", owner=_OTHER_STUDENT), _ROOT
    )

    assert mine_1.is_ok and mine_2.is_ok and theirs.is_ok
    assert [mine_1.value.turn_in_revision, mine_2.value.turn_in_revision] == [1, 2]
    assert theirs.value.turn_in_revision == 1


@pytest.mark.asyncio
async def test_a_deleted_turn_in_does_not_hand_its_number_to_a_later_one(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """v1, v2, delete v1: the next is v3 — a living entry holds v2."""
    backend = UserEntryBackend(neo4j_driver)
    for uid in ("ue_gap_1", "ue_gap_2"):
        created = await backend.create_with_exercise_link(_entry(uid, ""), _ROOT)
        assert created.is_ok, created.error
    deleted = await backend.delete("ue_gap_1", cascade=True)
    assert deleted.is_ok, deleted.error

    result = await backend.create_with_exercise_link(_entry("ue_gap_3", ""), _ROOT)

    assert result.is_ok, result.error
    assert result.value.turn_in_revision == 3
    assert result.value.title == "Root v3"
    assert (await _stored(neo4j_driver, "ue_gap_2"))["edge_revision"] == 2
    assert (await _stored(neo4j_driver, "ue_gap_3"))["edge_revision"] == 3


@pytest.mark.asyncio
async def test_an_edge_without_a_revision_counts_by_its_snapshot(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """A prior entry whose edge carries no ``revision`` is read by its ``turn_in_revision``."""
    backend = UserEntryBackend(neo4j_driver)
    prior = await backend.create_with_exercise_link(_entry("ue_legacy", ""), _ROOT)
    assert prior.is_ok, prior.error
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Entity {uid: 'ue_legacy'})-[r:FULFILLS_EXERCISE]->()
            REMOVE r.revision
            SET e.turn_in_revision = 4
            """
        )

    result = await backend.create_with_exercise_link(_entry("ue_after_legacy", ""), _ROOT)

    assert result.is_ok, result.error
    assert result.value.turn_in_revision == 5


@pytest.mark.asyncio
async def test_concurrent_turn_ins_of_one_pair_take_distinct_revisions(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """The write decides the number: six at once are 1..6, none shared."""
    backend = UserEntryBackend(neo4j_driver)

    results = await asyncio.gather(
        *(backend.create_with_exercise_link(_entry(f"ue_race_{i}", ""), _ROOT) for i in range(6))
    )

    assert all(result.is_ok for result in results), [r.error for r in results if r.is_error]
    assert sorted(result.value.turn_in_revision for result in results) == [1, 2, 3, 4, 5, 6]
    stored = [await _stored(neo4j_driver, f"ue_race_{i}") for i in range(6)]
    assert sorted(row["edge_revision"] for row in stored) == [1, 2, 3, 4, 5, 6]
    assert all(row["edge_revision"] == row["turn_in_revision"] for row in stored)
    # The lock's sentinel never outlives its statement.
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (root:Entity {uid: $root}) RETURN root.`_turn_in_lock` AS sentinel",
                root=_ROOT,
            )
        ).single()
    assert row is not None and row["sentinel"] is None


@pytest.mark.asyncio
async def test_a_target_that_is_not_an_exercise_is_not_found_and_nothing_is_written(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.create_with_exercise_link(_entry("ue_orphan", "Mine"), "ex.writer.gone")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    assert not await _exists(neo4j_driver, "ue_orphan")


@pytest.mark.asyncio
async def test_an_owner_who_does_not_exist_writes_nothing(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """The refusal is the create's own (no such owner), not a missing exercise."""
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.create_with_exercise_link(
        _entry("ue_ownerless", "Mine", owner="user_writer_nobody"), _ROOT
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE
    assert not await _exists(neo4j_driver, "ue_ownerless")
