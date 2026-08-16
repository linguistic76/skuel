"""
Integration tests for hybrid search with RRF.

Tests the hybrid_search method that combines:
- Vector similarity search
- Full-text keyword search
- Reciprocal Rank Fusion (RRF) scoring

Created: January 2026
Updated: April 2026 — commit bdbb4710 routed the service through
VectorSearchBackend, so these tests stub backend methods directly instead
of patching driver.execute_query with query-string branching.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_backend():
    """Mock VectorSearchBackend — stubs the methods the service actually calls."""
    backend = MagicMock()
    backend.query_vector_index = AsyncMock(return_value=Result.ok([]))
    backend.query_fulltext_index = AsyncMock(return_value=Result.ok([]))
    backend.get_semantic_relationships = AsyncMock(return_value=Result.ok([]))
    backend.get_learning_states_batch = AsyncMock(return_value=Result.ok([]))
    backend.get_node_embedding = AsyncMock(return_value=Result.ok([]))
    return backend


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
def vector_search_service(mock_backend, mock_embeddings_service):
    """Create vector search service with mocks."""
    config = VectorSearchConfig()
    return Neo4jVectorSearchService(
        backend=mock_backend, embeddings_service=mock_embeddings_service, config=config
    )


@pytest.mark.asyncio
async def test_fulltext_search_returns_results(vector_search_service, mock_backend):
    """Test internal full-text search method."""
    mock_backend.query_fulltext_index.return_value = Result.ok(
        [
            {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 5.2},
            {"node": {"uid": "ku.django", "title": "Django Framework"}, "score": 3.1},
        ]
    )

    result = await vector_search_service._fulltext_search(
        label="Entity", query_text="python", limit=10
    )

    assert result.is_ok
    assert len(result.value) == 2
    assert result.value[0]["node"]["uid"] == "ku.python"
    assert result.value[0]["score"] == 5.2


@pytest.mark.asyncio
async def test_fulltext_search_handles_missing_index(vector_search_service, mock_backend):
    """Test full-text search gracefully handles missing indexes."""
    mock_backend.query_fulltext_index.return_value = Result.fail(
        Errors.database(operation="fulltext_search", message="Index not found")
    )

    result = await vector_search_service._fulltext_search(
        label="Entity", query_text="python", limit=10
    )

    # Should return empty list instead of error (graceful degradation)
    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_hybrid_search_combines_results(vector_search_service, mock_backend):
    """Test hybrid search merges vector and full-text results with RRF."""
    mock_backend.query_vector_index.return_value = Result.ok(
        [
            {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 0.9},
            {"node": {"uid": "ku.javascript", "title": "JavaScript Guide"}, "score": 0.8},
        ]
    )
    mock_backend.query_fulltext_index.return_value = Result.ok(
        [
            {"node": {"uid": "ku.python", "title": "Python Basics"}, "score": 5.0},
            {"node": {"uid": "ku.django", "title": "Django Framework"}, "score": 3.0},
        ]
    )

    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="python programming", limit=10, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # Should have 3 unique nodes
    assert len(results) == 3

    # ku.python should be first (appears in both lists, highest RRF score)
    uids = [r["node"]["uid"] for r in results]
    assert uids[0] == "ku.python"

    # All results should have RRF scores
    for item in results:
        assert "score" in item
        assert item["score"] > 0


@pytest.mark.asyncio
async def test_hybrid_search_rrf_scoring(vector_search_service, mock_backend):
    """Test RRF scoring calculation."""
    mock_backend.query_vector_index.return_value = Result.ok(
        [
            {"node": {"uid": "ku.a", "title": "A"}, "score": 0.9},  # Rank 1
            {"node": {"uid": "ku.b", "title": "B"}, "score": 0.8},  # Rank 2
        ]
    )
    mock_backend.query_fulltext_index.return_value = Result.ok(
        [
            {"node": {"uid": "ku.b", "title": "B"}, "score": 5.0},  # Rank 1
            {"node": {"uid": "ku.c", "title": "C"}, "score": 3.0},  # Rank 2
        ]
    )

    # Execute with 50/50 weighting
    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="test", vector_weight=0.5, limit=10, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # ku.b should be first (rank 2 in vector + rank 1 in fulltext = highest combined)
    assert results[0]["node"]["uid"] == "ku.b"

    # Verify RRF score is approximately correct (k=60, weight=0.5 for both)
    expected_score = 0.5 / 62 + 0.5 / 61
    assert abs(results[0]["score"] - expected_score) < 0.0001


@pytest.mark.asyncio
async def test_hybrid_search_uses_config_defaults(vector_search_service, mock_backend):
    """Test hybrid search uses config defaults correctly."""
    # Backend returns empty (fixture default)
    result = await vector_search_service.hybrid_search(label="Entity", query_text="test")

    assert result.is_ok

    # Verify config defaults
    assert vector_search_service.config.default_limit == 10
    assert vector_search_service.config.vector_weight == 0.5


@pytest.mark.asyncio
async def test_hybrid_search_filters_by_min_rrf_score(vector_search_service, mock_backend):
    """Test hybrid search filters results below min_rrf_score threshold."""
    # Only one vector result (will have RRF score ~0.016)
    mock_backend.query_vector_index.return_value = Result.ok(
        [{"node": {"uid": "ku.a", "title": "A"}, "score": 0.9}]
    )

    # Set high min_rrf_score threshold (higher than typical RRF score)
    result = await vector_search_service.hybrid_search(
        label="Entity",
        query_text="test",
        min_rrf_score=0.1,  # Higher than RRF score (~0.016)
    )

    assert result.is_ok
    # Results should be filtered out
    assert len(result.value) == 0


@pytest.mark.asyncio
async def test_hybrid_search_entity_specific_thresholds_for_vector(
    vector_search_service, mock_backend
):
    """Test hybrid search uses entity-specific thresholds for vector input search."""
    # Backend returns empty (fixture default) — we just exercise both entity types
    result_ku = await vector_search_service.hybrid_search(label="Entity", query_text="test")
    result_task = await vector_search_service.hybrid_search(label="Task", query_text="test")

    assert result_ku.is_ok
    assert result_task.is_ok

    # Verify entity-specific thresholds from config (used for vector search input)
    assert vector_search_service.config.get_min_score_for_entity("Entity") == 0.75
    assert vector_search_service.config.get_min_score_for_entity("Task") == 0.65


@pytest.mark.asyncio
async def test_hybrid_search_handles_vector_failure(vector_search_service, mock_backend):
    """Test hybrid search continues with full-text only if vector fails."""
    mock_backend.query_vector_index.return_value = Result.fail(
        Errors.database(operation="vector_search", message="Vector index error")
    )
    mock_backend.query_fulltext_index.return_value = Result.ok(
        [{"node": {"uid": "ku.test", "title": "Test"}, "score": 3.0}]
    )

    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="test", min_rrf_score=0.0
    )

    assert result.is_ok
    # Should still have full-text results
    assert len(result.value) > 0


@pytest.mark.asyncio
async def test_hybrid_search_handles_fulltext_failure(vector_search_service, mock_backend):
    """Test hybrid search continues with vector only if full-text fails."""
    mock_backend.query_vector_index.return_value = Result.ok(
        [{"node": {"uid": "ku.test", "title": "Test"}, "score": 0.8}]
    )
    mock_backend.query_fulltext_index.return_value = Result.fail(
        Errors.database(operation="fulltext_search", message="Full-text index error")
    )

    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="test", min_rrf_score=0.0
    )

    assert result.is_ok
    # Should still have vector results
    assert len(result.value) > 0


@pytest.mark.asyncio
async def test_max_rrf_score_is_the_real_ceiling(vector_search_service, mock_backend):
    """`max_rrf_score` must equal what hybrid_search actually produces at best.

    SearchRouter divides by this property to put RRF on the same 0-1 scale as
    every other rung. If the algorithm's real maximum drifted above it, hybrid
    results would clamp to 1.0 and lose their ordering; below it, they would
    rank systematically low against other domains.
    """
    top = [{"node": {"uid": "ku.best", "title": "Best"}, "score": 0.99}]
    mock_backend.query_vector_index.return_value = Result.ok(top)
    mock_backend.query_fulltext_index.return_value = Result.ok(top)

    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="test", min_rrf_score=0.0
    )

    assert result.is_ok
    best_possible = result.value[0]["score"]  # rank 1 in BOTH halves
    assert best_possible == pytest.approx(vector_search_service.max_rrf_score)


@pytest.mark.asyncio
async def test_max_rrf_score_is_independent_of_the_weight_split(
    vector_search_service, mock_backend
):
    """The ceiling is 1/(k+1) whatever the split, because the weights sum to 1."""
    top = [{"node": {"uid": "ku.best", "title": "Best"}, "score": 0.99}]
    mock_backend.query_vector_index.return_value = Result.ok(top)
    mock_backend.query_fulltext_index.return_value = Result.ok(top)

    for weight in (0.0, 0.3, 0.5, 0.9, 1.0):
        result = await vector_search_service.hybrid_search(
            label="Entity", query_text="test", vector_weight=weight, min_rrf_score=0.0
        )
        assert result.value[0]["score"] == pytest.approx(vector_search_service.max_rrf_score)


@pytest.mark.asyncio
async def test_hybrid_search_custom_weights(vector_search_service, mock_backend):
    """Test hybrid search respects custom vector/text weights."""
    mock_backend.query_vector_index.return_value = Result.ok(
        [{"node": {"uid": "ku.a", "title": "A"}, "score": 0.9}]
    )
    mock_backend.query_fulltext_index.return_value = Result.ok(
        [{"node": {"uid": "ku.a", "title": "A"}, "score": 5.0}]
    )

    # Test with 70% vector, 30% text weighting
    result = await vector_search_service.hybrid_search(
        label="Entity", query_text="test", vector_weight=0.7, min_rrf_score=0.0
    )

    assert result.is_ok
    results = result.value

    # RRF score should reflect 70/30 weighting
    # Expected: 0.7/(60+1) + 0.3/(60+1) = 1.0/61
    expected_score = 1.0 / 61
    assert abs(results[0]["score"] - expected_score) < 0.0001
