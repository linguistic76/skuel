"""Every name in the query package's ``__all__`` must actually resolve.

`adapters/persistence/neo4j/query/__init__.py` re-exports a wide public surface
(the `cypher/` `build_*` functions, boundary enums, the fluent builder). Some of
those names arrive by re-export from another module, so deleting a module can
silently break `from ...query import X` while leaving `__all__` advertising it.

That is not hypothetical: the `query_builders/` decommission (2026-08-17) removed
`_query_models.py`, which had been re-exporting `QueryIntent`. Ruff, mypy, pyright
and the whole unit suite stayed green — nothing *currently* imports `QueryIntent`
from that path — but `from adapters.persistence.neo4j.query import QueryIntent`
raised ImportError. This test is the cheap guard for that class of break.
"""

from __future__ import annotations

import adapters.persistence.neo4j.query as query_pkg


def test_every_exported_name_resolves() -> None:
    """`__all__` is a promise: each name must be an attribute of the package."""
    missing = [name for name in query_pkg.__all__ if not hasattr(query_pkg, name)]

    assert missing == [], (
        f"query/__init__.py advertises {missing} in __all__ but does not bind them. "
        "A re-exported name lost its source module — import it directly or drop it "
        "from __all__."
    )


def test_all_is_sorted_and_unique() -> None:
    """Duplicate entries hide deletions; the list is maintained sorted."""
    assert len(query_pkg.__all__) == len(set(query_pkg.__all__)), "duplicate __all__ entries"
