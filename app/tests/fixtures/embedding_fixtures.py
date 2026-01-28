"""
Test fixtures for embeddings and vector search.

Provides mock embeddings to avoid OpenAI API calls during testing.

These fixtures enable testing of semantic search and vector operations
without requiring actual API keys or making external calls.

Usage:
    from tests.fixtures.embedding_fixtures import (
        mock_embedding_vector,
        mock_embeddings_service,
        mock_vector_search_service,
        services_with_embeddings,
    )

    async def test_semantic_search(services_with_embeddings):
        ku_search = KuSearchService(
            backend=mock_backend,
            vector_search_service=services_with_embeddings["vector_search"],
            embeddings_service=services_with_embeddings["embeddings"]
        )

        result = await ku_search.find_similar_content("ku.python", limit=5)
        assert result.is_ok
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.utils.result_simplified import Result


@pytest.fixture
def mock_embedding_vector():
    """
    Generate consistent mock embedding vector (1536 dimensions).

    Uses deterministic values for reproducible tests.
    Standard dimension for text-embedding-3-small model.

    Returns:
        List of 1536 floats representing an embedding vector
    """
    # Simple pattern: [0.001, 0.002, ..., 1.536]
    return [0.001 * i for i in range(1, 1537)]


@pytest.fixture
def mock_embeddings_service(mock_embedding_vector):
    """
    Mock Neo4j GenAI embeddings service.

    Returns deterministic embeddings without API calls.
    Mimics Neo4jGenAIEmbeddingsService interface.

    Returns:
        Mock embeddings service with create_embedding and create_batch_embeddings methods
    """

    service = MagicMock()

    # Mock create_embedding
    async def create_embedding(text, metadata=None):
        if not text or not text.strip():
            return Result.fail({"error": "Text cannot be empty"})

        # Return slightly different embeddings based on text length
        base_vector = mock_embedding_vector.copy()
        # Vary first element based on text to make embeddings distinguishable
        base_vector[0] = len(text) * 0.001
        return Result.ok(base_vector)

    # Mock create_batch_embeddings
    async def create_batch_embeddings(texts, metadata_list=None):
        if not texts:
            return Result.ok([])

        embeddings = []
        for i, text in enumerate(texts):
            vec = mock_embedding_vector.copy()
            # Make each embedding slightly different
            vec[0] = (len(text) + i) * 0.001
            embeddings.append(vec)
        return Result.ok(embeddings)

    # Mock calculate_similarity
    async def calculate_similarity(embedding1, embedding2):
        if len(embedding1) != len(embedding2):
            return Result.fail({"error": "Embeddings must have same dimension"})

        # Simple mock similarity (higher for identical vectors)
        if embedding1 == embedding2:
            return Result.ok(1.0)
        else:
            # Return a reasonable similarity score based on first element difference
            diff = abs(embedding1[0] - embedding2[0])
            similarity = max(0.0, 1.0 - diff)
            return Result.ok(similarity)

    service.create_embedding = create_embedding
    service.create_batch_embeddings = create_batch_embeddings
    service.calculate_similarity = calculate_similarity

    # Service attributes
    service.model = "text-embedding-3-small"
    service.dimension = 1536
    service._plugin_available = True

    return service


@pytest.fixture
def mock_vector_search_service():
    """
    Mock vector search service.

    Returns predefined similar nodes without Neo4j queries.
    Mimics Neo4jVectorSearchService interface.

    Returns:
        Mock vector search service with find_similar_* methods
    """

    service = MagicMock()

    async def find_similar_by_vector(label, embedding, limit=10, min_score=0.7):
        """Mock vector similarity search."""
        # Return mock similar nodes
        similar = [
            {
                "node": {
                    "uid": f"{label.lower()}.similar_{i}",
                    "title": f"Similar {label} {i}",
                    "content": f"Content {i}",
                },
                "score": 0.9 - (i * 0.1),  # Descending scores
            }
            for i in range(min(limit, 3))  # Return up to 3 results
            if (0.9 - (i * 0.1)) >= min_score  # Respect min_score
        ]
        return Result.ok(similar)

    async def find_similar_by_text(label, text, limit=10, min_score=0.7):
        """Mock text-based similarity search."""
        # Reuse vector search logic (would normally embed text first)
        return await find_similar_by_vector(label, [], limit, min_score)

    async def find_similar_to_node(label, uid, limit=10, min_score=0.7, exclude_self=True):
        """Mock node-to-node similarity search."""
        similar = await find_similar_by_vector(label, [], limit + 1 if exclude_self else limit, min_score)

        if similar.is_error:
            return similar

        results = similar.value

        # Exclude source node if requested
        if exclude_self:
            results = [r for r in results if r["node"]["uid"] != uid][:limit]

        return Result.ok(results)

    async def find_cross_domain_similar(embedding, labels, limit_per_label=5, min_score=0.7):
        """Mock cross-domain similarity search."""
        results = {}

        for label in labels:
            search_result = await find_similar_by_vector(
                label=label, embedding=embedding, limit=limit_per_label, min_score=min_score
            )

            if search_result.is_ok:
                results[label] = search_result.value
            else:
                results[label] = []

        return Result.ok(results)

    service.find_similar_by_vector = find_similar_by_vector
    service.find_similar_by_text = find_similar_by_text
    service.find_similar_to_node = find_similar_to_node
    service.find_cross_domain_similar = find_cross_domain_similar

    return service


@pytest.fixture
def services_with_embeddings(mock_embeddings_service, mock_vector_search_service):
    """
    Provide services dict with mock embeddings and vector search.

    Use this fixture in tests that need AI features without API calls.

    Returns:
        Dict with 'embeddings' and 'vector_search' services

    Example:
        async def test_semantic_search(services_with_embeddings):
            service = KuSearchService(
                backend=mock_backend,
                embeddings_service=services_with_embeddings["embeddings"],
                vector_search_service=services_with_embeddings["vector_search"]
            )
    """

    return {
        "embeddings": mock_embeddings_service,
        "vector_search": mock_vector_search_service,
        "llm": None,  # LLM service separate - not part of embeddings fixtures
    }


@pytest.fixture
def mock_embeddings_unavailable():
    """
    Mock embeddings service that simulates plugin unavailable.

    Use this to test graceful degradation when embeddings are not available.

    Returns:
        Mock service that returns unavailable errors
    """

    service = MagicMock()

    async def create_embedding(text, metadata=None):
        return Result.fail(
            {
                "error": "unavailable",
                "feature": "embeddings",
                "reason": "Neo4j GenAI plugin not available",
            }
        )

    async def create_batch_embeddings(texts, metadata_list=None):
        return Result.fail(
            {
                "error": "unavailable",
                "feature": "embeddings",
                "reason": "Neo4j GenAI plugin not available",
            }
        )

    service.create_embedding = create_embedding
    service.create_batch_embeddings = create_batch_embeddings
    service.model = "text-embedding-3-small"
    service.dimension = 1536
    service._plugin_available = False

    return service


@pytest.fixture
def mock_vector_search_unavailable():
    """
    Mock vector search service that simulates index unavailable.

    Use this to test graceful degradation when vector indexes don't exist.

    Returns:
        Mock service that returns unavailable errors
    """

    service = MagicMock()

    async def find_similar_by_vector(label, embedding, limit=10, min_score=0.7):
        return Result.fail(
            {"error": "database", "operation": "vector_search", "message": "Vector index not found"}
        )

    async def find_similar_by_text(label, text, limit=10, min_score=0.7):
        return Result.fail(
            {"error": "unavailable", "feature": "semantic_search", "reason": "Embeddings service required"}
        )

    async def find_similar_to_node(label, uid, limit=10, min_score=0.7, exclude_self=True):
        return Result.fail(
            {"error": "not_found", "entity_type": label, "uid": uid, "context": {"reason": "No embedding found"}}
        )

    service.find_similar_by_vector = find_similar_by_vector
    service.find_similar_by_text = find_similar_by_text
    service.find_similar_to_node = find_similar_to_node

    return service
