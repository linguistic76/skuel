"""
Integration tests for embedding cache optimization.

Tests the cache-first strategy of get_or_create_embedding.

Created: January 2026
Updated: March 2026 — HuggingFace migration (1536→1024 dims, v1→v2)
Updated: April 2026 — EmbeddingsBackend migration (executor → typed backend)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    HuggingFaceEmbeddingsService,
)
from core.utils.result_simplified import Errors, Result

# Dimension for bge-large-en-v1.5
DIM = 1024


@pytest.fixture
def mock_backend():
    """Mock EmbeddingsBackend for testing."""
    backend = MagicMock()
    backend.store_embedding_metadata = AsyncMock()
    backend.get_embedding_metadata = AsyncMock()
    backend.get_cached_embedding = AsyncMock()
    return backend


@pytest.fixture
def embeddings_service(mock_backend):
    """Create embeddings service with mock backend and mock inference client.

    The inference client (EmbeddingClientOperations) is injected; tests drive
    its ``embed`` method directly. The vendor SDK now lives in the adapter, so
    there is no HF_API_TOKEN / _client to set up here.
    """
    mock_client = MagicMock()
    mock_client.model = "BAAI/bge-large-en-v1.5"
    mock_client.dimension = DIM
    mock_client.embed = AsyncMock()
    return HuggingFaceEmbeddingsService(mock_backend, embedding_client=mock_client)


def _embed_ok(embedding):
    """Wrap an embedding as the inference client's ``embed`` Result.ok return."""
    return Result.ok(list(embedding))


@pytest.mark.asyncio
async def test_cache_hit_avoids_api_call(embeddings_service, mock_backend):
    """Test that cache hit doesn't make API call to HuggingFace."""
    # get_embedding_metadata returns current version (cache hit)
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": EMBEDDING_VERSION,
                "model": "BAAI/bge-large-en-v1.5",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )
    # get_cached_embedding returns the embedding
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.1] * DIM}])

    # Ensure HF client was NOT called (cache hit should skip API)
    async def fail_if_called(_text):
        raise AssertionError("HF API should not be called on cache hit")

    embeddings_service._embedding_client.embed = AsyncMock(side_effect=fail_if_called)

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM


@pytest.mark.asyncio
async def test_cache_miss_makes_api_call(embeddings_service, mock_backend):
    """Test that cache miss generates new embedding."""
    # get_embedding_metadata returns stale version (cache miss)
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v1",  # Old version
                "model": "text-embedding-3-small",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        ]
    )
    # store_embedding_metadata succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.python"}])

    # Mock HF client to return embedding
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.5] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # SHOULD have called HF API (cache miss)
    embeddings_service._embedding_client.embed.assert_called_once()


@pytest.mark.asyncio
async def test_cache_miss_no_embedding(embeddings_service, mock_backend):
    """Test cache miss when node has no embedding."""
    # get_embedding_metadata returns no embedding
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [{"embedding": None, "version": None, "model": None, "updated_at": None}]
    )
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.new"}])

    # Mock HF client
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.3] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.new", label="Entity", text="New knowledge unit"
    )

    assert result.is_ok
    embeddings_service._embedding_client.embed.assert_called_once()


@pytest.mark.asyncio
async def test_cache_stores_metadata_on_miss(embeddings_service, mock_backend):
    """Test that cache miss stores embedding with metadata."""
    # get_embedding_metadata: no embedding
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [{"embedding": None, "version": None, "model": None, "updated_at": None}]
    )
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.test"}])

    # Mock HF client
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.4] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test content"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # Should have called get_embedding_metadata (check version) + store_embedding_metadata
    mock_backend.get_embedding_metadata.assert_called_once()
    mock_backend.store_embedding_metadata.assert_called_once()


@pytest.mark.asyncio
async def test_multiple_calls_use_cache(embeddings_service, mock_backend):
    """Test that multiple calls to same node use cache."""
    # get_embedding_metadata returns current version
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.2] * DIM,
                "version": EMBEDDING_VERSION,
                "model": "BAAI/bge-large-en-v1.5",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )
    # get_cached_embedding returns embedding
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.2] * DIM}])

    # Call 3 times
    for _ in range(3):
        result = await embeddings_service.get_or_create_embedding(
            uid="ku.cached", label="Entity", text="Cached content"
        )
        assert result.is_ok

    # Should have made 0 HF API calls (all cache hits)
    embeddings_service._embedding_client.embed.assert_not_called()


@pytest.mark.asyncio
async def test_different_nodes_independent_cache(embeddings_service, mock_backend):
    """Test that different nodes have independent cache entries."""

    def metadata_side_effect(label, uid):
        if "python" in uid:
            # Cached
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
            # Not cached
            return Result.ok(
                [{"embedding": None, "version": None, "model": None, "updated_at": None}]
            )

    mock_backend.get_embedding_metadata = AsyncMock(side_effect=metadata_side_effect)
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.1] * DIM}])
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.javascript"}])

    # Mock HF client
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.7] * DIM))

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
async def test_cache_failure_returns_embedding_anyway(embeddings_service, mock_backend):
    """Test that if storing to cache fails, we still return the embedding."""
    # get_embedding_metadata: no embedding
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [{"embedding": None, "version": None, "model": None, "updated_at": None}]
    )
    # store fails
    mock_backend.store_embedding_metadata.return_value = Result.fail(
        Errors.database(operation="store_embedding", message="Database write failed")
    )

    # Mock HF client
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.8] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test"
    )

    # Should still return the embedding even though storage failed
    assert result.is_ok
    assert len(result.value) == DIM


@pytest.mark.asyncio
async def test_stale_version_regenerates(embeddings_service, mock_backend):
    """Test that stale versions trigger regeneration."""
    # get_embedding_metadata returns old version
    mock_backend.get_embedding_metadata.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v1",  # Stale
                "model": "text-embedding-3-small",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        ]
    )
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.stale"}])

    # Mock HF client
    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.9] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.stale", label="Entity", text="Stale content"
    )

    assert result.is_ok
    # Should have regenerated
    embeddings_service._embedding_client.embed.assert_called_once()
