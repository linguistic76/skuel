"""
Integration tests demonstrating embedding fixtures usage.

Shows how to use mock embeddings and vector search fixtures in tests
to avoid API calls while testing semantic search functionality.

These tests serve as examples for how to use the fixtures in domain-specific tests.
"""

import pytest


@pytest.mark.asyncio
async def test_embedding_generation_with_mock(mock_embeddings_service):
    """Test embedding generation using mock service."""

    # Generate embedding for text
    result = await mock_embeddings_service.create_embedding("Python programming")

    assert result.is_ok
    embedding = result.value
    assert isinstance(embedding, list)
    assert len(embedding) == 1024  # Standard dimension
    assert all(isinstance(x, float) for x in embedding)


@pytest.mark.asyncio
async def test_batch_embedding_generation_with_mock(mock_embeddings_service):
    """Test batch embedding generation using mock service."""

    texts = ["Python programming", "JavaScript development", "Machine learning"]

    result = await mock_embeddings_service.create_batch_embeddings(texts)

    assert result.is_ok
    embeddings = result.value
    assert len(embeddings) == 3
    assert all(len(emb) == 1024 for emb in embeddings)

    # Each embedding should be different (based on text length + index)
    assert embeddings[0] != embeddings[1]
    assert embeddings[1] != embeddings[2]


@pytest.mark.asyncio
async def test_embedding_validation_with_mock(mock_embeddings_service):
    """Test embedding validation with empty text."""

    result = await mock_embeddings_service.create_embedding("")

    assert result.is_error
    error = result.expect_error()
    assert "Text cannot be empty" in str(error)


@pytest.mark.asyncio
async def test_similarity_calculation_with_mock(mock_embeddings_service):
    """Test similarity calculation between embeddings."""

    # Generate two embeddings
    result1 = await mock_embeddings_service.create_embedding("Python")
    result2 = await mock_embeddings_service.create_embedding("Python")

    assert result1.is_ok
    assert result2.is_ok

    emb1 = result1.value
    emb2 = result2.value

    # Calculate similarity
    similarity_result = await mock_embeddings_service.calculate_similarity(emb1, emb2)

    assert similarity_result.is_ok
    similarity = similarity_result.value
    assert 0.0 <= similarity <= 1.0


@pytest.mark.asyncio
async def test_vector_search_by_vector_with_mock(mock_vector_search_service):
    """Test vector similarity search using mock service."""

    # Mock embedding
    query_embedding = [0.001 * i for i in range(1, 1025)]

    result = await mock_vector_search_service.find_similar_by_vector(
        label="Entity", embedding=query_embedding, limit=5, min_score=0.7
    )

    assert result.is_ok
    similar = result.value
    assert isinstance(similar, list)
    assert len(similar) <= 5

    # Check structure of results
    for item in similar:
        assert "node" in item
        assert "score" in item
        assert item["node"]["uid"].startswith("entity.")  # label="Entity" → entity.*
        assert 0.7 <= item["score"] <= 1.0


@pytest.mark.asyncio
async def test_vector_search_by_text_with_mock(mock_vector_search_service):
    """Test text-based similarity search using mock service."""

    result = await mock_vector_search_service.find_similar_by_text(
        label="Task", text="Complete the project", limit=3, min_score=0.8
    )

    assert result.is_ok
    similar = result.value
    assert isinstance(similar, list)

    # Should only return results with score >= 0.8
    for item in similar:
        assert item["score"] >= 0.8


@pytest.mark.asyncio
async def test_vector_search_to_node_with_mock(mock_vector_search_service):
    """Test node-to-node similarity search using mock service."""

    result = await mock_vector_search_service.find_similar_to_node(
        label="Goal", uid="goal.test_001", limit=5, min_score=0.7, exclude_self=True
    )

    assert result.is_ok
    similar = result.value

    # Source node should be excluded
    assert all(item["node"]["uid"] != "goal.test_001" for item in similar)


@pytest.mark.asyncio
async def test_cross_domain_search_with_mock(mock_vector_search_service):
    """Test cross-domain similarity search using mock service."""

    query_embedding = [0.001 * i for i in range(1, 1025)]

    result = await mock_vector_search_service.find_cross_domain_similar(
        embedding=query_embedding,
        labels=["Entity", "Task", "Goal"],
        limit_per_label=3,
        min_score=0.7,
    )

    assert result.is_ok
    results = result.value
    assert isinstance(results, dict)
    assert "Entity" in results
    assert "Task" in results
    assert "Goal" in results

    # Each label should have results
    for label, items in results.items():
        assert isinstance(items, list)
        for item in items:
            assert item["node"]["uid"].startswith(label.lower())


@pytest.mark.asyncio
async def test_services_with_embeddings_fixture(services_with_embeddings):
    """Test combined services fixture."""

    # Both services should be available
    assert services_with_embeddings["embeddings"] is not None
    assert services_with_embeddings["vector_search"] is not None

    # Can use both together
    embeddings = services_with_embeddings["embeddings"]
    vector_search = services_with_embeddings["vector_search"]

    # Generate embedding
    emb_result = await embeddings.create_embedding("Test content")
    assert emb_result.is_ok

    # Use embedding for search
    search_result = await vector_search.find_similar_by_vector(
        label="Entity", embedding=emb_result.value, limit=3
    )
    assert search_result.is_ok


@pytest.mark.asyncio
async def test_embeddings_unavailable_scenario(mock_embeddings_unavailable):
    """Test graceful degradation when embeddings unavailable."""

    result = await mock_embeddings_unavailable.create_embedding("Test")

    assert result.is_error
    error = result.expect_error()
    assert "unavailable" in str(error).lower()
    assert "hf_api_token" in str(error).lower()


@pytest.mark.asyncio
async def test_vector_search_unavailable_scenario(mock_vector_search_unavailable):
    """Test graceful degradation when vector search unavailable."""

    result = await mock_vector_search_unavailable.find_similar_by_vector(
        label="Entity", embedding=[0.1] * 1024, limit=5
    )

    assert result.is_error
    error = result.expect_error()
    assert "error" in error


@pytest.mark.asyncio
async def test_empty_batch_embeddings(mock_embeddings_service):
    """Test batch embeddings with empty list."""

    result = await mock_embeddings_service.create_batch_embeddings([])

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_embedding_determinism(mock_embeddings_service):
    """Test that embeddings are deterministic for same input."""

    text = "Machine learning basics"

    result1 = await mock_embeddings_service.create_embedding(text)
    result2 = await mock_embeddings_service.create_embedding(text)

    assert result1.is_ok
    assert result2.is_ok

    # Same text should produce same embedding
    assert result1.value == result2.value


@pytest.mark.asyncio
async def test_embedding_variance(mock_embeddings_service):
    """Test that different texts produce different embeddings."""

    result1 = await mock_embeddings_service.create_embedding("Short")
    result2 = await mock_embeddings_service.create_embedding("This is a much longer text")

    assert result1.is_ok
    assert result2.is_ok

    # Different texts should produce different embeddings
    # (varies by first element based on text length)
    assert result1.value[0] != result2.value[0]
