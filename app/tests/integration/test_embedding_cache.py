"""
Integration tests for embedding cache optimization.

Tests the cache-first strategy of get_or_create_embedding.

Created: January 2026
Updated: March 2026 — HuggingFace migration (1536→1024 dims, v1→v2)
Updated: April 2026 — EmbeddingsBackend migration (executor → typed backend)
Updated: July 2026 — cache decision folded onto verify_fresh_embeddings
    (ADR-074 §8): fresh = version current + text-hash match, so a
    version-current node whose text changed regenerates.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.embeddings_service import (
    EMBEDDING_VERSION,
    EmbeddingsService,
)
from core.utils.embedding_text_builder import hash_embedding_text
from core.utils.result_simplified import Errors, Result

# Dimension for bge-m3
DIM = 1024


@pytest.fixture
def mock_backend():
    """Mock EmbeddingsBackend for testing."""
    backend = MagicMock()
    backend.store_embedding_metadata = AsyncMock()
    backend.get_cached_embedding = AsyncMock()
    # The cache decision reads freshness (version + text hash) and touches
    # embedding_updated_at on verified-fresh nodes.
    backend.get_embedding_freshness = AsyncMock(return_value=Result.ok([]))
    backend.touch_embedding_updated_at = AsyncMock(return_value=Result.ok([{"touched": 1}]))
    return backend


@pytest.fixture
def embeddings_service(mock_backend):
    """Create embeddings service with mock backend and mock inference client.

    The inference client (EmbeddingClientOperations) is injected; tests drive
    its ``embed`` method directly. The vendor SDK now lives in the adapter, so
    there is no HF_API_TOKEN / _client to set up here.
    """
    mock_client = MagicMock()
    mock_client.model = "BAAI/bge-m3"
    mock_client.dimension = DIM
    mock_client.max_input_chars = 20000
    mock_client.embed = AsyncMock()
    return EmbeddingsService(mock_backend, embedding_client=mock_client)


def _embed_ok(embedding):
    """Wrap an embedding as the inference client's ``embed`` Result.ok return."""
    return Result.ok(list(embedding))


def _freshness_row(uid, text, *, has_embedding=True, version=EMBEDDING_VERSION, text_hash=None):
    """One get_embedding_freshness row; hash defaults to the given text's hash."""
    return {
        "uid": uid,
        "has_embedding": has_embedding,
        "version": version,
        "text_hash": hash_embedding_text(text) if text_hash is None else text_hash,
    }


@pytest.mark.asyncio
async def test_cache_hit_avoids_api_call(embeddings_service, mock_backend):
    """Test that cache hit (version + text hash match) makes no API call."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.python", "Python programming")]
    )
    # get_cached_embedding returns the embedding
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.1] * DIM}])

    # Ensure the inference client was NOT called (cache hit should skip API)
    async def fail_if_called(_text):
        raise AssertionError("Inference API should not be called on cache hit")

    embeddings_service._embedding_client.embed = AsyncMock(side_effect=fail_if_called)

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM
    # Verified-fresh node gets its embedding_updated_at touched
    mock_backend.touch_embedding_updated_at.assert_awaited_once_with(["ku.python"])


@pytest.mark.asyncio
async def test_cache_miss_makes_api_call(embeddings_service, mock_backend):
    """Test that a stale version triggers regeneration."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.python", "Python programming", version="v1")]
    )
    # store_embedding_metadata succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.python"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.5] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # SHOULD have called the inference API (cache miss)
    embeddings_service._embedding_client.embed.assert_called_once()


@pytest.mark.asyncio
async def test_changed_text_regenerates_despite_current_version(embeddings_service, mock_backend):
    """Version-current node whose TEXT changed regenerates (ADR-074 §8).

    The pre-fold recipe checked version only and would have returned the
    stale vector here — the exact bug the verify_fresh_embeddings fold fixes.
    """
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.python", "OLD text the vector was built from")]
    )
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.python"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.6] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Entity", text="NEW text after an edit"
    )

    assert result.is_ok
    # Regenerated — the stored vector no longer matches the current text
    embeddings_service._embedding_client.embed.assert_called_once()
    # And the fresh store carries the NEW text's hash
    store_kwargs = mock_backend.store_embedding_metadata.await_args.kwargs
    assert store_kwargs["text_hash"] == hash_embedding_text("NEW text after an edit")
    # Nothing was verified fresh, so nothing gets touched
    mock_backend.touch_embedding_updated_at.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_miss_no_embedding(embeddings_service, mock_backend):
    """Test cache miss when node has no embedding."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.new", "New knowledge unit", has_embedding=False, version=None)]
    )
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.new"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.3] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.new", label="Entity", text="New knowledge unit"
    )

    assert result.is_ok
    embeddings_service._embedding_client.embed.assert_called_once()


@pytest.mark.asyncio
async def test_cache_stores_metadata_on_miss(embeddings_service, mock_backend):
    """Test that cache miss stores embedding with metadata."""
    # Node not in the freshness read at all (never embedded)
    mock_backend.get_embedding_freshness.return_value = Result.ok([])
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.test"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.4] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test content"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == DIM

    # Should have checked freshness + stored with metadata
    mock_backend.get_embedding_freshness.assert_awaited_once()
    mock_backend.store_embedding_metadata.assert_awaited_once()


@pytest.mark.asyncio
async def test_multiple_calls_use_cache(embeddings_service, mock_backend):
    """Test that multiple calls to same node use cache."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.cached", "Cached content")]
    )
    # get_cached_embedding returns embedding
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.2] * DIM}])

    # Call 3 times
    for _ in range(3):
        result = await embeddings_service.get_or_create_embedding(
            uid="ku.cached", label="Entity", text="Cached content"
        )
        assert result.is_ok

    # Should have made 0 inference API calls (all cache hits)
    embeddings_service._embedding_client.embed.assert_not_called()


@pytest.mark.asyncio
async def test_different_nodes_independent_cache(embeddings_service, mock_backend):
    """Test that different nodes have independent cache entries."""

    def freshness_side_effect(uids):
        if "ku.python" in uids:
            # Cached (fresh for its text)
            return Result.ok([_freshness_row("ku.python", "Python")])
        # Not cached
        return Result.ok([])

    mock_backend.get_embedding_freshness = AsyncMock(side_effect=freshness_side_effect)
    mock_backend.get_cached_embedding.return_value = Result.ok([{"embedding": [0.1] * DIM}])
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.javascript"}])

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
    # No stored embedding
    mock_backend.get_embedding_freshness.return_value = Result.ok([])
    # store fails
    mock_backend.store_embedding_metadata.return_value = Result.fail(
        Errors.database(operation="store_embedding", message="Database write failed")
    )

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.8] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test"
    )

    # Should still return the embedding even though storage failed
    assert result.is_ok
    assert len(result.value) == DIM


@pytest.mark.asyncio
async def test_freshness_read_failure_fails_open_and_regenerates(embeddings_service, mock_backend):
    """A freshness-read error regenerates instead of erroring (fail OPEN)."""
    mock_backend.get_embedding_freshness.return_value = Result.fail(
        Errors.database(operation="get_embedding_freshness", message="read failed")
    )
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.test"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.9] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Entity", text="Test"
    )

    assert result.is_ok
    embeddings_service._embedding_client.embed.assert_called_once()


@pytest.mark.asyncio
async def test_stale_version_regenerates(embeddings_service, mock_backend):
    """Test that stale versions trigger regeneration even when text matches."""
    mock_backend.get_embedding_freshness.return_value = Result.ok(
        [_freshness_row("ku.stale", "Stale content", version="v1")]
    )
    # store succeeds
    mock_backend.store_embedding_metadata.return_value = Result.ok([{"uid": "ku.stale"}])

    embeddings_service._embedding_client.embed = AsyncMock(return_value=_embed_ok([0.9] * DIM))

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.stale", label="Entity", text="Stale content"
    )

    assert result.is_ok
    # Should have regenerated (version outranks hash)
    embeddings_service._embedding_client.embed.assert_called_once()
