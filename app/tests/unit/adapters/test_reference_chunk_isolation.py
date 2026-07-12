"""Isolation guard: canon :ReferenceChunk is invisible to SearchRouter.

Freezes the Phase-2 invariant that the reference vector index
(``referencechunk_embedding_idx``) is reachable ONLY through the reference
ingest/retrieval door — never through the curriculum `/search` path. DB-free
and introspective (mirrors ``tests/unit/models/test_search_router_registry.py``):
it reads the source of the two files that MUST NOT know about canon and asserts
the index name is absent, and that the chunk vector query still targets only
``contentchunk_embedding_idx``.

If a future edit wires canon into SearchRouter or the shared chunk query, one of
these assertions fails — the deliberate omission is the isolation guarantee.
"""

from pathlib import Path

import adapters.persistence.neo4j.vector_search_backend as vsb_module
import core.models.search.search_router as router_module

REFERENCE_INDEX = "referencechunk_embedding_idx"
CONTENT_INDEX = "contentchunk_embedding_idx"


def _source(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def test_search_router_never_names_reference_index() -> None:
    """SearchRouter must not reference the canon index in any form."""
    source = _source(router_module)
    assert REFERENCE_INDEX not in source, (
        "SearchRouter references the canon reference index "
        f"({REFERENCE_INDEX!r}) — canon must stay invisible to /search."
    )


def test_vector_search_backend_never_names_reference_index() -> None:
    """The shared vector-search backend must not reference the canon index."""
    source = _source(vsb_module)
    assert REFERENCE_INDEX not in source, (
        f"vector_search_backend references the canon reference index "
        f"({REFERENCE_INDEX!r}) — the chunk query must target ContentChunk only."
    )


def test_semantic_search_chunks_targets_only_content_index() -> None:
    """`semantic_search_chunks` still hardcodes contentchunk_embedding_idx alone."""
    import inspect

    source = inspect.getsource(vsb_module.VectorSearchBackend.semantic_search_chunks)
    assert CONTENT_INDEX in source, (
        f"semantic_search_chunks no longer targets {CONTENT_INDEX!r} — "
        "the curriculum chunk retrieval path changed unexpectedly."
    )
    assert REFERENCE_INDEX not in source, (
        f"semantic_search_chunks now targets {REFERENCE_INDEX!r} — canon chunks "
        "must never be reachable through the curriculum chunk query."
    )


def test_reference_adapter_never_queries_content_index() -> None:
    """Symmetric wall (canon P3): the reference adapter must not READ ContentChunk.

    The vault scope made the content index the owner-scoped retrieval substrate;
    a reference-adapter read of it would be the same wall breach in the other
    direction (one Cypher across the two corpora). The adapter legitimately
    *mentions* ContentChunk in docstrings (documenting the wall) and reuses the
    ``ContentChunk`` dataclass as its in-memory chunk shape — so the assert
    targets the QUOTED index literal (what a Cypher/queryNodes call would use)
    and the Cypher label form, never prose.
    """
    import adapters.persistence.neo4j.neo4j_reference_chunk_adapter as adapter_module

    source = _source(adapter_module)
    for query_form in (f"'{CONTENT_INDEX}'", f'"{CONTENT_INDEX}"', "(chunk:ContentChunk"):
        assert query_form not in source, (
            f"The reference chunk adapter contains {query_form!r} — the two corpora "
            "share a contract, never a query (ADR-077)."
        )


def test_scoped_branch_stays_adapter_only() -> None:
    """The scoped exact-cosine scan lives ONLY in the reference chunk adapter.

    The PS-scoped branch (ADR-077) reads :ReferenceChunk via
    ``vector.similarity.cosine`` instead of the index — a second read path that
    must stay behind the same wall. SearchRouter and the shared vector backend
    must not gain a :ReferenceChunk read of either shape.
    """
    import adapters.persistence.neo4j.neo4j_reference_chunk_adapter as adapter_module

    adapter_source = _source(adapter_module)
    assert "vector.similarity.cosine" in adapter_source, (
        "The scoped exact-cosine branch left the reference chunk adapter — "
        "the ADR-077 scoped read must live behind the canon wall."
    )
    for module, name in ((router_module, "SearchRouter"), (vsb_module, "vector_search_backend")):
        source = _source(module)
        assert ":ReferenceChunk" not in source and "ReferenceChunk" not in source, (
            f"{name} now references ReferenceChunk — canon chunks must stay "
            "invisible outside the reference adapter."
        )
