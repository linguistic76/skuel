"""
The turn-in writer stamps the version and titles an untitled turn-in (Submit & Share arc PR 7).

``create_with_exercise_link`` writes the ``FULFILLS_EXERCISE {revision}`` edge and,
in the same statement, the snapshot ``turn_in_revision`` beside the exercise
snapshot. A turn-in handed in with an empty title is titled "<root title> v<N>";
a title the student typed is kept verbatim. A revision target names the ROOT
exercise in both the snapshot and the default title.
"""

from datetime import datetime

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry

_STUDENT = "user_writer_student"
_ROOT = "ex.writer.root"
_REVISION = "re_writer_revision"


@pytest.fixture
async def root_and_revision(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (student:User {uid: $student})
            CREATE (root:Entity:Exercise {uid: $root, entity_type: 'exercise', title: 'Root'})
            CREATE (re:Entity:RevisedExercise {uid: $revision, entity_type: 'revised_exercise',
                                               title: 'Revision 1', student_uid: $student,
                                               original_exercise_uid: $root})
            CREATE (re)-[:REVISES_EXERCISE]->(root)
            RETURN count(root) AS seeded
            """,
            student=_STUDENT,
            root=_ROOT,
            revision=_REVISION,
        )
        seeded = await result.single()
        assert seeded is not None and seeded["seeded"] == 1


def _entry(uid: str, title: str) -> UserEntry:
    now = datetime.now()
    return UserEntry(
        uid=uid,
        title=title,
        entity_type=EntityType.USER_ENTRY,
        user_uid=_STUDENT,
        created_by=_STUDENT,
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


@pytest.mark.asyncio
async def test_an_untitled_turn_in_is_titled_from_the_root_and_the_version_is_stamped(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.create_with_exercise_link(_entry("ue_writer_1", ""), _ROOT, revision=1)

    assert result.is_ok, result.error
    assert result.value.title == "Root v1"
    assert result.value.turn_in_revision == 1
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

    result = await backend.create_with_exercise_link(
        _entry("ue_writer_2", "My own words"), _ROOT, revision=2
    )

    assert result.is_ok, result.error
    assert result.value.title == "My own words"
    assert result.value.turn_in_revision == 2
    stored = await _stored(neo4j_driver, "ue_writer_2")
    assert stored["title"] == "My own words"
    assert stored["turn_in_revision"] == 2


@pytest.mark.asyncio
async def test_a_revision_target_defaults_the_title_from_the_root(
    neo4j_driver: AsyncDriver, root_and_revision: None
) -> None:
    """A revision is titled "Revision N"; the default names the root the snapshot holds."""
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.create_with_exercise_link(
        _entry("ue_writer_3", ""), _REVISION, revision=3
    )

    assert result.is_ok, result.error
    assert result.value.title == "Root v3"
    stored = await _stored(neo4j_driver, "ue_writer_3")
    assert stored["root_uid"] == _ROOT
    assert stored["root_title"] == "Root"
    assert stored["turn_in_revision"] == 3
    assert stored["edge_target"] == _ROOT
