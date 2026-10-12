"""An in-memory stand-in for ``HabitsBackend.update_habit_learning_state``.

It keeps each habit's learning properties and applies a planner the way the backend
does: the planner sees every ``HABIT_LEARNING_PROPERTIES`` key (``None`` where unwritten),
a key outside that set is refused, and a uid it does not hold is not found. The real
statement — the lock, the transaction — is proven against the container in
``tests/integration/routes/test_habit_learning_state.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.habit.learning_state import HABIT_LEARNING_PROPERTIES
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.models.type_hints import Neo4jProperties


class HabitLearningStore:
    """The learning properties of the habits it holds, keyed by uid."""

    def __init__(self, *uids: str) -> None:
        self.states: dict[str, Neo4jProperties] = {uid: {} for uid in uids}
        self.writes: list[tuple[str, Neo4jProperties]] = []

    async def update_habit_learning_state(
        self, habit_uid: str, plan: Callable[[Neo4jProperties], Neo4jProperties]
    ) -> Result[Neo4jProperties]:
        if habit_uid not in self.states:
            return Result.fail(Errors.not_found("Habit", habit_uid))
        stored = self.states[habit_uid]
        properties = plan({name: stored.get(name) for name in HABIT_LEARNING_PROPERTIES})
        unknown = set(properties) - set(HABIT_LEARNING_PROPERTIES)
        if unknown:
            return Result.fail(Errors.validation(f"Not learning properties: {unknown}"))
        stored.update(properties)
        self.writes.append((habit_uid, properties))
        return Result.ok(properties)
