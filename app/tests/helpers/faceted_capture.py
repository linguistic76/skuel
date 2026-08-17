"""Capture the Cypher ``faceted_search_raw`` composes, without a database.

``faceted_search_raw`` builds its query as a string and hands it to the driver,
so a stub driver that records ``(query, params)`` is enough to assert on the
composition — the ownership predicate, the publication gate, ORDER BY/SKIP, the
tag facet. Used by the scoping tests (which care WHICH predicate is emitted) and
the library faceted tests (which care about sort/pagination/facets).

Integration coverage of the same path against a real container lives in
``tests/integration/test_advanced_search_scoping.py``; this harness answers
"what Cypher did we build", not "what rows come back".
"""

from __future__ import annotations

from typing import Any

from adapters.persistence.neo4j._search_raw_mixin import _SearchRawMixin
from core.models.enums import SearchVisibility
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Result


class _CapturingResult:
    async def data(self) -> list[dict[str, Any]]:
        return []


class _CapturingSession:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    async def __aenter__(self) -> _CapturingSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def run(self, query: str, params: dict[str, Any]) -> _CapturingResult:
        self._store["query"] = query
        self._store["params"] = params
        return _CapturingResult()


class _CapturingDriver:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def session(self) -> _CapturingSession:
        return _CapturingSession(self._store)


class CapturingBackend(_SearchRawMixin[Any]):
    """Minimal `_SearchRawMixin` host — only what the raw search methods read."""

    def __init__(self, store: dict[str, Any], label: NeoLabel = NeoLabel.KU) -> None:
        self.driver = _CapturingDriver(store)  # type: ignore[assignment]  # boundary: test stub
        self.label = label
        self.entity_class = object


async def run_faceted(
    store: dict[str, Any],
    *,
    user_uid: str | None = None,
    label: NeoLabel = NeoLabel.KU,
    **overrides: Any,
) -> Result[list[dict[str, Any]]]:
    """Invoke ``faceted_search_raw``, recording the Cypher into ``store``.

    Defaults describe an anonymous PUBLIC browse; pass ``user_uid`` and
    ``visibility`` to compose any other scoping shape.
    """
    backend = CapturingBackend(store, label)
    kwargs: dict[str, Any] = {
        "search_fields": ("title", "description"),
        "search_order_by": "updated_at",
        "graph_enrichment_patterns": (),
        "property_filters": {},
        "visibility": SearchVisibility.PUBLIC,
    }
    kwargs.update(overrides)
    return await backend.faceted_search_raw(user_uid, **kwargs)
