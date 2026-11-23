"""What a raw-Cypher seed shared by the activity kinds writes, kind by kind.

A seed that writes one shape onto every activity label writes, beyond the fields they all
hold, only those its kind declares: a property no field of its class names is a key no
read reads, which the integration graph census fails (``tests/integration/_graph_census.py``).
"""

from dataclasses import fields

from core.models.choice.choice import Choice
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task

_ACTIVITY_CLASSES: dict[str, type] = {
    cls.__name__: cls for cls in (Task, Goal, Habit, Event, Choice, Principle)
}


def declared_fields(label: str, **properties: object) -> dict[str, object]:
    """``properties`` less each one the class ``label`` names does not declare as a field.

    ``declared_fields("Habit", recurrence_pattern="daily", event_date=day)`` is the
    recurrence alone: a Habit has no day.
    """
    names = {spec.name for spec in fields(_ACTIVITY_CLASSES[label])}
    return {name: value for name, value in properties.items() if name in names}
