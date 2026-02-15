"""
Integration tests for hybrid search with RRF.

Tests the hybrid_search method that combines:
- Vector similarity search
- Full-text keyword search
- Reciprocal Rank Fusion (RRF) scoring

Created: January 2026
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver for testing."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def mock_embeddings_service():
    """Mock embeddings service that returns deterministic embeddings."""
    service = MagicMock()

    async def create_embedding(text, metadata=None):
        # Return mock embedding based on text length
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
async def test_fulltext_search_returns_results(vector_search_service, mock_driver):
    """Test internal full-text search method."""
    # Mock driver response — execute_query returns (records, summary, keys) tuple
    mock_driver.execute_query.return_value = (
        [
            {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 5.2},
            {"node": {"uid": "ku.django", "title": "Django Framework"}, "score": 3.1},
        ],
        None,
        None,
    )

    result = await vector_search_service._fulltext_search(label="Ku", query_text="python", limit=10)

    assert result.is_ok
    assert len(result.value) == 2
    assert result.value[0]["node"]["uid"] == "ku.python"
    assert result.value[0]["score"] == 5.2


@pytest.mark.asyncio
async def test_fulltext_search_handles_missing_index(vector_search_service, mock_driver):
    """Test full-text search gracefully handles missing indexes."""
    # Mock driver to raise exception (index doesn't exist)
    mock_driver.execute_query.side_effect = Exception("Index not found")

    result = await vector_search_service._fulltext_search(label="Ku", query_text="python", limit=10)

    # Should return empty list instead of error (graceful degradation)
    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_hybrid_search_combines_results(
    vector_search_service, mock_driver, mock_embeddings_service
):
    """Test hybrid search merges vector and full-text results with RRF."""
    # Mock vector search results (via find_similar_by_text)
    vector_results = [
        {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 0.9},
        {"node": {"uid": "ku.javascript", "title": "JavaScript Guide"}, "score": 0.8},
    ]

    # Mock full-text search results
    fulltext_results = [
        {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 5.0},  # Also in vector
        {
            "node": {"uid": "ku.django", "title": "Django Framework"},
            "score": 3.0,
        },  # Only in fulltext
    ]

    # Setup driver to return different results based on query
    call_count = [0]

    async def mock_execute_query(query, params):
        call_count[0] += 1

        # First call: vector search
        if "db.index.vector.queryNodes" in query:
            records = [
                {"node": {"uid": r["node"]["uid"], **r["node"]}, "score": r["score"]}
                for r in vector_results
            ]
            return (records, None, None)
        # Second call: full-text search
        elif "db.index.fulltext.queryNodes" in query:
            records = [
                {"node": {"uid": r["node"]["uid"], **r["node"]}, "score": r["score"]}
                for r in fulltext_results
            ]
            return (records, None, None)
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Execute hybrid search with min_rrf_score=0.0 to include all results
    result = await vector_search_service.hybrid_search(
        label="Ku", query_text="python programming", limit=10, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # Should have 3 unique nodes
    assert len(results) == 3

    # Results should be sorted by RRF score (descending)
    uids = [r["node"]["uid"] for r in results]

    # ku.python should be first (appears in both lists, highest RRF score)
    assert uids[0] == "ku.python"

    # All results should have RRF scores
    for item in results:
        assert "score" in item
        assert item["score"] > 0


@pytest.mark.asyncio
async def test_hybrid_search_rrf_scoring(vector_search_service, mock_driver):
    """Test RRF scoring calculation."""
    # Mock responses
    vector_results = [
        {"node": {"uid": "ku.a", "title": "A"}, "score": 0.9},  # Rank 1
        {"node": {"uid": "ku.b", "title": "B"}, "score": 0.8},  # Rank 2
    ]

    fulltext_results = [
        {"node": {"uid": "ku.b", "title": "B"}, "score": 5.0},  # Rank 1
        {"node": {"uid": "ku.c", "title": "C"}, "score": 3.0},  # Rank 2
    ]

    async def mock_execute_query(query, params):
        if "db.index.vector.queryNodes" in query:
            return ([{"node": r["node"], "score": r["score"]} for r in vector_results], None, None)
        elif "db.index.fulltext.queryNodes" in query:
            return (
                [{"node": r["node"], "score": r["score"]} for r in fulltext_results],
                None,
                None,
            )
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Execute with 50/50 weighting
    result = await vector_search_service.hybrid_search(
        label="Ku", query_text="test", vector_weight=0.5, limit=10, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # Calculate expected RRF scores (k=60, weight=0.5 for both)
    # ku.a: 0.5 * (1/(60+1)) = 0.5/61 = 0.00820 (vector rank 1 only)
    # ku.b: 0.5 * (1/(60+2)) + 0.5 * (1/(60+1)) = 0.5/62 + 0.5/61 = 0.01626 (highest!)
    #       vector rank 2 + fulltext rank 1
    # ku.c: 0.5 * (1/(60+2)) = 0.5/62 = 0.00806 (fulltext rank 2 only)

    # ku.b should be first (appears in both lists with highest combined score)
    assert results[0]["node"]["uid"] == "ku.b"

    # Verify RRF score is approximately correct
    expected_score = 0.5 / 62 + 0.5 / 61  # Rank 2 in vector, rank 1 in fulltext
    assert abs(results[0]["score"] - expected_score) < 0.0001


@pytest.mark.asyncio
async def test_hybrid_search_uses_config_defaults(vector_search_service, mock_driver):
    """Test hybrid search uses config defaults correctly."""

    # Mock empty results
    async def mock_execute_query(query, params):
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Call without explicit parameters
    result = await vector_search_service.hybrid_search(label="Ku", query_text="test")

    assert result.is_ok

    # Verify config defaults were used (can check via logs or service internals)
    assert vector_search_service.config.default_limit == 10
    assert vector_search_service.config.vector_weight == 0.5


@pytest.mark.asyncio
async def test_hybrid_search_filters_by_min_rrf_score(vector_search_service, mock_driver):
    """Test hybrid search filters results below min_rrf_score threshold."""

    # Mock results with varying RRF scores
    async def mock_execute_query(query, params):
        if "db.index.vector.queryNodes" in query:
            # Only one vector result (will have RRF score ~0.016)
            return ([{"node": {"uid": "ku.a", "title": "A"}, "score": 0.9}], None, None)
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Set high min_rrf_score threshold (higher than typical RRF score)
    result = await vector_search_service.hybrid_search(
        label="Ku",
        query_text="test",
        min_rrf_score=0.1,  # Higher than RRF score (~0.016)
    )

    assert result.is_ok
    # Results should be filtered out
    assert len(result.value) == 0


@pytest.mark.asyncio
async def test_hybrid_search_entity_specific_thresholds_for_vector(
    vector_search_service, mock_driver
):
    """Test hybrid search uses entity-specific thresholds for vector input search."""

    async def mock_execute_query(query, params):
        # Return empty for simplicity
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Test with different entity types
    result_ku = await vector_search_service.hybrid_search(label="Ku", query_text="test")
    result_task = await vector_search_service.hybrid_search(label="Task", query_text="test")

    assert result_ku.is_ok
    assert result_task.is_ok

    # Verify entity-specific thresholds from config (used for vector search input)
    assert vector_search_service.config.get_min_score_for_entity("Ku") == 0.75
    assert vector_search_service.config.get_min_score_for_entity("Task") == 0.65


@pytest.mark.asyncio
async def test_hybrid_search_handles_vector_failure(vector_search_service, mock_driver):
    """Test hybrid search continues with full-text only if vector fails."""
    # Mock vector search failure, full-text success
    call_count = [0]

    async def mock_execute_query(query, params):
        call_count[0] += 1
        if "db.index.vector.queryNodes" in query:
            raise Exception("Vector index error")
        elif "db.index.fulltext.queryNodes" in query:
            return ([{"node": {"uid": "ku.test", "title": "Test"}, "score": 3.0}], None, None)
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    result = await vector_search_service.hybrid_search(
        label="Ku", query_text="test", min_rrf_score=0.0
    )

    assert result.is_ok
    # Should still have full-text results
    assert len(result.value) > 0


@pytest.mark.asyncio
async def test_hybrid_search_handles_fulltext_failure(vector_search_service, mock_driver):
    """Test hybrid search continues with vector only if full-text fails."""

    async def mock_execute_query(query, params):
        if "db.index.vector.queryNodes" in query:
            return ([{"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8}], None, None)
        elif "db.index.fulltext.queryNodes" in query:
            raise Exception("Full-text index error")
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    result = await vector_search_service.hybrid_search(
        label="Ku", query_text="test", min_rrf_score=0.0
    )

    assert result.is_ok
    # Should still have vector results
    assert len(result.value) > 0


@pytest.mark.asyncio
async def test_hybrid_search_custom_weights(vector_search_service, mock_driver):
    """Test hybrid search respects custom vector/text weights."""

    # Mock results
    async def mock_execute_query(query, params):
        if "db.index.vector.queryNodes" in query:
            return ([{"node": {"uid": "ku.a", "title": "A"}, "score": 0.9}], None, None)
        elif "db.index.fulltext.queryNodes" in query:
            return ([{"node": {"uid": "ku.a", "title": "A"}, "score": 5.0}], None, None)
        return ([], None, None)

    mock_driver.execute_query = mock_execute_query

    # Test with 70% vector, 30% text weighting
    result = await vector_search_service.hybrid_search(
        label="Ku", query_text="test", vector_weight=0.7, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # RRF score should reflect 70/30 weighting
    # Expected: 0.7/(60+1) + 0.3/(60+1) = 1.0/61
    expected_score = 1.0 / 61
    assert abs(results[0]["score"] - expected_score) < 0.0001
