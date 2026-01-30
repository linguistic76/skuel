"""
Unit tests for embedding versioning system.

Tests version tracking, metadata storage, and cache-first retrieval.

Created: January 2026
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.neo4j_genai_embeddings_service import (
    EMBEDDING_VERSION,
    Neo4jGenAIEmbeddingsService,
)


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver for testing."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def embeddings_service(mock_driver):
    """Create embeddings service with mock driver."""
    return Neo4jGenAIEmbeddingsService(mock_driver)


@pytest.mark.asyncio
async def test_embedding_version_constant():
    """Test that EMBEDDING_VERSION is defined."""
    assert EMBEDDING_VERSION is not None
    assert isinstance(EMBEDDING_VERSION, str)
    assert EMBEDDING_VERSION.startswith("v")


@pytest.mark.asyncio
async def test_store_embedding_with_metadata(embeddings_service, mock_driver):
    """Test storing embedding with version metadata."""
    # Mock successful update
    mock_driver.execute_query.return_value = [{"uid": "ku.python"}]

    embedding = [0.1] * 1536

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.python", label="Ku", embedding=embedding, text="Python programming"
    )

    assert result.is_ok

    # Verify query was called
    mock_driver.execute_query.assert_called_once()
    call_args = mock_driver.execute_query.call_args

    # Check parameters include version metadata
    params = call_args[0][1]
    assert params["uid"] == "ku.python"
    assert params["embedding"] == embedding
    assert params["version"] == EMBEDDING_VERSION
    assert params["model"] == "text-embedding-3-small"
    assert params["text"] == "Python programming"


@pytest.mark.asyncio
async def test_store_embedding_node_not_found(embeddings_service, mock_driver):
    """Test storing embedding when node doesn't exist."""
    # Mock no results (node not found)
    mock_driver.execute_query.return_value = []

    embedding = [0.1] * 1536

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.nonexistent", label="Ku", embedding=embedding
    )

    assert result.is_error
    assert "not_found" in str(result.error).lower()


@pytest.mark.asyncio
async def test_get_embedding_metadata(embeddings_service, mock_driver):
    """Test getting embedding metadata."""
    # Mock metadata response
    mock_driver.execute_query.return_value = [
        {
            "embedding": [0.1] * 1536,
            "version": "v1",
            "model": "text-embedding-3-small",
            "updated_at": "2026-01-29T12:00:00Z",
        }
    ]

    result = await embeddings_service.get_embedding_metadata(uid="ku.python", label="Ku")

    assert result.is_ok
    metadata = result.value

    assert metadata["has_embedding"] is True
    assert metadata["version"] == "v1"
    assert metadata["model"] == "text-embedding-3-small"
    assert metadata["updated_at"] == "2026-01-29T12:00:00Z"
    assert metadata["dimension"] == 1536


@pytest.mark.asyncio
async def test_get_embedding_metadata_no_embedding(embeddings_service, mock_driver):
    """Test getting metadata when node has no embedding."""
    # Mock node with no embedding
    mock_driver.execute_query.return_value = [
        {"embedding": None, "version": None, "model": None, "updated_at": None}
    ]

    result = await embeddings_service.get_embedding_metadata(uid="ku.test", label="Ku")

    assert result.is_ok
    metadata = result.value

    assert metadata["has_embedding"] is False
    assert metadata["version"] is None
    assert metadata["model"] is None
    assert metadata["dimension"] is None


@pytest.mark.asyncio
async def test_check_version_compatibility_current(embeddings_service, mock_driver):
    """Test version compatibility check for current version."""
    # Mock current version
    mock_driver.execute_query.return_value = [
        {
            "embedding": [0.1] * 1536,
            "version": EMBEDDING_VERSION,
            "model": "text-embedding-3-small",
            "updated_at": "2026-01-29T12:00:00Z",
        }
    ]

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Ku")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is True
    assert compat["node_version"] == EMBEDDING_VERSION
    assert compat["current_version"] == EMBEDDING_VERSION
    assert compat["needs_update"] is False
    assert compat["has_embedding"] is True


@pytest.mark.asyncio
async def test_check_version_compatibility_stale(embeddings_service, mock_driver):
    """Test version compatibility check for stale version."""
    # Mock old version
    mock_driver.execute_query.return_value = [
        {
            "embedding": [0.1] * 1536,
            "version": "v0",  # Old version
            "model": "text-embedding-ada-002",
            "updated_at": "2025-01-01T12:00:00Z",
        }
    ]

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Ku")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] == "v0"
    assert compat["current_version"] == EMBEDDING_VERSION
    assert compat["needs_update"] is True  # Has embedding but wrong version
    assert compat["has_embedding"] is True


@pytest.mark.asyncio
async def test_check_version_compatibility_no_version(embeddings_service, mock_driver):
    """Test version compatibility when node has embedding but no version."""
    # Mock embedding without version metadata
    mock_driver.execute_query.return_value = [
        {"embedding": [0.1] * 1536, "version": None, "model": None, "updated_at": None}
    ]

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Ku")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] is None
    assert compat["needs_update"] is True  # Has embedding but no version


@pytest.mark.asyncio
async def test_get_or_create_embedding_returns_embedding(embeddings_service, mock_driver):
    """Test get_or_create_embedding basic functionality.

    Note: Full integration test of caching logic is in integration tests.
    This unit test just verifies the method structure.
    """

    # Mock all possible queries to return valid responses
    async def mock_query(query, params=None):
        # Metadata query
        if "embedding_version" in query and "RETURN" in query:
            return [
                {
                    "embedding": None,
                    "version": None,
                    "model": None,
                    "updated_at": None,
                }
            ]
        # Create embedding (GenAI)
        elif "ai.text.embed" in query:
            return [{"embedding": [0.1] * 1536}]
        # Store embedding
        elif "SET n.embedding" in query:
            return [{"uid": "ku.python"}]
        return []

    mock_driver.execute_query = mock_query
    embeddings_service._plugin_available = True

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python programming"
    )

    # Just verify it returns a valid embedding
    assert result.is_ok
    assert len(result.value) == 1536


@pytest.mark.asyncio
async def test_get_or_create_embedding_cache_miss(embeddings_service, mock_driver):
    """Test cache miss - generates new embedding."""
    # Mock stale version (needs regeneration)
    call_count = [0]

    async def mock_query(query, params):
        call_count[0] += 1

        # First call: check compatibility (stale version)
        if call_count[0] == 1:
            return [
                {
                    "embedding": [0.1] * 1536,
                    "version": "v0",  # Old version
                    "model": "old-model",
                    "updated_at": "2025-01-01T12:00:00Z",
                }
            ]
        # Second call: create new embedding (GenAI plugin)
        elif "ai.text.embed" in query:
            return [{"embedding": [0.2] * 1536}]
        # Third call: store with metadata
        else:
            return [{"uid": "ku.python"}]

    mock_driver.execute_query = mock_query

    # Mock plugin availability
    embeddings_service._plugin_available = True

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python programming"
    )

    assert result.is_ok
    embedding = result.value
    assert len(embedding) == 1536
    assert embedding[0] == 0.2  # New embedding, not cached


@pytest.mark.asyncio
async def test_get_or_create_embedding_no_existing(embeddings_service, mock_driver):
    """Test when node has no existing embedding."""
    call_count = [0]

    async def mock_query(query, params):
        call_count[0] += 1

        # First call: check compatibility (no embedding)
        if call_count[0] == 1:
            return [{"embedding": None, "version": None, "model": None, "updated_at": None}]
        # Second call: create embedding
        elif "ai.text.embed" in query:
            return [{"embedding": [0.3] * 1536}]
        # Third call: store with metadata
        else:
            return [{"uid": "ku.python"}]

    mock_driver.execute_query = mock_query
    embeddings_service._plugin_available = True

    result = await embeddings_service.get_or_create_embedding(
        uid="ku.python", label="Ku", text="Python programming"
    )

    assert result.is_ok
    assert len(result.value) == 1536
