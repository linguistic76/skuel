"""
A revision's search enrichment collects the turn-ins that answer it.

``RevisedExerciseService`` enriches faceted-search hits with their incoming
turn-ins. A turn-in against a revision reaches it by
``FULFILLS_REVISED_EXERCISE`` (its ``FULFILLS_EXERCISE`` anchors on the root
exercise), and one filed after the original was deleted reaches it by
``FULFILLS_EXERCISE`` alone; the enrichment pattern is a union of the two, so
both kinds land in ``_graph_context["submissions"]``.
"""

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.exercise_backends import RevisedExerciseBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.search_request import SearchRequest
from core.models.type_hints import UserUID
from core.services.revised_exercises.revised_exercise_service import RevisedExerciseService

_TEACHER_UID = UserUID("user_test")
_STUDENT_UID = "user_other"
_REVISION_UID = "rex.lineage.revision"
_ROOT_UID = "ex.lineage.root"
_ANSWER_UID = "ue.lineage.answer"
_ORPHAN_ANSWER_UID = "ue.lineage.orphan-answer"


@pytest.fixture
async def answered_revision(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """A teacher-owned revision answered once by each edge kind."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (teacher:User {uid: $teacher_uid})
            CREATE (root:Entity:Exercise {uid: $root_uid, entity_type: 'exercise', title: 'Root'})
            CREATE (re:Entity:RevisedExercise {uid: $revision_uid, entity_type: 'revised_exercise',
                                               title: 'Lineage revision', user_uid: $teacher_uid,
                                               student_uid: $student_uid, created_at: '2026-09-25'})
            CREATE (teacher)-[:OWNS]->(re)
            CREATE (re)-[:REVISES_EXERCISE]->(root)
            CREATE (answer:Entity:UserEntry {uid: $answer_uid, entity_type: 'user_entry',
                                             title: 'Answer', user_uid: $student_uid})
            CREATE (answer)-[:FULFILLS_EXERCISE {revision: 2}]->(root)
            CREATE (answer)-[:FULFILLS_REVISED_EXERCISE {revision: 2}]->(re)
            CREATE (orphan:Entity:UserEntry {uid: $orphan_answer_uid, entity_type: 'user_entry',
                                             title: 'Orphan answer', user_uid: $student_uid})
            CREATE (orphan)-[:FULFILLS_EXERCISE {revision: 3}]->(re)
            """,
            teacher_uid=_TEACHER_UID,
            student_uid=_STUDENT_UID,
            root_uid=_ROOT_UID,
            revision_uid=_REVISION_UID,
            answer_uid=_ANSWER_UID,
            orphan_answer_uid=_ORPHAN_ANSWER_UID,
        )


@pytest.fixture
def revised_service(neo4j_driver: AsyncDriver) -> RevisedExerciseService:
    backend = RevisedExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.REVISED_EXERCISE,
        entity_class=RevisedExercise,
        base_label=NeoLabel.ENTITY,
    )
    return RevisedExerciseService(backend=backend)


@pytest.mark.asyncio
async def test_faceted_search_collects_turn_ins_by_either_edge(
    revised_service: RevisedExerciseService, answered_revision: None
) -> None:
    request = SearchRequest(query_text="Lineage")

    result = await revised_service.graph_aware_faceted_search(request, _TEACHER_UID)

    assert result.is_ok, result.error
    hits = {hit["uid"]: hit for hit in result.value}
    assert set(hits) == {_REVISION_UID}
    submissions = hits[_REVISION_UID]["_graph_context"]["submissions"]
    assert {item["submissions_uid"] for item in submissions} == {_ANSWER_UID, _ORPHAN_ANSWER_UID}
    assert hits[_REVISION_UID]["_graph_context"]["submissions_count"] == 2
