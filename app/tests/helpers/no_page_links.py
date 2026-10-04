"""A ``ConnectionFetchOperations`` with no links — for tests of the routes around them.

The Activity pages' link reader (``ConnectionFetchBackend``) is measured on a real
graph by tests/integration/routes/test_activity_page_links.py; a test of a card's
field route or the day view's assembly hands it this instead. It records each read,
so a test can still see which label and uids a surface asked for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums.neo_labels import NeoLabel
    from core.ports.query_types import EntityConnection


class NoPageLinks:
    """Answers every page-link read with no links; records what it was asked."""

    def __init__(self) -> None:
        self.reads: list[tuple[NeoLabel, list[str]]] = []

    async def fetch_entity_connections(
        self, label: NeoLabel, entity_uids: list[str]
    ) -> dict[str, list[EntityConnection]]:
        self.reads.append((label, list(entity_uids)))
        return {}

    async def fetch_source_pathstep(self, ps_uid: str, owner_uid: str) -> dict[str, str] | None:
        return None
