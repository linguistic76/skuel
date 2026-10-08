"""
Connection-Fetch Protocols
==========================

Port for the links an Activity Domain page shows: the detail page's Connections
section and the list card. Authors + executes the parameterized Cypher below the
hexagonal boundary so ``core/`` stays Cypher-free (ADR-044).

What a page shows is declared once, in the relationship registry: the domain's
definitions that carry a ``page_heading`` (``DomainRelationshipConfig.page_views``,
ADR-090 §2).

Implementation: adapters/persistence/neo4j/connection_fetch_backend.py
Consumers: adapters/inbound/activity_ui_factory.py (list + detail),
adapters/inbound/route_factories/activity_field_api_factory.py (the card re-render),
ui/today/orchestrator.py (the day's cards)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel
    from core.ports.query_types import EntityConnection


@runtime_checkable
class ConnectionFetchOperations(Protocol):
    """Fetch the links an Activity page shows, and an activity's curriculum origin."""

    async def fetch_entity_connections(
        self, label: NeoLabel, entity_uids: list[str]
    ) -> dict[str, list[EntityConnection]]:
        """Batch-fetch the page links of ``label`` entities, both directions.

        Returns ``entity_uid -> rows``, each row under the heading of the page view
        that reads it, in the order of the domain's page views; a far end is listed once
        under its heading. Empty dict on no input
        or query failure (page-resilient).
        """
        ...

    async def fetch_source_pathstep(self, ps_uid: str, owner_uid: str) -> dict[str, str] | None:
        """Resolve a spawned activity's ``source_path_step_uid`` to its PathStep.

        Returns ``{"uid", "title"}`` or ``None`` if the PathStep is missing, is a
        draft ``owner_uid`` never engaged, or the lookup fails.
        """
        ...
