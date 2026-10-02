"""
Habit Cypher fragments — a completion inside the adherence window, and the per-habit count.

``core.models.habit.adherence`` defines a habit's adherence as its completions in
the trailing window over what its frequency expects there. These two fragments
are the Cypher half of that definition: which ``:HabitCompletion`` is inside the
window, and how many of them belong to one habit. Every read that counts
completions toward adherence or consistency composes them — the per-user count
behind ``consistency_score`` (``CrossDomainBackend.get_habit_analytics``), the
per-habit count (``CrossDomainBackend.get_habit_window_completions``) and both
user-context statements. A copy is a second definition that drifts — compose,
never restate.

The predicate reads ``completed_at`` through ``datetime()`` and compares it with
bounds that cross the driver as ISO strings read the same way, so both operands
are one temporal type whatever the writer stored (an ISO string on every live
row today). The bounds are ``[start, end)`` — the window's first instant and the
first instant after its last day, on the stored clock
(``core.models.habit.adherence.adherence_window_bounds``) — so a completion
stamped in the future is outside the window until its day arrives.
"""

from __future__ import annotations

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

from ._helpers import validate_identifier

#: The parameter names the user-context statements bind the window to.
HABIT_WINDOW_START_PARAM = "habit_window_start"
HABIT_WINDOW_END_PARAM = "habit_window_end"


def build_completion_in_window_predicate(alias: str, start_param: str, end_param: str) -> str:
    """``alias`` (a ``:HabitCompletion``) completed inside ``[$start_param, $end_param)``."""
    validate_identifier(alias, "alias")
    validate_identifier(start_param, "start_param")
    validate_identifier(end_param, "end_param")
    return (
        f"(datetime({alias}.completed_at) >= datetime(${start_param})"
        f" AND datetime({alias}.completed_at) < datetime(${end_param}))"
    )


def build_habit_window_completion_count(
    owner_alias: str,
    habit_alias: str,
    start_param: str = HABIT_WINDOW_START_PARAM,
    end_param: str = HABIT_WINDOW_END_PARAM,
) -> str:
    """How many of ``owner_alias``'s completions of ``habit_alias`` fall inside the window.

    A completion counts when the habit's owner owns it (``OWNS``, ADR-086) and it
    names the habit (``habit_uid``) — another user's record of the same uid is
    not this habit's completion. An integer expression; zero when there are none.
    """
    validate_identifier(owner_alias, "owner_alias")
    validate_identifier(habit_alias, "habit_alias")
    predicate = build_completion_in_window_predicate("window_completion", start_param, end_param)
    return (
        f"COUNT {{ ({owner_alias})-[:{RelationshipName.OWNS.value}]->"
        f"(window_completion:{NeoLabel.HABIT_COMPLETION.value}) "
        f"WHERE window_completion.habit_uid = {habit_alias}.uid AND {predicate} }}"
    )
