"""
Integration tests for search metrics tracking.

Tests the metrics collection wrappers in Neo4jVectorSearchService.

Created: January 2026
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver for testing."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def mock_embeddings_service():
    """Mock embeddings service that returns deterministic embeddings."""
    from core.utils.result_simplified import Result

    service = MagicMock()

    async def create_embedding(text, metadata=None):
        embedding = [0.001 * i for i in range(1, 1537)]
        embedding[0] = len(text) * 0.001
        return Result.ok(embedding)

    service.create_embedding = create_embedding
    return service


@pytest.fixture
def vector_search_service(mock_driver, mock_embeddings_service):
    """Create vector search service with mocks."""
    config = VectorSearchConfig()
    return Neo4jVectorSearchService(
        driver=mock_driver, embeddings_service=mock_embeddings_service, config=config
    )


@pytest.mark.asyncio
async def test_find_similar_by_text_with_metrics(vector_search_service, mock_driver):
    """Test vector search with metrics tracking."""
    # Mock driver response — execute_query returns (records, summary, keys) tuple
    mock_driver.execute_query.return_value = (
        [
            {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 0.9},
            {"node": {"uid": "ku.django", "title": "Django Framework"}, "score": 0.8},
        ],
        None,
        None,
    )

    result, metrics = await vector_search_service.find_similar_by_text_with_metrics(
        label="Ku", text="python programming", limit=10
    )

    # Verify result
    assert result.is_ok
    assert len(result.value) == 2

    # Verify metrics
    assert metrics is not None
    assert metrics.query == "python programming"
    assert metrics.search_type == "vector"
    assert metrics.label == "Ku"
    assert metrics.num_results == 2
    assert metrics.avg_similarity == pytest.approx(0.85)  # (0.9 + 0.8) / 2
    assert metrics.min_similarity == pytest.approx(0.8)
    assert metrics.max_similarity == pytest.approx(0.9)
    assert metrics.latency_ms > 0  # Should have measured some latency
    assert metrics.timestamp is not None


@pytest.mark.asyncio
async def test_find_similar_by_text_with_metrics_error(vector_search_service, mock_driver):
    """Test metrics when search fails."""
    # Mock driver to raise error
    mock_driver.execute_query.side_effect = Exception("Database error")

    result, metrics = await vector_search_service.find_similar_by_text_with_metrics(
        label="Ku", text="test query"
    )

    # Verify error result
    assert result.is_error

    # Metrics should be None on error
    assert metrics is None


@pytest.mark.asyncio
async def test_hybrid_search_with_metrics(vector_search_service, mock_driver):
    """Test hybrid search with metrics tracking."""
    # Mock responses for both vector and fulltext searches
    call_count = [0]

    async def mock_execute_query(query, params):
        call_count[0] += 1

        # Vector search
        if "db.index.vector.queryNodes" in query:
            return (
                [
                    {"node": {"uid": "ku.python", "title": "Python"}, "score": 0.9},
                    {"node": {"uid": "ku.javascript", "title": "JavaScript"}, "score": 0.8},
                ],
                None,
                None,
            )
        # Full-text search
        elif "db.index.fulltext.queryNodes" in query:
            return (
                [
                    {"node": {"uid": "ku.python", "title": "Python"}, "score": 5.0},
                    {"node": {"uid": "ku.django", "title": "Django"}, "score": 3.0},
                ],
                None,
                None,
            )
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    result, metrics = await vector_search_service.hybrid_search_with_metrics(
        label="Ku", query_text="python", limit=10, min_rrf_score=0.0
    )

    # Verify result
    assert result.is_ok
    assert len(result.value) == 3  # 3 unique nodes

    # Verify metrics
    assert metrics is not None
    assert metrics.query == "python"
    assert metrics.search_type == "hybrid"
    assert metrics.label == "Ku"
    assert metrics.num_results == 3
    assert metrics.latency_ms > 0
    assert metrics.vector_weight == 0.5  # Default config value
    assert metrics.timestamp is not None

    # Check RRF scores
    assert metrics.avg_similarity > 0.0
    assert metrics.min_similarity > 0.0
    assert metrics.max_similarity > 0.0


@pytest.mark.asyncio
async def test_hybrid_search_with_metrics_custom_weight(vector_search_service, mock_driver):
    """Test metrics capture custom vector weight."""

    # Mock empty results for simplicity
    async def mock_execute_query(query, params):
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    result, metrics = await vector_search_service.hybrid_search_with_metrics(
        label="Ku", query_text="test", vector_weight=0.7, min_rrf_score=0.0
    )

    assert result.is_ok
    assert metrics is not None
    assert metrics.vector_weight == 0.7  # Custom weight captured


@pytest.mark.asyncio
async def test_metrics_track_empty_results(vector_search_service, mock_driver):
    """Test metrics correctly handle zero results."""
    # Mock empty results — execute_query returns (records, summary, keys) tuple
    mock_driver.execute_query.return_value = ([], None, None)

    result, metrics = await vector_search_service.find_similar_by_text_with_metrics(
        label="Ku", text="nonexistent query"
    )

    assert result.is_ok
    assert len(result.value) == 0

    # Metrics should still be created
    assert metrics is not None
    assert metrics.num_results == 0
    assert metrics.avg_similarity == 0.0
    assert metrics.min_similarity == 0.0
    assert metrics.max_similarity == 0.0


@pytest.mark.asyncio
async def test_metrics_similarity_statistics(vector_search_service, mock_driver):
    """Test metrics correctly calculate similarity statistics."""
    # Mock results with known scores — execute_query returns (records, summary, keys) tuple
    mock_driver.execute_query.return_value = (
        [
            {"node": {"uid": "ku.a", "title": "A"}, "score": 1.0},
            {"node": {"uid": "ku.b", "title": "B"}, "score": 0.8},
            {"node": {"uid": "ku.c", "title": "C"}, "score": 0.6},
        ],
        None,
        None,
    )

    result, metrics = await vector_search_service.find_similar_by_text_with_metrics(
        label="Ku", text="test"
    )

    assert result.is_ok
    assert metrics is not None

    # Verify statistics
    assert metrics.num_results == 3
    assert metrics.avg_similarity == pytest.approx(0.8)  # (1.0 + 0.8 + 0.6) / 3
    assert metrics.min_similarity == 0.6
    assert metrics.max_similarity == 1.0


@pytest.mark.asyncio
async def test_metrics_latency_measurement(vector_search_service, mock_driver):
    """Test that metrics measure latency correctly."""
    import asyncio

    # Mock with artificial delay — execute_query returns (records, summary, keys) tuple
    async def slow_query(query, params):
        await asyncio.sleep(0.05)  # 50ms delay
        return (
            [{"node": {"uid": "ku.test", "title": "Test"}, "score": 0.9}],
            None,
            None,
        )

    mock_driver.execute_query = slow_query

    result, metrics = await vector_search_service.find_similar_by_text_with_metrics(
        label="Ku", text="test"
    )

    assert result.is_ok
    assert metrics is not None

    # Latency should be >= 50ms
    assert metrics.latency_ms >= 50.0

    # But not absurdly high (< 1 second for 50ms operation)
    assert metrics.latency_ms < 1000.0
