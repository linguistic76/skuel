"""Vault door: a Task's goal link is ONE fact authored two ways, stored two ways.

``connections.fulfills_goal`` is the registered relationship field — it drives the
``(Task)-[:FULFILLS_GOAL]->(Goal)`` edge and nothing else. ``fulfills_goal_uid`` is the
Task's node column, which the app doors set and every in-hand reader consults (the
relevance scorer, the completion → goal-progress cascade, the edit form's picker). The
preparer reconciles the two so a vault task satisfies BOTH kinds of reader: the edge
target is stamped as the property, a bare property authors the connection, and a file
that names no goal clears a stale stamp on re-ingest (a ``None`` in props REMOVES the
node property under ``SET n += props``).

The invariant: property == edge target, wherever both exist.
"""

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.preparer import prepare_entity_data

_PATH = Path("/vault/tasks/ship-it.md")
_USER = "user_parity"


def _prepare(entity_type: EntityType, data: dict) -> dict:
    return prepare_entity_data(entity_type, dict(data), None, _PATH, _USER)


class TestTaskGoalLinkParity:
    def test_the_connection_stamps_the_property(self) -> None:
        prepared = _prepare(
            EntityType.TASK,
            {"title": "Ship it", "connections": {"fulfills_goal": ["goal.ship.v1"]}},
        )

        assert prepared["connections.fulfills_goal"] == ["goal.ship.v1"]
        assert prepared["fulfills_goal_uid"] == "goal.ship.v1"

    def test_a_bare_property_authors_the_connection(self) -> None:
        """A file that spells the link as the column, not the connection, still gets
        the edge — otherwise the property-only spelling would be invisible to every
        graph reader."""
        prepared = _prepare(EntityType.TASK, {"title": "Ship it", "fulfills_goal_uid": "goal.a"})

        assert prepared["fulfills_goal_uid"] == "goal.a"
        assert prepared["connections.fulfills_goal"] == ["goal.a"]

    def test_no_goal_clears_a_stale_stamp(self) -> None:
        """Re-ingesting a file whose goal link was removed retracts the edge (the
        authored-edge diff) — the property must go with it, which needs an explicit
        ``None`` in props, not an absent key."""
        prepared = _prepare(EntityType.TASK, {"title": "Ship it"})

        assert "fulfills_goal_uid" in prepared
        assert prepared["fulfills_goal_uid"] is None
        assert "connections.fulfills_goal" not in prepared

    def test_the_edge_target_wins_when_the_two_disagree(self) -> None:
        """The connection is the registered authoring surface and the half the graph
        readers see; a property that contradicts it is the stale copy."""
        prepared = _prepare(
            EntityType.TASK,
            {
                "title": "Ship it",
                "fulfills_goal_uid": "goal.stale",
                "connections": {"fulfills_goal": ["goal.current"]},
            },
        )

        assert prepared["fulfills_goal_uid"] == "goal.current"
        assert prepared["connections.fulfills_goal"] == ["goal.current"]

    def test_a_scalar_connection_is_normalised_to_a_list(self) -> None:
        prepared = _prepare(
            EntityType.TASK, {"title": "Ship it", "connections": {"fulfills_goal": "goal.one"}}
        )

        assert prepared["connections.fulfills_goal"] == ["goal.one"]
        assert prepared["fulfills_goal_uid"] == "goal.one"

    def test_only_the_first_target_is_stamped(self) -> None:
        """The column is singular; a multi-goal connection writes every edge and the
        property names the first."""
        prepared = _prepare(
            EntityType.TASK,
            {"title": "Ship it", "connections": {"fulfills_goal": ["goal.one", "goal.two"]}},
        )

        assert prepared["connections.fulfills_goal"] == ["goal.one", "goal.two"]
        assert prepared["fulfills_goal_uid"] == "goal.one"

    @pytest.mark.parametrize("entity_type", [EntityType.GOAL, EntityType.HABIT])
    def test_other_types_are_untouched(self, entity_type: EntityType) -> None:
        """``Goal.fulfills_goal_uid`` is the SUB-GOAL → parent property, a different
        fact with a different edge (HAS_SUBGOAL); it must not grow a Task connection."""
        prepared = _prepare(entity_type, {"title": "Parented", "fulfills_goal_uid": "goal.parent"})

        assert prepared["fulfills_goal_uid"] == "goal.parent"
        assert "connections.fulfills_goal" not in prepared

    def test_a_habit_without_the_field_gains_no_stamp(self) -> None:
        prepared = _prepare(EntityType.HABIT, {"title": "Daily pages"})

        assert "fulfills_goal_uid" not in prepared
