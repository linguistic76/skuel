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

from typing import Any, TypedDict

from adapters.persistence.neo4j._search_raw_mixin import _SearchRawMixin
from core.models.entity import Entity
from core.models.enums import SearchVisibility
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Result


class CapturedQuery(TypedDict, total=False):
    """What the stub driver recorded: the composed Cypher and its parameters.

    ``total=False`` is load-bearing — a call rejected before it reaches the
    driver (an invalid sort field, say) leaves both keys absent, and
    ``"query" not in store`` is how those tests assert the query never ran.
    """

    query: str
    # boundary: genuinely heterogeneous — faceted params mix str (query_text),
    # list[str] (tags_contain), and arbitrary property-filter VALUES whose type
    # is whatever the domain's field holds. Neo4jProperties is too narrow.
    params: dict[str, Any]


class _CapturingResult:
    # boundary: mirrors AsyncResult.data(), whose records are nested —
    # a node-property dict under "entity" plus collected enrichment lists.
    # Neo4jProperties (flat scalar values) cannot describe that shape.
    async def data(self) -> list[dict[str, Any]]:
        return []


class _CapturingSession:
    def __init__(self, store: CapturedQuery) -> None:
        self._store = store

    async def __aenter__(self) -> _CapturingSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def run(self, query: str, params: dict[str, Any]) -> _CapturingResult:
        # boundary: params as above — the driver's own signature is equally wide.
        self._store["query"] = query
        self._store["params"] = params
        return _CapturingResult()


class _CapturingDriver:
    def __init__(self, store: CapturedQuery) -> None:
        self._store = store

    def session(self) -> _CapturingSession:
        return _CapturingSession(self._store)


class CapturingBackend(_SearchRawMixin[Entity]):
    """Minimal ``_SearchRawMixin`` host — only what the raw search methods read.

    Parameterized on ``Entity`` (the universal base) rather than a per-label
    model: the harness is label-parameterized, and ``faceted_search_raw`` never
    touches ``entity_class`` — it returns raw record dicts, not domain models.
    """

    def __init__(self, store: CapturedQuery, label: NeoLabel = NeoLabel.KU) -> None:
        # boundary: fasthtml-style test double — _CapturingDriver implements the
        # one method the mixin uses (session()), not the full AsyncDriver surface.
        self.driver = _CapturingDriver(store)  # type: ignore[assignment]
        self.label = label
        self.entity_class = Entity


async def run_faceted(
    store: CapturedQuery,
    *,
    user_uid: str | None = None,
    label: NeoLabel = NeoLabel.KU,
    # boundary: the keyword surface of faceted_search_raw is heterogeneous by
    # construction — tuples, dicts, bools, enums, ints. Narrowing this would
    # mean restating that whole signature here and re-editing it on every change.
    **overrides: Any,
) -> Result[list[dict[str, Any]]]:
    """Invoke ``faceted_search_raw``, recording the Cypher into ``store``.

    Defaults describe an anonymous PUBLIC browse; pass ``user_uid`` and
    ``visibility`` to compose any other scoping shape. The return type mirrors
    ``faceted_search_raw``'s own — raw records, not domain models.
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
