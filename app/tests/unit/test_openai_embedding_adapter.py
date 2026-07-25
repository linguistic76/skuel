"""
Unit tests for OpenAIEmbeddingAdapter.

Covers the W1 inference-client boundary: response parsing, the API
``dimensions`` request parameter (ADR-068: 1024 via Matryoshka truncation),
error → Result mapping, fail-fast on a missing API key, and the
model/dimension/max_input_chars port properties. The vendor SDK call itself
is mocked — no network access.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.external.embeddings import OpenAIEmbeddingAdapter

DIM = 1024


def _response(vector: list[float]) -> SimpleNamespace:
    """Shape-compatible stand-in for openai's CreateEmbeddingResponse."""
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector)])


def _adapter() -> OpenAIEmbeddingAdapter:
    """Build an adapter with a mocked SDK client (no network)."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    adapter._client = MagicMock()
    return adapter


def test_fail_fast_without_api_key():
    """Empty API key raises immediately (fail-fast at the wiring layer)."""
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingAdapter(api_key="")


def test_port_properties():
    """model/dimension/max_input_chars are exposed for the consuming service."""
    adapter = OpenAIEmbeddingAdapter(api_key="test-key")
    assert adapter.model == "text-embedding-3-small"
    assert adapter.dimension == DIM
    assert adapter.max_input_chars == 24000  # ~6k tokens, under the 8191-token model cap


@pytest.mark.asyncio
async def test_embed_returns_vector():
    adapter = _adapter()
    adapter._client.embeddings.create = AsyncMock(return_value=_response([0.1] * DIM))

    result = await adapter.embed("hello")

    assert result.is_ok
    assert result.value == [0.1] * DIM


@pytest.mark.asyncio
async def test_embed_requests_configured_dimensions():
    """The API call carries the `dimensions` param — the index-compat contract
    (ADR-068: 1024 keeps Neo4j vector indexes aligned with the BGE swap)."""
    adapter = _adapter()
    adapter._client.embeddings.create = AsyncMock(return_value=_response([0.2] * DIM))

    await adapter.embed("hello")

    kwargs = adapter._client.embeddings.create.await_args.kwargs
    assert kwargs["dimensions"] == DIM
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["input"] == "hello"


@pytest.mark.asyncio
async def test_embed_maps_exception_to_integration_error(monkeypatch):
    """A raising client → Result.fail with an OpenAI integration error.

    asyncio.sleep is patched so tenacity's retry backoff doesn't slow the test.
    """
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    adapter = _adapter()
    adapter._client.embeddings.create = AsyncMock(side_effect=ConnectionError("boom"))

    result = await adapter.embed("hello")

    assert result.is_error
    error = result.expect_error()
    assert "openai" in str(error).lower() or "embedding generation failed" in str(error).lower()
    # Exhausts retries (3 attempts) before failing.
    assert adapter._client.embeddings.create.await_count == 3
