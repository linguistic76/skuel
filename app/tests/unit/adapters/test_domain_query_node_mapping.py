"""Node maps become models through the mapper, never a constructor splat.

`RevisedExerciseBackend.list_for_student` / `get_by_report_uid`,
`GroupBackend.get_user_groups` and `ExerciseService.list_user_exercises` each
once rebuilt the model by splatting the node into the constructor. That splat
rejects any property the dataclass does not declare — and
`EmbeddingsBackend.store_embedding_metadata` writes two of them
(`embedding_version`, `embedding_text_hash`), so an embedded entity raised
TypeError, was swallowed as a "malformed row" warning, and vanished from its own
listing (the teacher's exercise list showed no embedded exercise at all).

These pin the mapper's half of the fix: `from_neo4j_node`, the mapper `get()`
uses, ignores undeclared properties. The negative control is the splat itself —
it must still fail on the same input, or these tests would pass for the wrong
reason. The list reads' own pins are
`tests/unit/test_exercise_service_list_user_exercises.py` and the dashboard case
in `tests/integration/routes/test_exercise_authoring_scope_ownership.py`.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.group.group import Group

_EMBEDDING_BOOKKEEPING = {
    "embedding_version": 3,
    "embedding_text_hash": "0f2b" * 16,
}


def _revised_exercise_node() -> dict[str, object]:
    return {
        "uid": "re_abc123",
        "title": "Revision 1",
        "entity_type": "revised_exercise",
        "user_uid": "user_teacher_01",
        "instructions": "Try the second paragraph again.",
        **_EMBEDDING_BOOKKEEPING,
    }


def _exercise_node() -> dict[str, object]:
    return {
        "uid": "ex_abc123",
        "title": "Arc exercise",
        "entity_type": "exercise",
        "owner_uid": "user_teacher_01",
        "scope": "assigned",
        "instructions": "Write one paragraph.",
        **_EMBEDDING_BOOKKEEPING,
    }


def _group_node() -> dict[str, object]:
    return {
        "uid": "group_physics-101_abc",
        "name": "Physics 101",
        "owner_uid": "user_teacher_01",
        **_EMBEDDING_BOOKKEEPING,
    }


@pytest.mark.parametrize(
    ("node", "model"),
    [
        (_revised_exercise_node(), RevisedExercise),
        (_exercise_node(), Exercise),
        (_group_node(), Group),
    ],
    ids=["revised_exercise", "exercise", "group"],
)
def test_mapper_keeps_a_node_carrying_embedding_bookkeeping(
    node: dict[str, object], model: type[RevisedExercise] | type[Exercise] | type[Group]
) -> None:
    entity: RevisedExercise | Exercise | Group = from_neo4j_node(node, model)

    assert entity.uid == node["uid"]


def test_mapped_exercise_carries_its_scope_as_the_enum() -> None:
    exercise = from_neo4j_node(_exercise_node(), Exercise)

    assert exercise.scope is ExerciseScope.ASSIGNED


@pytest.mark.parametrize(
    ("node", "model"),
    [
        (_revised_exercise_node(), RevisedExercise),
        (_exercise_node(), Exercise),
        (_group_node(), Group),
    ],
    ids=["revised_exercise", "exercise", "group"],
)
def test_constructor_splat_still_rejects_the_same_node(
    node: dict[str, object], model: type[RevisedExercise] | type[Exercise] | type[Group]
) -> None:
    # Negative control: without this the test above would pass even if the
    # adapters regressed to splatting, because nothing would have been broken.
    with pytest.raises(TypeError, match="embedding_"):
        model(**node)
