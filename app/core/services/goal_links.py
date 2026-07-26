"""Shared selection rule for derived entity→Goal read-projections.

Habits (``SUPPORTS_GOAL``) and Events (``CONTRIBUTES_TO_GOAL``) both project a
single goal uid onto a frozen model at fetch time, and both may find several
candidate edges. The tie-break between them is one rule, not two — it lives here
so the two ``_goal_links`` enrichers cannot drift apart.

See: core/services/habits/_goal_links.py, core/services/events/_goal_links.py
"""

from __future__ import annotations


def pick_goal(goal_uids: list[str], active_goal_uids: list[str] | None) -> str:
    """Return the best goal UID for scoring: prefer an active goal, else first."""
    if active_goal_uids:
        active_set = set(active_goal_uids)
        for uid in goal_uids:
            if uid in active_set:
                return uid
    return goal_uids[0]
