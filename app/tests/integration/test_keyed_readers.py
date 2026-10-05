"""Real-Neo4j reads through the keyed readers: a view returns its kind, its tier, its owner's.

A keyed reader on ``UnifiedRelationshipService`` names a registry definition by key.
The definition decides the far end's kind (``target_label``) and the tier
(``filter_property``), and the backend reads those into its statement
(``resolve_keyed_read``, Activity links arc PR 1c). The unit invariant
(``tests/unit/test_activity_link_invariant.py``) shows both reach the backend call; this
file shows the statement applies them, through each of the three readers, against the
real graph.

The views are built on an edge type no config declares (``undeclared_edge``), so no later
PR that changes a registry definition can move these controls. The anchor is a goal read
through the Goal backend, as the goals facade reads it, so the far-node wall applies: a
habit another user owns, linked to the goal, is withheld from the readers that name far
ends (``get_related_uids``, ``batch_get_related_uids``) and counted by the one that does
arithmetic (``has_relationship``).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend
from adapters.persistence.neo4j.query.cypher.crud_queries import build_link_far_node_clause
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal import Goal
from core.models.relationship_registry import GOALS_CONFIG, UnifiedRelationshipDefinition
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from tests.helpers.activity_links import undeclared_edge

EDGE = undeclared_edge()

P = "keyed_"
OWNER = "user_" + P + "owner"
STRANGER = "user_" + P + "stranger"

GOAL = P + "goal"  # linked from a habit of each tier, a task and a stranger's habit
GOAL_HABIT_ONLY = P + "goal_habit_only"  # linked from one optional-tier habit

HABIT_ESSENTIAL = P + "habit_essential"
HABIT_UNTIERED = P + "habit_untiered"
TASK_OPTIONAL = P + "task_optional"
HABIT_OPTIONAL = P + "habit_optional"
STRANGERS_HABIT = P + "strangers_habit"


def _view(
    method_key: str, far_end: NeoLabel, tier: str | None = None
) -> UnifiedRelationshipDefinition:
    return UnifiedRelationshipDefinition(
        relationship=EDGE,
        target_label=far_end,
        direction="incoming",
        context_field_name=method_key,
        method_key=method_key,
        filter_property="tier" if tier else None,
        filter_value=tier,
    )


VIEWS = (
    _view("habits", NeoLabel.HABIT),
    _view("tasks", NeoLabel.TASK),
    _view("essential", NeoLabel.ENTITY, tier="essential"),
    _view("everything", NeoLabel.ENTITY),
)


@pytest.fixture
def goal_relationships(neo4j_driver) -> UnifiedRelationshipService[Any, Any, Any]:
    backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
    config = dataclasses.replace(GOALS_CONFIG, relationships=VIEWS)
    return UnifiedRelationshipService[Any, Any, Any](
        backend=backend, config=config, graph_intel=None
    )


@pytest.fixture
async def linked_goals(neo4j_driver, clean_neo4j) -> None:
    """Two goals of OWNER's, each linked over EDGE from the nodes its constant names."""
    nodes = [
        ("Goal", GOAL, OWNER),
        ("Goal", GOAL_HABIT_ONLY, OWNER),
        ("Habit", HABIT_ESSENTIAL, OWNER),
        ("Habit", HABIT_UNTIERED, OWNER),
        ("Task", TASK_OPTIONAL, OWNER),
        ("Habit", HABIT_OPTIONAL, OWNER),
        ("Habit", STRANGERS_HABIT, STRANGER),
    ]
    edges = [
        (HABIT_ESSENTIAL, GOAL, "essential"),
        (HABIT_UNTIERED, GOAL, None),
        (TASK_OPTIONAL, GOAL, "optional"),
        (STRANGERS_HABIT, GOAL, "essential"),
        (HABIT_OPTIONAL, GOAL_HABIT_ONLY, "optional"),
    ]
    async with neo4j_driver.session() as session:
        for label, uid, owner in nodes:
            await session.run(
                f"CREATE (:Entity:{label} {{uid: $uid, entity_type: $kind, title: $uid, "
                "user_uid: $owner, status: 'active'})",
                uid=uid,
                kind=label.lower(),
                owner=owner,
            )
        for source, goal, tier in edges:
            await session.run(
                f"MATCH (s:Entity {{uid: $source}}), (g:Goal {{uid: $goal}}) "
                f"CREATE (s)-[r:{EDGE}]->(g) SET r.tier = $tier",
                source=source,
                goal=goal,
                tier=tier,
            )


def test_the_edge_is_walled_under_a_goal():
    """Precondition: the wall applies to EDGE, so the stranger's habit is a real control."""
    assert build_link_far_node_clause(NeoLabel.GOAL, "related", "owners", EDGE) is not None


# (key, what GOAL's view holds, what GOAL_HABIT_ONLY's holds)
EXPECTED = [
    ("habits", {HABIT_ESSENTIAL, HABIT_UNTIERED}, {HABIT_OPTIONAL}),
    ("tasks", {TASK_OPTIONAL}, set()),
    ("essential", {HABIT_ESSENTIAL}, set()),
    ("everything", {HABIT_ESSENTIAL, HABIT_UNTIERED, TASK_OPTIONAL}, {HABIT_OPTIONAL}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "on_goal", "on_habit_only_goal"), EXPECTED)
async def test_get_related_uids_returns_its_kind_its_tier_and_its_owners(
    goal_relationships, linked_goals, key, on_goal, on_habit_only_goal
):
    for goal, expected in ((GOAL, on_goal), (GOAL_HABIT_ONLY, on_habit_only_goal)):
        result = await goal_relationships.get_related_uids(key, goal)

        assert result.is_ok, result
        assert set(result.value) == expected, (key, goal)


@pytest.mark.asyncio
@pytest.mark.parametrize(("key", "on_goal", "on_habit_only_goal"), EXPECTED)
async def test_batch_get_related_uids_returns_its_kind_its_tier_and_its_owners(
    goal_relationships, linked_goals, key, on_goal, on_habit_only_goal
):
    result = await goal_relationships.batch_get_related_uids(key, [GOAL, GOAL_HABIT_ONLY])

    assert result.is_ok, result
    assert {uid: set(related) for uid, related in result.value.items()} == {
        GOAL: on_goal,
        GOAL_HABIT_ONLY: on_habit_only_goal,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "goal", "expected"),
    [
        ("habits", GOAL_HABIT_ONLY, True),
        ("tasks", GOAL_HABIT_ONLY, False),
        ("tasks", GOAL, True),
        ("essential", GOAL, True),
        ("essential", GOAL_HABIT_ONLY, False),
        ("everything", GOAL_HABIT_ONLY, True),
    ],
)
async def test_has_relationship_asks_of_its_kind_and_its_tier(
    goal_relationships, linked_goals, key, goal, expected
):
    result = await goal_relationships.has_relationship(key, goal)

    assert result.is_ok, result
    assert result.value is expected


@pytest.mark.asyncio
async def test_has_relationship_counts_the_edges_the_wall_withholds(
    neo4j_driver, goal_relationships, clean_neo4j
):
    """Arithmetic sees every edge: a goal linked only from a stranger's habit has one."""
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity:Goal {uid: $goal, entity_type: 'goal', title: $goal, "
            "user_uid: $owner, status: 'active'})"
            f"<-[:{EDGE}]-(:Entity:Habit {{uid: $habit, entity_type: 'habit', "
            "title: $habit, user_uid: $stranger, status: 'active'})",
            goal=GOAL,
            owner=OWNER,
            habit=STRANGERS_HABIT,
            stranger=STRANGER,
        )

    has = await goal_relationships.has_relationship("habits", GOAL)
    shown = await goal_relationships.get_related_uids("habits", GOAL)

    assert has.is_ok and has.value is True
    assert shown.is_ok and shown.value == []


@pytest.mark.asyncio
async def test_a_linked_draft_ku_is_withheld_and_a_published_one_returned(
    neo4j_driver, goal_relationships, clean_neo4j
):
    """The wall's publication half: shared content across the edge must be published.

    Both readers that name far ends withhold the draft; the existence check counts it.
    """
    published, draft = P + "ku_published", P + "ku_draft"
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (g:Entity:Goal {uid: $goal, entity_type: 'goal', title: $goal, "
            "user_uid: $owner, status: 'active'}) "
            "CREATE (p:Entity:Ku {uid: $published, entity_type: 'ku', title: $published, "
            "publication_state: $published_state}) "
            "CREATE (d:Entity:Ku {uid: $draft, entity_type: 'ku', title: $draft, "
            "publication_state: $draft_state}) "
            f"CREATE (p)-[:{EDGE}]->(g), (d)-[:{EDGE}]->(g)",
            goal=GOAL_HABIT_ONLY,
            owner=OWNER,
            published=published,
            draft=draft,
            published_state=PublicationState.PUBLISHED.value,
            draft_state=PublicationState.DRAFT.value,
        )

    shown = await goal_relationships.get_related_uids("everything", GOAL_HABIT_ONLY)
    batched = await goal_relationships.batch_get_related_uids("everything", [GOAL_HABIT_ONLY])
    has = await goal_relationships.has_relationship("everything", GOAL_HABIT_ONLY)

    assert shown.is_ok and shown.value == [published]
    assert batched.is_ok and batched.value == {GOAL_HABIT_ONLY: [published]}
    assert has.is_ok and has.value is True
