"""Tests for SearchRouter.retrieve_scoped_chunks — the chunk-level (RAG) scope path."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.ps_content.content_chunks import ContentChunkType
from core.models.search.search_router import SearchRouter
from core.models.search_request import SearchRequest
from core.utils.result_simplified import Result


def _router_with_vector_search(vector_search: Any | None) -> SearchRouter:
    services = MagicMock()
    services.vector_search_service = vector_search
    return SearchRouter(services)


@pytest.mark.anyio
async def test_forwards_query_limit_and_parent_filters() -> None:
    """The request's text/limit/facets are forwarded to the vector service."""
    vector_search = MagicMock()
    vector_search.find_similar_chunks_by_text = AsyncMock(return_value=Result.ok([]))
    router = _router_with_vector_search(vector_search)

    request = SearchRequest(query_text="what is the body?", nous="body", limit=7)
    # Persisted ContentChunkType VALUE — the router is a pass-through, but a
    # hand-written UPPERCASE literal here is what taught the spelling that made
    # the Askesis chunk filter match zero rows.
    chunk_types = [ContentChunkType.DEFINITION.value]
    result = await router.retrieve_scoped_chunks(request, chunk_types=chunk_types, min_score=0.6)

    assert result.is_ok
    vector_search.find_similar_chunks_by_text.assert_awaited_once()
    kwargs = vector_search.find_similar_chunks_by_text.await_args.kwargs
    assert kwargs["text"] == "what is the body?"
    assert kwargs["limit"] == 7
    assert kwargs["chunk_types"] == chunk_types
    assert kwargs["min_score"] == 0.6
    assert kwargs["parent_filters"].get("nous") == "body"


@pytest.mark.anyio
async def test_unavailable_when_vector_search_missing() -> None:
    """CORE tier (no vector search) returns an unavailable error, not a crash."""
    router = _router_with_vector_search(None)

    result = await router.retrieve_scoped_chunks(SearchRequest(query_text="hello"))

    assert result.is_error
    error = result.expect_error()
    assert "scoped_chunk_search" in str(error.message) or "scoped_chunk_search" in str(error)
