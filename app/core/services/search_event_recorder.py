"""
Search Event Recorder
=====================

Event-bus subscriber that persists `search.executed` events as :SearchEvent
nodes — the write half of discovery analytics (the read half is the
content-gap aggregation on the admin surface).

Fail-soft by design: the recorder never raises. The event bus additionally
isolates handler errors, so a recorder failure can never break a search.
Tier-independent — a plain graph write, no AI dependency (ADR-043 untouched).

Backend: SearchEventBackend.record_search_event
See: /docs/roadmap/DISCOVERY_ANALYTICS_ROADMAP.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from core.ports.query_types import SearchEventProps
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.events.search_events import SearchExecuted
    from core.ports.search_protocols import SearchEventBackendOperations


class SearchEventRecorder:
    """Persists search.executed events as :SearchEvent nodes."""

    def __init__(self, backend: SearchEventBackendOperations) -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.search_event_recorder")

    async def handle_search_executed(self, event: SearchExecuted) -> None:
        """Record one :SearchEvent node for a search.executed event. Never raises."""
        props = SearchEventProps(
            uid=str(uuid4()),
            query_text=event.query_text,
            query_normalized=event.query_text.lower().strip(),
            user_uid=event.user_uid,
            entry_point=event.entry_point,
            domains=list(event.domains),
            filters_json=event.filters_json,
            result_count=event.result_count,
            zero_results=event.zero_results,
            semantic_boost=event.semantic_boost,
            created_at=event.occurred_at.isoformat(),
        )
        try:
            result = await self.backend.record_search_event(props)
        except NEO4J_EXCEPTIONS as e:
            self.logger.warning(f"Search event not recorded (database error): {e}")
            return
        if result.is_error:
            self.logger.warning(f"Search event not recorded: {result.error}")
