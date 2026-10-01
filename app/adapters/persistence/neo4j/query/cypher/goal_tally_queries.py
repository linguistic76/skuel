"""
Goal tally Cypher — a goal's linked-task tally, in its one spelling.

The tally is the measurement a TASK_BASED goal's progress is: the owner's tasks
that fulfill the goal (``(Task)-[:FULFILLS_GOAL]->(Goal)``) and count toward it
(``completion_updates_goal``, absent read as True), and how many of those are
COMPLETED. Two callers run this statement — the locked recompute that writes the
goal's figure (``GoalsBackend.recompute_progress_from_linked_tasks``) and the
plain read a dashboard reports from (``GoalsBackend.get_linked_task_tally``) —
so the number a goal is written with and the number it is reported with are
counted by the same rule. A copy of the statement is a second membership rule
that drifts — compose, never restate.

``tests/unit/test_goal_linked_task_tally_statement.py`` holds both callers to
this statement.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID


def build_linked_task_tally_query() -> str:
    """The statement counting a goal's linked tasks: ``total_tasks`` / ``completed_tasks``.

    Takes ``$uid`` (the goal) beside :func:`linked_task_tally_params`. Returns one
    row, zeros included — an aggregate over no match is a row of zero counts, so a
    goal with no counting tasks (or no goal at all) reads 0 / 0.
    """
    entity = NeoLabel.ENTITY.value
    return f"""
        MATCH (goal:{entity} {{uid: $uid}})
        OPTIONAL MATCH (task:{entity} {{entity_type: $task_type}})-[:{RelationshipName.FULFILLS_GOAL.value}]->(goal)
        WHERE task.user_uid = $user_uid AND coalesce(task.completion_updates_goal, true)
        RETURN count(task) AS total_tasks,
               count(CASE WHEN task.status = $completed THEN 1 END) AS completed_tasks
        """


def linked_task_tally_params(user_uid: UserUID) -> Neo4jProperties:
    """The statement's parameters other than ``$uid`` — whose tasks, and what counts as done."""
    return {
        "user_uid": user_uid,
        "task_type": EntityType.TASK.value,
        "completed": EntityStatus.COMPLETED.value,
    }
