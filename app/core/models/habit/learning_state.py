"""
Habit learning state — what ADR-048 learns about one habit from how it is kept.

Five properties on the habit's node hold it: the completion-hour histogram
(``completion_hours_json``, a JSON object of hour → completions), the hour the habit
is most often done (``learned_preferred_hour``), an exponential moving average of
on-time completions (``learned_on_time_rate``), how many completions taught it
(``learned_completion_count``), and the difficulty a run of misses suggests
(``learned_difficulty_level``).

The state is read raw from the node, never through the ``Habit`` model, which declares
none of these fields: a model read would drop them. :func:`habit_learning_state` turns
the raw properties into a :class:`~core.ports.query_types.HabitLearningState`, and the
planners here say what a completion or a miss writes next, from the properties as they
stand. The backend runs a planner under the node's write-lock, so two completions in
flight build on each other instead of on the same old state.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from core.constants import LearningLoop
from core.utils.neo4j_props import coerce_float, coerce_int, parse_neo4j_json
from core.utils.sort_functions import make_dict_value_getter

if TYPE_CHECKING:
    from core.models.type_hints import Neo4jProperties
    from core.ports.query_types import HabitLearningState

HABIT_LEARNING_PROPERTIES: Final[tuple[str, ...]] = (
    "completion_hours_json",
    "learned_preferred_hour",
    "learned_on_time_rate",
    "learned_completion_count",
    "learned_difficulty_level",
)
"""The node properties that hold a habit's learning state — every one a planner may write."""


def _completion_hours(raw: object) -> dict[int, int]:
    """The stored histogram as hour → completions; empty when nothing is stored."""
    parsed = parse_neo4j_json(raw, default={})
    if not isinstance(parsed, dict):
        return {}
    return {int(hour): coerce_int(count) for hour, count in parsed.items()}


def habit_learning_state(raw: Mapping[str, object]) -> HabitLearningState:
    """One habit's learning state from its node's raw properties."""
    preferred_hour = raw.get("learned_preferred_hour")
    on_time_rate = raw.get("learned_on_time_rate")
    difficulty = raw.get("learned_difficulty_level")
    return {
        "completion_hours": _completion_hours(raw.get("completion_hours_json")),
        "learned_preferred_hour": coerce_int(preferred_hour)
        if preferred_hour is not None
        else None,
        "learned_on_time_rate": coerce_float(on_time_rate) if on_time_rate is not None else None,
        "learned_completion_count": coerce_int(raw.get("learned_completion_count")),
        "learned_difficulty_level": str(difficulty) if difficulty is not None else None,
    }


def plan_completion_timing(
    raw: Mapping[str, object], hour: int, completed_on_time: bool
) -> Neo4jProperties:
    """What one completion at ``hour`` writes, built on the state ``raw`` holds.

    The hour joins the histogram, the preferred hour is the histogram's busiest hour
    (the first one seen on a tie), the on-time rate moves toward this completion by
    ``LearningLoop.EMA_ALPHA_HABIT_TIMING`` (a habit's first completion sets it outright),
    and the count goes up by one.
    """
    state = habit_learning_state(raw)
    hours = state["completion_hours"]
    hours[hour] = hours.get(hour, 0) + 1
    preferred_hour = max(hours, key=make_dict_value_getter(hours))

    on_time = 1.0 if completed_on_time else 0.0
    old_rate = state["learned_on_time_rate"]
    alpha = LearningLoop.EMA_ALPHA_HABIT_TIMING
    new_rate = on_time if old_rate is None else alpha * on_time + (1 - alpha) * old_rate

    return {
        "completion_hours_json": json.dumps({str(h): count for h, count in hours.items()}),
        "learned_preferred_hour": preferred_hour,
        "learned_on_time_rate": round(new_rate, 4),
        "learned_completion_count": state["learned_completion_count"] + 1,
    }


def plan_difficulty(raw: Mapping[str, object], level: str) -> Neo4jProperties:
    """What a run of misses writes: the difficulty ``level`` it suggests, whatever ``raw`` held."""
    del raw  # the difficulty is the latest assessment, not built on the last one
    return {"learned_difficulty_level": level}
