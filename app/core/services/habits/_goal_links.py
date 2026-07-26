# skuel-lint: disable-file=SKUEL005 -- fail-soft read-projection; habits returned unchanged on lookup failure (derived field is best-effort, not a propagated error)
"""Shared helper: populate the derived ``supports_goal_uid`` on Habit objects.

The Habit→Goal link is the ``(Habit)-[:SUPPORTS_GOAL]->(Goal)`` graph edge,
not a persisted property. Habit services that read the link in-memory (scoring)
enrich their habit lists from the edge via this helper rather than re-implementing
the batch lookup.

The graph is the single source of truth; the derived field is a read-projection
populated at fetch time and never written back.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from core.services.goal_links import pick_goal

if TYPE_CHECKING:
    from core.models.habit.habit import Habit
    from core.ports.domain_protocols import HabitsOperations


async def enrich_habits_with_goal_links(
    backend: HabitsOperations,
    habits: list[Habit],
    active_goal_uids: list[str] | None = None,
) -> list[Habit]:
    """Return habits with their derived ``supports_goal_uid`` populated.

    Batch-looks up the SUPPORTS_GOAL edge for ``habits`` and returns new Habit
    instances (frozen → ``replace``) carrying the linked goal uid. When a habit
    supports multiple goals, the one matching ``active_goal_uids`` is preferred
    so the priority scorer sees the active goal rather than an arbitrary inactive one.
    Habits with no edge are returned unchanged (field stays ``None``).
    """
    if not habits:
        return habits
    links = await backend.get_goal_links_for_habits([h.uid for h in habits])
    if links.is_error or not links.value:
        return habits
    link_map: dict[str, list[str]] = links.value
    return [
        replace(
            habit,
            supports_goal_uid=pick_goal(link_map[habit.uid], active_goal_uids),
        )
        if habit.uid in link_map
        else habit
        for habit in habits
    ]
