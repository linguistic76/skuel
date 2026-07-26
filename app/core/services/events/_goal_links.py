# skuel-lint: disable-file=SKUEL005 -- fail-soft read-projection; events returned unchanged on lookup failure (derived field is best-effort, not a propagated error)
"""Shared helper: populate the derived ``contributes_to_goal_uid`` on Event objects.

The Event→Goal link is the ``(Event)-[:CONTRIBUTES_TO_GOAL]->(Goal)`` graph edge,
not a persisted property. Event services that read the link in-memory (scoring)
enrich their event lists from the edge via this helper rather than re-implementing
the batch lookup.

The graph is the single source of truth; the derived field is a read-projection
populated at fetch time and never written back.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from core.services.goal_links import pick_goal

if TYPE_CHECKING:
    from core.models.event.event import Event
    from core.ports.domain_protocols import EventsOperations


async def enrich_events_with_goal_links(
    backend: EventsOperations,
    events: list[Event],
    active_goal_uids: list[str] | None = None,
) -> list[Event]:
    """Return events with their derived ``contributes_to_goal_uid`` populated.

    Batch-looks up the CONTRIBUTES_TO_GOAL edge for ``events`` and returns new Event
    instances (frozen → ``replace``) carrying the linked goal uid. When an event
    contributes to multiple goals, the one matching ``active_goal_uids`` is preferred
    so the priority scorer sees the active goal rather than an arbitrary inactive one.
    Events with no edge are returned unchanged (field stays ``None``).
    """
    if not events:
        return events
    links = await backend.get_goal_links_for_events([e.uid for e in events])
    if links.is_error or not links.value:
        return events
    link_map: dict[str, list[str]] = links.value
    return [
        replace(
            event,
            contributes_to_goal_uid=pick_goal(link_map[event.uid], active_goal_uids),
        )
        if event.uid in link_map
        else event
        for event in events
    ]
