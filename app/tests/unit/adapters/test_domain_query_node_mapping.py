"""Domain list queries must map nodes the way by-UID reads do.

`RevisedExerciseBackend.list_for_student` / `get_by_report_uid` and
`GroupBackend.get_user_groups` used to hand raw records to their service, which
rebuilt the model by splatting the node into the constructor. That splat rejects
any property the dataclass does not declare — and `store_entity_embedding`
writes three of them (`embedding_version`, `embedding_text_hash`,
`embedding_source_text`), so an embedded entity raised TypeError, was swallowed
as a "malformed row" warning, and vanished from its own listing.

These pin the fix at the layer that owns it: the adapter maps through
`from_neo4j_node`, the same mapper `get()` uses, which ignores undeclared
properties. The negative control is the splat itself — it must still fail on the
same input, or these tests would pass for the wrong reason.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.group.group import Group

_EMBEDDING_BOOKKEEPING = {
    "embedding_version": 3,
    "embedding_text_hash": "0f2b" * 16,
    "embedding_source_text": None,
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
        (_group_node(), Group),
    ],
    ids=["revised_exercise", "group"],
)
def test_mapper_keeps_a_node_carrying_embedding_bookkeeping(
    node: dict[str, object], model: type[RevisedExercise] | type[Group]
) -> None:
    entity: RevisedExercise | Group = from_neo4j_node(node, model)

    assert entity.uid == node["uid"]


@pytest.mark.parametrize(
    ("node", "model"),
    [
        (_revised_exercise_node(), RevisedExercise),
        (_group_node(), Group),
    ],
    ids=["revised_exercise", "group"],
)
def test_constructor_splat_still_rejects_the_same_node(
    node: dict[str, object], model: type[RevisedExercise] | type[Group]
) -> None:
    # Negative control: without this the test above would pass even if the
    # adapters regressed to splatting, because nothing would have been broken.
    with pytest.raises(TypeError, match="embedding_"):
        model(**node)
