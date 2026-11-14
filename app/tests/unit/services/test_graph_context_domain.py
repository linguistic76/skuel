"""A graph-context node's domain names what kind of entity it is, read from its stored
``entity_type`` — never from its label order, and never from the ``domain`` property,
which holds what a piece of content is ABOUT (a subject area, or the model's default).

The mapping is ``EntityType.kind_domain()``; ``determine_domain`` applies it to a node's
properties. The real-traversal half is ``tests/integration/test_graph_context_domain.py``.
"""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from core.models.enums import Domain, EntityType
from core.models.query_types import QueryIntent
from core.models.type_hints import Neo4jProperties
from core.services.infrastructure.graph_record_transformer import (
    build_graph_context_from_domain_context,
    determine_domain,
)

# The ruled mapping: every EntityType names one kind domain.
EXPECTED: dict[EntityType, Domain] = {
    EntityType.KU: Domain.KNOWLEDGE,
    EntityType.PATH_STEP: Domain.LEARNING,
    EntityType.LEARNING_PATH: Domain.LEARNING,
    EntityType.EXERCISE: Domain.LEARNING,
    EntityType.REVISED_EXERCISE: Domain.LEARNING,
    EntityType.TASK: Domain.TASKS,
    EntityType.GOAL: Domain.GOALS,
    EntityType.HABIT: Domain.HABITS,
    EntityType.EVENT: Domain.EVENTS,
    EntityType.CHOICE: Domain.CHOICES,
    EntityType.PRINCIPLE: Domain.PRINCIPLES,
    EntityType.USER_ENTRY: Domain.REPORTS,
    EntityType.ENTRY_REPORT: Domain.REPORTS,
    EntityType.ACTIVITY_REPORT: Domain.REPORTS,
    EntityType.TASK_TEMPLATE: Domain.SYSTEM,
    EntityType.GOAL_TEMPLATE: Domain.SYSTEM,
    EntityType.HABIT_TEMPLATE: Domain.SYSTEM,
    EntityType.EVENT_TEMPLATE: Domain.SYSTEM,
    EntityType.CHOICE_TEMPLATE: Domain.SYSTEM,
    EntityType.PRINCIPLE_TEMPLATE: Domain.SYSTEM,
    EntityType.FORM_TEMPLATE: Domain.SYSTEM,
    EntityType.FORM_SUBMISSION: Domain.SYSTEM,
    EntityType.INTERACTION: Domain.SYSTEM,
    EntityType.LIFE_PATH: Domain.SYSTEM,
    EntityType.RESOURCE: Domain.SYSTEM,
}


def test_the_ruling_covers_every_entity_type() -> None:
    """The enum is the list: a new EntityType fails here until it is given a domain."""
    assert set(EXPECTED) == set(EntityType)


@pytest.mark.parametrize("entity_type", list(EntityType), ids=str)
def test_each_entity_type_names_its_kind_domain(entity_type: EntityType) -> None:
    assert entity_type.kind_domain() is EXPECTED[entity_type]
    assert not entity_type.kind_domain().is_subject_area()


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        # The stored subject area (or the model's "knowledge" default) is not the kind.
        ({"entity_type": "task", "domain": "knowledge"}, Domain.TASKS),
        ({"entity_type": "choice", "domain": "personal"}, Domain.CHOICES),
        ({"entity_type": "path_step", "domain": "spiritual"}, Domain.LEARNING),
        ({"entity_type": "ku"}, Domain.KNOWLEDGE),
        ({"entity_type": "user_entry", "domain": "knowledge"}, Domain.REPORTS),
        # A User node carries no entity_type.
        ({"uid": "user_x", "title": "x"}, Domain.SYSTEM),
    ],
    ids=[
        "task-storing-knowledge",
        "choice-storing-personal",
        "step-storing-spiritual",
        "ku",
        "entry-storing-knowledge",
        "user-node",
    ],
)
def test_determine_domain_reads_entity_type(properties: Neo4jProperties, expected: Domain) -> None:
    assert determine_domain(properties.get("entity_type"), "n0") is expected


def test_an_unknown_entity_type_is_system_and_logged() -> None:
    """A stored value outside the enum is no kind SKUEL knows — said, not guessed."""
    with capture_logs() as logs:
        assert determine_domain("knowledge", "n1") is Domain.SYSTEM
        assert determine_domain(3, "n2") is Domain.SYSTEM
    warnings = [entry["event"] for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 2
    assert "n1" in warnings[0] and "'knowledge'" in warnings[0]
    assert "n2" in warnings[1]


def test_a_node_storing_no_entity_type_logs_nothing() -> None:
    """A User node is system by right, not a defect."""
    with capture_logs() as logs:
        assert determine_domain(None, "user_x") is Domain.SYSTEM
    assert logs == []


def _entry(uid: str, labels: list[str], properties: Neo4jProperties) -> dict[str, object]:
    """One row as the shared producer emits it."""
    return {
        "uid": uid,
        "labels": labels,
        "properties": {"uid": uid, **properties},
        "distance": 1,
        "path_strength": 1.0,
        "incident_rel_type": "RELATED_TO",
        "incident_into_related": True,
    }


def test_the_context_groups_nodes_by_kind_whatever_their_label_order() -> None:
    """Both label orders, a stored subject area, curriculum and the owner's User node:
    each node lands in its own kind, and the summary reports those kinds."""
    rows = [
        _entry("t1", ["Entity", "Task"], {"entity_type": "task", "domain": "knowledge"}),
        _entry("t2", ["Task", "Entity"], {"entity_type": "task", "domain": "knowledge"}),
        _entry("c1", ["Entity", "Choice"], {"entity_type": "choice", "domain": "personal"}),
        _entry("h1", ["Entity", "Habit"], {"entity_type": "habit"}),
        _entry("k1", ["Ku", "Entity"], {"entity_type": "ku"}),
        _entry("s1", ["Entity", "PathStep"], {"entity_type": "path_step", "domain": "personal"}),
        _entry("u1", ["User"], {"title": "owner"}),
    ]

    context = build_graph_context_from_domain_context(
        rows, "origin", Domain.TASKS, QueryIntent.RELATIONSHIP, 1
    )

    by_uid = {node.uid: node.domain for node in context.all_nodes}
    assert by_uid == {
        "t1": Domain.TASKS,
        "t2": Domain.TASKS,
        "c1": Domain.CHOICES,
        "h1": Domain.HABITS,
        "k1": Domain.KNOWLEDGE,
        "s1": Domain.LEARNING,
        "u1": Domain.SYSTEM,
    }
    assert sorted(context.get_summary()["domains"]) == sorted(
        ["tasks", "choices", "habits", "knowledge", "learning", "system"]
    )
    assert [n.uid for n in context.get_nodes_by_domain(Domain.TASKS)] == ["t1", "t2"]
    # The subject area is still on the node, where a reader of the subject finds it.
    assert context.get_nodes_by_domain(Domain.CHOICES)[0].properties["domain"] == "personal"
