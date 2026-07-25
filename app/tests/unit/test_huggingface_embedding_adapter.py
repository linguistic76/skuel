"""
Unit tests for HuggingFaceEmbeddingAdapter.

Covers the W1 inference-client boundary: response-shape parsing (numpy /
nested-list / flat-list), error → Result mapping, fail-fast on a missing API
key, and the model/dimension port properties. The vendor SDK call itself is
mocked — no network access.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from adapters.external.embeddings import HuggingFaceEmbeddingAdapter

DIM = 1024


def _adapter() -> HuggingFaceEmbeddingAdapter:
    """Build an adapter with a mocked inference client (no network)."""
    adapter = HuggingFaceEmbeddingAdapter(api_key="test-token")
    adapter._client = MagicMock()
    return adapter


def test_fail_fast_without_api_key():
    """Empty API key raises immediately (fail-fast at the wiring layer)."""
    with pytest.raises(ValueError, match="HF_API_TOKEN"):
        HuggingFaceEmbeddingAdapter(api_key="")


def test_model_and_dimension_properties():
    """model/dimension/max_input_chars are exposed for the consuming service."""
    adapter = HuggingFaceEmbeddingAdapter(api_key="test-token")
    assert adapter.model == "BAAI/bge-m3"
    assert adapter.dimension == DIM
    assert adapter.max_input_chars == 20000  # ~6.7k tokens, under the 8192-token M3 window


@pytest.mark.asyncio
async def test_embed_parses_1d_ndarray():
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(return_value=np.array([0.1] * DIM))

    result = await adapter.embed("hello")

    assert result.is_ok
    assert result.value == pytest.approx([0.1] * DIM)
    assert isinstance(result.value, list)


@pytest.mark.asyncio
async def test_embed_parses_2d_ndarray():
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(return_value=np.array([[0.2] * DIM]))

    result = await adapter.embed("hello")

    assert result.is_ok
    assert result.value == pytest.approx([0.2] * DIM)


@pytest.mark.asyncio
async def test_embed_parses_nested_list():
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(return_value=[[0.3] * DIM])

    result = await adapter.embed("hello")

    assert result.is_ok
    assert result.value == [0.3] * DIM


@pytest.mark.asyncio
async def test_embed_parses_flat_list():
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(return_value=[0.4] * DIM)

    result = await adapter.embed("hello")

    assert result.is_ok
    assert result.value == [0.4] * DIM


@pytest.mark.asyncio
async def test_embed_maps_exception_to_integration_error(monkeypatch):
    """A raising client → Result.fail with a HuggingFace integration error.

    asyncio.sleep is patched so tenacity's retry backoff doesn't slow the test.
    """
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(side_effect=ConnectionError("boom"))

    result = await adapter.embed("hello")

    assert result.is_error
    error = result.expect_error()
    assert (
        "huggingface" in str(error).lower() or "embedding generation failed" in str(error).lower()
    )
    # Exhausts retries (3 attempts) before failing.
    assert adapter._client.feature_extraction.await_count == 3


@pytest.mark.asyncio
async def test_embed_maps_unexpected_response_type(monkeypatch):
    """An unexpected response type raises TypeError → Result.fail after retries."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    adapter = _adapter()
    adapter._client.feature_extraction = AsyncMock(return_value={"unexpected": "dict"})

    result = await adapter.embed("hello")

    assert result.is_error
