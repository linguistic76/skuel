"""
Goal contributions — the tasks and events that count toward a goal's progress.

A task or an event contributes to a goal through one edge,
``(contributor)-[:CONTRIBUTES_TO_GOAL]->(Goal)`` (ADR-090). A TASK_BASED goal's progress
is its contributions' tally: how many count, and how many of those are done. Each
contribution sits in one of three classes by its status:

- **done** — COMPLETED;
- **out** — CANCELLED: no longer part of the goal's plan, so it is left out of the count
  and does not hold the goal's progress down;
- **not done** — every other status, FAILED included (a failed contribution keeps the
  goal below 100% until it is reopened or cancelled), and a missing status.

The tally statement (``goal_tally_queries.build_contribution_tally_query``) counts by
these sets, and a status write that moves a contribution from one class to another
announces ``GoalContributionsChanged`` (:func:`moves_contribution_class`) — one
definition for the count and for its trigger.

See: /docs/roadmap/activity-links-arc.md (R5, R6, R11)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from core.models.enums.entity_enums import EntityStatus, EntityType


class ContributionClass(StrEnum):
    """Where a contribution's status puts it in its goal's tally."""

    DONE = "done"
    NOT_DONE = "not_done"
    OUT = "out"


#: The kinds of entity whose ``CONTRIBUTES_TO_GOAL`` edge a goal's tally counts.
CONTRIBUTOR_TYPES: Final = (EntityType.TASK, EntityType.EVENT)

#: Statuses counted as done.
DONE_STATUSES: Final = frozenset({EntityStatus.COMPLETED})

#: Statuses left out of the count.
OUT_STATUSES: Final = frozenset({EntityStatus.CANCELLED})


def contribution_class(status: str | None) -> ContributionClass:
    """The tally class a contribution with ``status`` sits in (a missing status: not done)."""
    if status is None:
        return ContributionClass.NOT_DONE
    if status in {s.value for s in DONE_STATUSES}:
        return ContributionClass.DONE
    if status in {s.value for s in OUT_STATUSES}:
        return ContributionClass.OUT
    return ContributionClass.NOT_DONE


def moves_contribution_class(prior_status: str | None, new_status: str | None) -> bool:
    """Whether a status write from ``prior_status`` to ``new_status`` changes a goal's tally."""
    return contribution_class(prior_status) is not contribution_class(new_status)
