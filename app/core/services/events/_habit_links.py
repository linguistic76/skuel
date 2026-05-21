"""Shared helper: populate the derived ``reinforces_habit_uid`` on Event objects.

The Event↔Habit link is the ``(Event)-[:REINFORCES_HABIT]->(Habit)`` graph edge,
not a persisted property. Event services that read the link in-memory (scoring,
analytics, grouping, engagement signals) enrich their event lists from the edge
via this helper rather than re-implementing the batch lookup.

The graph is the single source of truth; the derived field is a read-projection
populated at fetch time and never written back.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.event.event import Event


async def enrich_events_with_habit_links(backend: Any, events: list[Event]) -> list[Event]:
    """Return events with their derived ``reinforces_habit_uid`` populated.

    Batch-looks up the REINFORCES_HABIT edge for ``events`` and returns new Event
    instances (frozen → ``replace``) carrying the linked habit uid. Events with no
    edge are returned unchanged (field stays ``None``).
    """
    if not events:
        return events
    links = await backend.get_habit_links_for_events([e.uid for e in events])
    if links.is_error or not links.value:
        return events
    link_map = links.value
    return [
        replace(event, reinforces_habit_uid=link_map[event.uid]) if event.uid in link_map else event
        for event in events
    ]
