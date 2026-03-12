"""
Unit tests for embedding versioning system.

Tests version tracking, metadata storage, and cache-first retrieval.

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
    """Create embeddings service with mock driver."""
    return HuggingFaceEmbeddingsService(mock_driver)


@pytest.mark.asyncio
async def test_embedding_version_constant():
    """Test that EMBEDDING_VERSION is defined."""
    assert EMBEDDING_VERSION is not None
    assert isinstance(EMBEDDING_VERSION, str)
    assert EMBEDDING_VERSION.startswith("v")
    assert EMBEDDING_VERSION == "v2"


@pytest.mark.asyncio
async def test_store_embedding_with_metadata(embeddings_service, mock_driver):
    """Test storing embedding with version metadata."""
    # Mock successful update
    mock_driver.execute_query.return_value = Result.ok([{"uid": "ku.python"}])

    embedding = [0.1] * DIM

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.python", label="Entity", embedding=embedding, text="Python programming"
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
    assert params["model"] == "BAAI/bge-large-en-v1.5"
    assert params["text"] == "Python programming"


@pytest.mark.asyncio
async def test_store_embedding_node_not_found(embeddings_service, mock_driver):
    """Test storing embedding when node doesn't exist."""
    # Mock no results (node not found)
    mock_driver.execute_query.return_value = Result.ok([])

    embedding = [0.1] * DIM

    result = await embeddings_service.store_embedding_with_metadata(
        uid="ku.nonexistent", label="Entity", embedding=embedding
    )

    assert result.is_error
    assert "not_found" in str(result.error).lower()


@pytest.mark.asyncio
async def test_get_embedding_metadata(embeddings_service, mock_driver):
    """Test getting embedding metadata."""
    # Mock metadata response
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v2",
                "model": "BAAI/bge-large-en-v1.5",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.get_embedding_metadata(uid="ku.python", label="Entity")

    assert result.is_ok
    metadata = result.value

    assert metadata["has_embedding"] is True
    assert metadata["version"] == "v2"
    assert metadata["model"] == "BAAI/bge-large-en-v1.5"
    assert metadata["updated_at"] == "2026-03-12T12:00:00Z"
    assert metadata["dimension"] == DIM


@pytest.mark.asyncio
async def test_get_embedding_metadata_no_embedding(embeddings_service, mock_driver):
    """Test getting metadata when node has no embedding."""
    # Mock node with no embedding
    mock_driver.execute_query.return_value = Result.ok(
        [{"embedding": None, "version": None, "model": None, "updated_at": None}]
    )

    result = await embeddings_service.get_embedding_metadata(uid="ku.test", label="Entity")

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
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": EMBEDDING_VERSION,
                "model": "BAAI/bge-large-en-v1.5",
                "updated_at": "2026-03-12T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

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
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "embedding": [0.1] * DIM,
                "version": "v1",  # Old version
                "model": "text-embedding-3-small",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        ]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] == "v1"
    assert compat["current_version"] == EMBEDDING_VERSION
    assert compat["needs_update"] is True  # Has embedding but wrong version
    assert compat["has_embedding"] is True


@pytest.mark.asyncio
async def test_check_version_compatibility_no_version(embeddings_service, mock_driver):
    """Test version compatibility when node has embedding but no version."""
    # Mock embedding without version metadata
    mock_driver.execute_query.return_value = Result.ok(
        [{"embedding": [0.1] * DIM, "version": None, "model": None, "updated_at": None}]
    )

    result = await embeddings_service.check_version_compatibility(uid="ku.python", label="Entity")

    assert result.is_ok
    compat = result.value

    assert compat["is_current"] is False
    assert compat["node_version"] is None
    assert compat["needs_update"] is True  # Has embedding but no version
