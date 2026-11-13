"""A goal's habit system: each habit that supports the goal, at its tier.

The link is ``(Habit)-[:SUPPORTS_GOAL {weight, essentiality}]->(Goal)``; the tier is the
edge's ``essentiality`` (``HabitEssentiality.from_stored`` reads an absent or unknown
value as supporting). A principle supports a goal by the same edge type and is never
one of these.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.enums.goal_enums import HabitEssentiality


@dataclass(frozen=True)
class GoalHabitLink:
    """One habit that supports a goal: what the goal page lists and its controls name.

    Attributes:
        habit_uid: the habit, one of the goal owner's own.
        title: the habit's title as stored.
        essentiality: the link's tier.
    """

    habit_uid: str
    title: str
    essentiality: HabitEssentiality

    def listing_order(self) -> tuple[int, str]:
        """The page's order: by tier, essential first, then by title."""
        return (list(HabitEssentiality).index(self.essentiality), self.title.casefold())
