"""
Integration tests for embedding cache optimization.

Tests the cache-first strategy of get_or_create_embedding.

Created: January 2026
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.services.neo4j_genai_embeddings_service import (
    EMBEDDING_VERSION,
    Neo4jGenAIEmbeddingsService,
)
from core.utils.result_simplified import Result


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver for testing."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def embeddings_service(mock_driver):
    """Create embeddings service with mock driver."""
    service = Neo4jGenAIEmbeddingsService(mock_driver)
    service._plugin_available = True  # Mock plugin as available
    return service


@pytest.mark.asyncio
async def test_cache_hit_avoids_api_call(embeddings_service, mock_driver):
    """Test that cache hit doesn't make API call to GenAI."""
    api_calls = []

    async def track_calls(query, params=None):
        # Track which queries are called
        if "ai.text.embed" in query:
            api_calls.append("genai_api")
            return [{"embedding": [0.5] * 1536}]
        elif "embedding_version" in query:
            # Return current version (cache hit)
            return [
                {
                    "embedding": [0.1] * 1536,
                    "version": EMBEDDING_VERSION,
                    "model": "text-embedding-3-small",
                    "updated_at": "2026-01-29T12:00:00Z",
                }
            ]
        elif "RETURN n.embedding" in query:
            # Return cached embedding
            return [{"embedding": [0.1] * 1536}]
        return []

    mock_driver.execute_query = track_calls

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == 1536

    # Should NOT have called GenAI API (cache hit)
    assert "genai_api" not in api_calls


@pytest.mark.asyncio
async def test_cache_miss_makes_api_call(embeddings_service, mock_driver):
    """Test that cache miss generates new embedding."""
    api_calls = []

    async def track_calls(query, params=None):
        if "ai.text.embed" in query:
            api_calls.append("genai_api")
            return [{"embedding": [0.5] * 1536}]
        elif "embedding_version" in query:
            # Return stale version (cache miss)
            return [
                {
                    "embedding": [0.1] * 1536,
                    "version": "v0",  # Old version
                    "model": "old-model",
                    "updated_at": "2025-01-01T12:00:00Z",
                }
            ]
        elif "SET n.embedding" in query:
            # Store new embedding
            return [{"uid": "ku.python"}]
        return []

    mock_driver.execute_query = track_calls

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python programming"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == 1536

    # SHOULD have called GenAI API (cache miss)
    assert "genai_api" in api_calls


@pytest.mark.asyncio
async def test_cache_miss_no_embedding(embeddings_service, mock_driver):
    """Test cache miss when node has no embedding."""
    api_calls = []

    async def track_calls(query, params=None):
        if "ai.text.embed" in query:
            api_calls.append("genai_api")
            return [{"embedding": [0.3] * 1536}]
        elif "embedding_version" in query:
            # No embedding on node
            return [
                {
                    "embedding": None,
                    "version": None,
                    "model": None,
                    "updated_at": None,
                }
            ]
        elif "SET n.embedding" in query:
            return [{"uid": "ku.new"}]
        return []

    mock_driver.execute_query = track_calls

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.new", label="Ku", text="New knowledge unit"
    )

    assert result.is_ok
    assert "genai_api" in api_calls


@pytest.mark.asyncio
async def test_cache_stores_metadata_on_miss(embeddings_service, mock_driver):
    """Test that cache miss stores embedding with metadata."""
    # Use side_effect to return different results for each call in sequence
    mock_driver.execute_query.side_effect = [
        # First: check version - no embedding
        [{"embedding": None, "version": None, "model": None, "updated_at": None}],
        # Second: generate embedding via GenAI
        [{"embedding": [0.4] * 1536}],
        # Third: store with metadata
        [{"uid": "ku.test"}],
    ]

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Ku", text="Test content"
    )

    # Should succeed
    assert result.is_ok
    assert len(result.value) == 1536

    # Should have made 3 calls
    assert mock_driver.execute_query.call_count == 3


@pytest.mark.asyncio
async def test_multiple_calls_use_cache(embeddings_service, mock_driver):
    """Test that multiple calls to same node use cache."""
    api_calls = []

    async def track_calls(query, params=None):
        if "ai.text.embed" in query:
            api_calls.append("genai_api")
            return [{"embedding": [0.6] * 1536}]
        elif "embedding_version" in query:
            # Current version
            return [
                {
                    "embedding": [0.2] * 1536,
                    "version": EMBEDDING_VERSION,
                    "model": "text-embedding-3-small",
                    "updated_at": "2026-01-29T12:00:00Z",
                }
            ]
        elif "RETURN n.embedding" in query:
            return [{"embedding": [0.2] * 1536}]
        return []

    mock_driver.execute_query = track_calls

    # Call 3 times
    for _ in range(3):
        result = await embeddings_service.get_or_create_embedding(
            uid="ku.cached", label="Ku", text="Cached content"
        )
        assert result.is_ok

    # Should have made 0 API calls (all cache hits)
    assert len(api_calls) == 0


@pytest.mark.asyncio
async def test_different_nodes_independent_cache(embeddings_service, mock_driver):
    """Test that different nodes have independent cache entries."""
    call_count = [0]

    async def track_calls(query, params=None):
        call_count[0] += 1

        if "ai.text.embed" in query:
            return [{"embedding": [0.7] * 1536}]
        elif "embedding_version" in query:
            # First node: cached, Second node: not cached
            if "python" in str(params.get("uid", "")):
                return [
                    {
                        "embedding": [0.1] * 1536,
                        "version": EMBEDDING_VERSION,
                        "model": "text-embedding-3-small",
                        "updated_at": "2026-01-29T12:00:00Z",
                    }
                ]
            else:
                return [{"embedding": None, "version": None, "model": None, "updated_at": None}]
        elif "RETURN n.embedding" in query:
            return [{"embedding": [0.1] * 1536}]
        elif "SET n.embedding" in query:
            return [{"uid": params.get("uid")}]
        return []

    mock_driver.execute_query = track_calls

    # First node: cache hit
    result1 = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python"
    )
    assert result1.is_ok

    # Second node: cache miss
    result2 = await embeddings_service.get_or_create_embedding(
        uid="ku.javascript", label="Ku", text="JavaScript"
    )
    assert result2.is_ok


@pytest.mark.asyncio
async def test_cache_failure_returns_embedding_anyway(embeddings_service, mock_driver):
    """Test that if storing to cache fails, we still return the embedding."""

    async def track_calls(query, params=None):
        if "ai.text.embed" in query:
            return [{"embedding": [0.8] * 1536}]
        elif "embedding_version" in query:
            return [{"embedding": None, "version": None, "model": None, "updated_at": None}]
        elif "SET n.embedding" in query:
            # Simulate storage failure
            raise Exception("Database write failed")
        return []

    mock_driver.execute_query = track_calls

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.test", label="Ku", text="Test"
    )

    # Should still return the embedding even though storage failed
    assert result.is_ok
    assert len(result.value) == 1536


@pytest.mark.asyncio
async def test_stale_version_regenerates(embeddings_service, mock_driver):
    """Test that stale versions trigger regeneration."""
    api_calls = []

    async def track_calls(query, params=None):
        if "ai.text.embed" in query:
            api_calls.append("regenerate")
            return [{"embedding": [0.9] * 1536}]
        elif "embedding_version" in query:
            # Return old version
            return [
                {
                    "embedding": [0.1] * 1536,
                    "version": "v0",  # Stale
                    "model": "old-model",
                    "updated_at": "2025-01-01T12:00:00Z",
                }
            ]
        elif "SET n.embedding" in query:
            return [{"uid": "ku.stale"}]
        return []

    mock_driver.execute_query = track_calls

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.stale", label="Ku", text="Stale content"
    )

    assert result.is_ok
    # Should have regenerated
    assert "regenerate" in api_calls
