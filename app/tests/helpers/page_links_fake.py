"""A ``ConnectionFetchOperations`` with canned links — for tests of the surfaces around the reader.

The Activity pages' link reader (``ConnectionFetchBackend``) is measured on a real
graph by tests/integration/routes/test_activity_page_links.py; a test of a card's
field route or the day view's assembly hands it this instead. It answers each uid with
the links it was given (none by default) and records each read, so a test sees both
what a surface asked for and that the links reached what it rendered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from core.models.enums.neo_labels import NeoLabel
    from core.ports.query_types import EntityConnection


def page_link(heading: str, title: str, connected_type: str = "goal") -> EntityConnection:
    """One page-link row, as the reader returns it."""
    return {
        "heading": heading,
        "rel_type": "PROBE",
        "connected_uid": f"{connected_type}_{title.lower().replace(' ', '_')}",
        "title": title,
        "connected_type": connected_type,
    }


class FakePageLinks:
    """Answers a page-link read from canned links; records what it was asked."""

    def __init__(self, links: Mapping[str, list[EntityConnection]] | None = None) -> None:
        self._links = dict(links or {})
        self.reads: list[tuple[NeoLabel, list[str]]] = []

    async def fetch_entity_connections(
        self, label: NeoLabel, entity_uids: list[str]
    ) -> dict[str, list[EntityConnection]]:
        self.reads.append((label, list(entity_uids)))
        return {uid: self._links[uid] for uid in entity_uids if uid in self._links}

    async def fetch_source_pathstep(self, ps_uid: str, owner_uid: str) -> dict[str, str] | None:
        return None
