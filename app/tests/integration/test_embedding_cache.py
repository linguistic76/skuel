"""
Integration tests for embedding cache optimization.

Tests the cache-first strategy of get_or_create_embedding.

Created: January 2026
Updated: March 2026 — HuggingFace migration (1536→1024 dims, v1→v2)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    HuggingFaceEmbeddingsService,
)
from core.utils.result_simplified import Result

# Dimension for bge-large-en-v1.5
DIM = 1024


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver for testing."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def embeddings_service(mock_driver):
    """Create embeddings service with mock driver and mock HF client."""
    service = HuggingFaceEmbeddingsService(mock_driver)
    # Patch a mock client so create_embedding works without HF_API_TOKEN
    mock_client = MagicMock()
    service._client = mock_client
    return service


def _hf_embedding(embedding):
    """Configure mock HF client to return a specific embedding."""
    import numpy as np

    return np.array(embedding)


@pytest.mark.asyncio
async def test_cache_hit_avoids_api_call(embeddings_service, mock_driver):
    """Test that cache hit doesn't make API call to HuggingFace."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # Return current version (cache hit)
            return Result.ok(
                [
                    {
                        "embedding": [0.1] * DIM,
                        "version": EMBEDDING_VERSION,
                        "model": "BAAI/bge-large-en-v1.5",
                        "updated_at": "2026-03-12T12:00:00Z",
                    }
                ]
            )
        elif "RETURN n.embedding" in query:
            # Return cached embedding
            return Result.ok([{"embedding": [0.1] * DIM}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Ensure HF client was NOT called (cache hit should skip API)
    def fail_if_called(_text):
        raise AssertionError("HF API should not be called on cache hit")

    embeddings_service._client.feature_extraction = MagicMock(side_effect=fail_if_called)

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM


@pytest.mark.asyncio
async def test_cache_miss_makes_api_call(embeddings_service, mock_driver):
    """Test that cache miss generates new embedding."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # Return stale version (cache miss)
            return Result.ok(
                [
                    {
                        "embedding": [0.1] * DIM,
                        "version": "v1",  # Old version
                        "model": "text-embedding-3-small",
                        "updated_at": "2025-01-01T12:00:00Z",
                    }
                ]
            )
        elif "SET n.embedding" in query:
            # Store new embedding
            return Result.ok([{"uid": "ku.python"}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Mock HF client to return embedding
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.5] * DIM)
    )

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # SHOULD have called HF API (cache miss)
    embeddings_service._client.feature_extraction.assert_called_once()


@pytest.mark.asyncio
async def test_cache_miss_no_embedding(embeddings_service, mock_driver):
    """Test cache miss when node has no embedding."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # No embedding on node
            return Result.ok(
                [
                    {
                        "embedding": None,
                        "version": None,
                        "model": None,
                        "updated_at": None,
                    }
                ]
            )
        elif "SET n.embedding" in query:
            return Result.ok([{"uid": "ku.new"}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Mock HF client
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.3] * DIM)
    )

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.new", label="Entity", text="New knowledge unit"
    )

    assert result.is_ok
    embeddings_service._client.feature_extraction.assert_called_once()


@pytest.mark.asyncio
async def test_cache_stores_metadata_on_miss(embeddings_service, mock_driver):
    """Test that cache miss stores embedding with metadata."""
    # Use side_effect to return different results for each call in sequence
    mock_driver.execute_query.side_effect = [
        # First: check version - no embedding (get_embedding_metadata)
        Result.ok([{"embedding": None, "version": None, "model": None, "updated_at": None}]),
        # Second: store with metadata (store_embedding_with_metadata)
        Result.ok([{"uid": "ku.test"}]),
    ]

    # Mock HF client
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.4] * DIM)
    )

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test content"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # Should have made 2 DB calls (check version + store)
    assert mock_driver.execute_query.call_count == 2


@pytest.mark.asyncio
async def test_multiple_calls_use_cache(embeddings_service, mock_driver):
    """Test that multiple calls to same node use cache."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # Current version
            return Result.ok(
                [
                    {
                        "embedding": [0.2] * DIM,
                        "version": EMBEDDING_VERSION,
                        "model": "BAAI/bge-large-en-v1.5",
                        "updated_at": "2026-03-12T12:00:00Z",
                    }
                ]
            )
        elif "RETURN n.embedding" in query:
            return Result.ok([{"embedding": [0.2] * DIM}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Call 3 times
    for _ in range(3):
        result = await embeddings_service.get_or_create_embedding(
            uid="ku.cached", label="Entity", text="Cached content"
        )
        assert result.is_ok

    # Should have made 0 HF API calls (all cache hits)
    embeddings_service._client.feature_extraction.assert_not_called()


@pytest.mark.asyncio
async def test_different_nodes_independent_cache(embeddings_service, mock_driver):
    """Test that different nodes have independent cache entries."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # First node: cached, Second node: not cached
            if "python" in str(params.get("uid", "")):
                return Result.ok(
                    [
                        {
                            "embedding": [0.1] * DIM,
                            "version": EMBEDDING_VERSION,
                            "model": "BAAI/bge-large-en-v1.5",
                            "updated_at": "2026-03-12T12:00:00Z",
                        }
                    ]
                )
            else:
                return Result.ok(
                    [{"embedding": None, "version": None, "model": None, "updated_at": None}]
                )
        elif "RETURN n.embedding" in query:
            return Result.ok([{"embedding": [0.1] * DIM}])
        elif "SET n.embedding" in query:
            return Result.ok([{"uid": params.get("uid")}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Mock HF client
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.7] * DIM)
    )

    # First node: cache hit
    result1 = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python"
    )
    assert result1.is_ok

    # Second node: cache miss
    result2 = await embeddings_service.get_or_create_embedding(
        uid="ku.javascript", label="Entity", text="JavaScript"
    )
    assert result2.is_ok


@pytest.mark.asyncio
async def test_cache_failure_returns_embedding_anyway(embeddings_service, mock_driver):
    """Test that if storing to cache fails, we still return the embedding."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            return Result.ok(
                [{"embedding": None, "version": None, "model": None, "updated_at": None}]
            )
        elif "SET n.embedding" in query:
            # Simulate storage failure via Result.fail
            from core.utils.errors import Errors

            return Result.fail(
                Errors.database(operation="store_embedding", message="Database write failed")
            )
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Mock HF client
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.8] * DIM)
    )

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test"
    )

    # Should still return the embedding even though storage failed
    assert result.is_ok
    assert len(result.value) == DIM


@pytest.mark.asyncio
async def test_stale_version_regenerates(embeddings_service, mock_driver):
    """Test that stale versions trigger regeneration."""

    async def track_calls(query, params=None):
        if "embedding_version" in query:
            # Return old version
            return Result.ok(
                [
                    {
                        "embedding": [0.1] * DIM,
                        "version": "v1",  # Stale
                        "model": "text-embedding-3-small",
                        "updated_at": "2025-01-01T12:00:00Z",
                    }
                ]
            )
        elif "SET n.embedding" in query:
            return Result.ok([{"uid": "ku.stale"}])
        return Result.ok([])

    mock_driver.execute_query = track_calls

    # Mock HF client
    embeddings_service._client.feature_extraction = MagicMock(
        return_value=_hf_embedding([0.9] * DIM)
    )

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.stale", label="Entity", text="Stale content"
    )

    assert result.is_ok
    # Should have regenerated
    embeddings_service._client.feature_extraction.assert_called_once()
