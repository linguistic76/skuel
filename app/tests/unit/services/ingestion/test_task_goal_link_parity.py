"""Vault door: a Task's goals are edges only — no column rides beside them.

``connections.contributes_to_goal`` is the registered relationship field; it drives one
``(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)`` edge per target and nothing else. A task
contributes to any number of goals, so the preparer passes every target through and
stamps no node property for any of them. ``Goal.fulfills_goal_uid`` — a sub-goal's
parent — is a different fact and passes through untouched.
"""

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.services.ingestion.preparer import prepare_entity_data

_PATH = Path("/vault/tasks/ship-it.md")
_USER = "user_parity"


def _prepare(entity_type: EntityType, data: dict) -> dict:
    return prepare_entity_data(entity_type, dict(data), None, _PATH, _USER)


class TestTaskGoalLinksAreEdgesOnly:
    def test_every_target_is_carried_and_no_column_is_stamped(self) -> None:
        prepared = _prepare(
            EntityType.TASK,
            {
                "title": "Ship it",
                "connections": {"contributes_to_goal": ["goal.one", "goal.two"]},
            },
        )

        assert prepared["connections.contributes_to_goal"] == ["goal.one", "goal.two"]
        assert "fulfills_goal_uid" not in prepared
        assert "contributes_to_goal_uid" not in prepared
        assert "contributes_to_goal_uids" not in prepared

    def test_a_task_without_goals_gains_no_stamp(self) -> None:
        prepared = _prepare(EntityType.TASK, {"title": "Ship it"})

        assert "fulfills_goal_uid" not in prepared
        assert "connections.contributes_to_goal" not in prepared

    @pytest.mark.parametrize("entity_type", [EntityType.GOAL, EntityType.HABIT])
    def test_other_types_are_untouched(self, entity_type: EntityType) -> None:
        """``Goal.fulfills_goal_uid`` is the SUB-GOAL → parent property, a different
        fact with a different edge (HAS_SUBGOAL); it must not grow a Task connection."""
        prepared = _prepare(entity_type, {"title": "Parented", "fulfills_goal_uid": "goal.parent"})

        assert prepared["fulfills_goal_uid"] == "goal.parent"
        assert "connections.contributes_to_goal" not in prepared

    def test_a_habit_without_the_field_gains_no_stamp(self) -> None:
        prepared = _prepare(EntityType.HABIT, {"title": "Daily pages"})

        assert "fulfills_goal_uid" not in prepared
