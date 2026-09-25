"""
The linker retitles a turn-in from its root-exercise snapshot on a real backend.

A revision target is titled "Revision N"; the retitle names the root exercise
the entry's ``turn_in_exercise_title`` holds, and the revision number is the
count of the student's turn-ins on that root.
"""

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.services.user_entry.exercise_linker import ProcessingOutcome, UserEntryExerciseLinker

_STUDENT = "user_linker_student"
_ROOT = "ex.linker.root"
_REVISION = "re_linker_revision"
_ENTRY = "ue_linker_answer"


@pytest.fixture
async def revision_turn_in(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """A student's turn-in against a revision, in the writer's shape."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (student:User {uid: $student})
            CREATE (root:Entity:Exercise {uid: $root, entity_type: 'exercise', title: 'Root'})
            CREATE (re:Entity:RevisedExercise {uid: $revision, entity_type: 'revised_exercise',
                                               title: 'Revision 1', student_uid: $student,
                                               original_exercise_uid: $root})
            CREATE (re)-[:REVISES_EXERCISE]->(root)
            CREATE (entry:Entity:UserEntry {uid: $entry, entity_type: 'user_entry', user_uid: $student,
                                            title: 'My own words', turn_in_exercise_uid: $root,
                                            turn_in_exercise_title: 'Root'})
            CREATE (student)-[:OWNS]->(entry)
            CREATE (entry)-[:FULFILLS_EXERCISE {revision: 1}]->(root)
            CREATE (entry)-[:FULFILLS_REVISED_EXERCISE {revision: 1}]->(re)
            RETURN count(entry) AS seeded
            """,
            student=_STUDENT,
            root=_ROOT,
            revision=_REVISION,
            entry=_ENTRY,
        )
        seeded = await result.single()
        assert seeded is not None and seeded["seeded"] == 1, "the turn-in fixture did not land"


@pytest.mark.asyncio
async def test_revision_turn_in_is_retitled_from_the_root_snapshot(
    neo4j_driver: AsyncDriver, revision_turn_in: None
) -> None:
    linker = UserEntryExerciseLinker(UserEntryBackend(neo4j_driver))

    result = await linker.process_exercise_submission(_ENTRY, _REVISION)

    assert result.is_ok, result.error
    assert result.value == ProcessingOutcome.PROCESSED
    async with neo4j_driver.session() as session:
        row = await (
            await session.run(
                "MATCH (e:Entity {uid: $uid}) RETURN e.title AS title, e.revision_number AS revision",
                uid=_ENTRY,
            )
        ).single()
    assert row is not None
    assert row["title"] == "Root v1"
    assert row["revision"] == 1
