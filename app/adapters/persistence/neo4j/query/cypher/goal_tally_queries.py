"""
Goal tally Cypher — a goal's contribution tally, in its one spelling.

The tally is the measurement a TASK_BASED goal's progress is: the goal owner's tasks
and events that contribute to the goal (``(contributor)-[:CONTRIBUTES_TO_GOAL]->(Goal)``),
less the ones left out (CANCELLED) and the tasks that opt out of counting
(``completion_updates_goal`` false; absent reads as True), and how many of those are
done (COMPLETED). The classes come from ``core.models.goal.goal_contribution``, the
definition the recompute's trigger also reads. Two callers run this statement — the
locked recompute that writes the goal's figure
(``GoalsBackend.recompute_progress_from_contributions``) and the plain read a dashboard
reports from (``GoalsBackend.get_contribution_tally``) — so the number a goal is written
with and the number it is reported with are counted by the same rule. A copy of the
statement is a second membership rule that drifts — compose, never restate.

``tests/unit/test_goal_contribution_tally_statement.py`` holds both callers to this
statement.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.goal.goal_contribution import CONTRIBUTOR_TYPES, DONE_STATUSES, OUT_STATUSES
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties


def build_contribution_tally_query() -> str:
    """The statement counting a goal's contributions: ``total_contributions`` / ``completed_contributions``.

    Takes ``$uid`` (the goal) beside :func:`contribution_tally_params`. Returns one row,
    zeros included — an aggregate over no match is a row of zero counts, so a goal with
    no counting contribution (or no goal at all) reads 0 / 0. A contributor is counted
    once however many edges join it to the goal, and only when the goal's owner owns it:
    the owner is read off the goal, so no caller can count a goal against another
    user's contributions.
    """
    entity = NeoLabel.ENTITY.value
    return f"""
        MATCH (goal:{entity} {{uid: $uid}})
        OPTIONAL MATCH (c:{entity})-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}]->(goal)
        WHERE c.entity_type IN $contributor_types
          AND c.user_uid = goal.user_uid
          AND NOT coalesce(c.status, '') IN $out
          AND (c.entity_type <> $task_type OR coalesce(c.completion_updates_goal, true))
        RETURN count(DISTINCT c) AS total_contributions,
               count(DISTINCT CASE WHEN c.status IN $done THEN c END) AS completed_contributions
        """


def contribution_tally_params() -> Neo4jProperties:
    """The statement's parameters other than ``$uid`` — the contributor kinds and their classes."""
    return {
        "contributor_types": [t.value for t in CONTRIBUTOR_TYPES],
        "task_type": EntityType.TASK.value,
        "done": sorted(s.value for s in DONE_STATUSES),
        "out": sorted(s.value for s in OUT_STATUSES),
    }
