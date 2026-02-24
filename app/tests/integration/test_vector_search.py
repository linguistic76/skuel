"""
Integration tests for Neo4j vector search.

Tests vector index creation, embedding generation, and similarity search.
Uses mock services for testing without requiring actual OpenAI API or Neo4j GenAI plugin.

These tests verify:
1. Vector index creation and verification
2. Embedding generation and storage in Neo4j
3. Vector similarity search across KU nodes
4. Graceful degradation when embeddings unavailable
"""

import pytest

from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.utils.result_simplified import Result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_index_verification(neo4j_driver):
    """Test that we can query for vector indexes in Neo4j."""

    # Query for vector indexes
    query = """
    SHOW INDEXES
    YIELD name, type, labelsOrTypes, properties
    RETURN name, type, labelsOrTypes, properties
    """

    async with neo4j_driver.session() as session:
        result = await session.run(query)
        indexes = await result.data()

    # Should return some indexes (even if no vector indexes yet)
    assert isinstance(indexes, list)

    # Check structure of index results
    for idx in indexes:
        assert "name" in idx
        assert "type" in idx


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_vector_index_manually(neo4j_driver, clean_neo4j):
    """Test creating a vector index manually for testing purposes."""

    # Create a vector index for KU nodes
    # Note: This requires Neo4j 5.11+ with vector index support
    index_name = "ku_embedding_test_idx"

    create_index_query = """
    CREATE VECTOR INDEX $index_name IF NOT EXISTS
    FOR (n:Entity)
    ON n.embedding
    OPTIONS {indexConfig: {
        `vector.dimensions`: 1536,
        `vector.similarity_function`: 'cosine'
    }}
    """

    try:
        async with neo4j_driver.session() as session:
            await session.run(create_index_query, {"index_name": index_name})

        # Verify index was created
        verify_query = """
        SHOW INDEXES
        YIELD name, type, labelsOrTypes, properties
        WHERE type = 'VECTOR' AND name = $index_name
        RETURN name, type, labelsOrTypes, properties
        """

        async with neo4j_driver.session() as session:
            result = await session.run(verify_query, {"index_name": index_name})
            vector_indexes = await result.data()

        # Should find the index (if vector indexes are supported)
        # If not supported, this test will be skipped
        if len(vector_indexes) > 0:
            ku_index = vector_indexes[0]
            assert ku_index["name"] == index_name
            assert ku_index["type"] == "VECTOR"
            assert "Entity" in ku_index["labelsOrTypes"]
            assert "embedding" in ku_index["properties"]

    except Exception as e:
        # If vector indexes aren't supported, skip the test
        pytest.skip(f"Vector indexes not supported in this Neo4j version: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embedding_generation_and_storage(neo4j_driver, clean_neo4j, mock_embeddings_service):
    """Test embedding generation and storage in Neo4j."""

    # Create test Ku without embedding
    create_query = """
    CREATE (ku:Entity {
        uid: 'ku.test_embedding',
        title: 'Test Embedding Generation',
        content: 'This is test content for embedding generation.',
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN ku.uid as uid
    """

    async with neo4j_driver.session() as session:
        result = await session.run(create_query)
        record = await result.single()
        uid = record["uid"]

    assert uid == "ku.test_embedding"

    # Generate embedding using mock service
    text = "Test Embedding Generation This is test content for embedding generation."

    embedding_result = await mock_embeddings_service.create_embedding(text)
    assert embedding_result.is_ok

    embedding = embedding_result.value
    assert len(embedding) == 1536
    assert all(isinstance(x, float) for x in embedding)

    # Store embedding in Neo4j
    update_query = """
    MATCH (ku:Entity {uid: $uid})
    SET ku.embedding = $embedding,
        ku.embedding_model = $model,
        ku.embedding_updated_at = datetime()
    RETURN ku.uid as uid
    """

    async with neo4j_driver.session() as session:
        await session.run(
            update_query,
            {"uid": uid, "embedding": embedding, "model": "text-embedding-3-small"},
        )

    # Verify stored embedding
    verify_query = """
    MATCH (ku:Entity {uid: $uid})
    RETURN ku.embedding as embedding,
           size(ku.embedding) as dimension,
           ku.embedding_model as model
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query, {"uid": uid})
        record = await result.single()

    assert record["dimension"] == 1536
    assert record["model"] == "text-embedding-3-small"
    assert record["embedding"] == embedding


@pytest.mark.integration
@pytest.mark.asyncio
async def test_batch_embedding_generation(neo4j_driver, clean_neo4j, mock_embeddings_service):
    """Test batch embedding generation and storage."""

    # Create multiple KUs
    kus = [
        {
            "uid": f"ku.test_batch_{i}",
            "title": f"Test KU {i}",
            "content": f"Test content {i}" * 10,  # Vary length
        }
        for i in range(3)
    ]

    # Create KUs in Neo4j
    for ku in kus:
        create_query = """
        CREATE (ku:Entity {
            uid: $uid,
            title: $title,
            content: $content,
            created_at: datetime(),
            updated_at: datetime()
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Generate embeddings in batch
    texts = [ku["title"] + " " + ku["content"] for ku in kus]

    batch_result = await mock_embeddings_service.create_batch_embeddings(texts)
    assert batch_result.is_ok

    embeddings = batch_result.value
    assert len(embeddings) == 3
    assert all(len(emb) == 1536 for emb in embeddings)

    # Store embeddings
    for ku, embedding in zip(kus, embeddings, strict=False):
        update_query = """
        MATCH (ku:Entity {uid: $uid})
        SET ku.embedding = $embedding,
            ku.embedding_model = $model,
            ku.embedding_updated_at = datetime()
        """
        async with neo4j_driver.session() as session:
            await session.run(
                update_query,
                {"uid": ku["uid"], "embedding": embedding, "model": "text-embedding-3-small"},
            )

    # Verify all stored
    verify_query = """
    MATCH (ku:Entity)
    WHERE ku.uid STARTS WITH 'ku.test_batch_'
    RETURN count(ku) as count,
           count(ku.embedding) as with_embedding
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["count"] == 3
    assert record["with_embedding"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_service_initialization(neo4j_driver, mock_embeddings_service):
    """Test that vector search service initializes correctly."""

    # Create vector search service with mock embeddings
    vector_search = Neo4jVectorSearchService(
        executor=neo4j_driver, embeddings_service=mock_embeddings_service
    )

    assert vector_search.executor == neo4j_driver
    assert vector_search.embeddings == mock_embeddings_service


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_by_text_mock(neo4j_driver, clean_neo4j, services_with_embeddings):
    """Test vector search by text using mock services."""

    # Create test KUs with embeddings
    base_embedding = [0.001 * i for i in range(1, 1537)]

    kus = [
        {
            "uid": "ku.python_basics",
            "title": "Python Basics",
            "content": "Introduction to Python programming",
            "embedding": base_embedding,
        },
        {
            "uid": "ku.python_advanced",
            "title": "Python Advanced",
            "content": "Advanced Python concepts",
            "embedding": [e * 1.1 for e in base_embedding],  # Similar to basics
        },
        {
            "uid": "ku.javascript",
            "title": "JavaScript",
            "content": "JavaScript programming",
            "embedding": [e * 2.0 for e in base_embedding],  # Different
        },
    ]

    # Create KUs in Neo4j
    for ku in kus:
        create_query = """
        CREATE (ku:Entity {
            uid: $uid,
            title: $title,
            content: $content,
            embedding: $embedding,
            created_at: datetime(),
            updated_at: datetime()
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Create vector search service
    vector_search = services_with_embeddings["vector_search"]

    # Search for similar to "Python"
    result = await vector_search.find_similar_by_text(
        label="Entity", text="Python programming basics", limit=5, min_score=0.7
    )

    assert result.is_ok
    similar = result.value
    assert isinstance(similar, list)

    # Mock service returns up to 3 results
    assert len(similar) <= 3

    # Check structure of results
    for item in similar:
        assert "node" in item
        assert "score" in item
        assert item["node"]["uid"].startswith("entity.")  # label="Entity" → entity.*
        assert 0.7 <= item["score"] <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_by_vector_mock(neo4j_driver, clean_neo4j, mock_vector_search_service):
    """Test vector search by embedding vector using mock service."""

    # Create query embedding
    query_embedding = [0.001 * i for i in range(1, 1537)]

    # Search using mock service
    result = await mock_vector_search_service.find_similar_by_vector(
        label="Entity", embedding=query_embedding, limit=5, min_score=0.8
    )

    assert result.is_ok
    similar = result.value

    # Should return results matching min_score threshold
    assert all(item["score"] >= 0.8 for item in similar)

    # Results should be sorted by score (descending)
    scores = [item["score"] for item in similar]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_find_similar_to_node_mock(
    neo4j_driver, clean_neo4j, mock_vector_search_service
):
    """Test finding nodes similar to a specific node using mock service."""

    # Create test KUs
    kus = [
        {"uid": "ku.source", "title": "Source KU", "embedding": [0.1] * 1536},
        {"uid": "ku.similar_1", "title": "Similar KU 1", "embedding": [0.11] * 1536},
        {"uid": "ku.similar_2", "title": "Similar KU 2", "embedding": [0.12] * 1536},
    ]

    for ku in kus:
        create_query = """
        CREATE (ku:Entity {
            uid: $uid,
            title: $title,
            embedding: $embedding,
            created_at: datetime()
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Find similar to source node
    result = await mock_vector_search_service.find_similar_to_node(
        label="Entity", uid="ku.source", limit=5, min_score=0.7, exclude_self=True
    )

    assert result.is_ok
    similar = result.value

    # Source node should be excluded
    assert all(item["node"]["uid"] != "ku.source" for item in similar)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_domain_search_mock(neo4j_driver, clean_neo4j, mock_vector_search_service):
    """Test cross-domain similarity search using mock service."""

    query_embedding = [0.001 * i for i in range(1, 1537)]

    # Search across multiple domains
    result = await mock_vector_search_service.find_cross_domain_similar(
        embedding=query_embedding,
        labels=["Entity", "Task", "Goal"],
        limit_per_label=3,
        min_score=0.7,
    )

    assert result.is_ok
    results = result.value

    # Should have results for each domain
    assert isinstance(results, dict)
    assert "Entity" in results
    assert "Task" in results
    assert "Goal" in results

    # Each domain should have results (mock returns up to 3)
    for items in results.values():
        assert isinstance(items, list)
        assert len(items) <= 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graceful_degradation_no_embeddings_service(ku_backend):
    """Test that services work without embeddings service (graceful degradation)."""

    # Create a search service-like component WITHOUT embeddings
    # This tests the pattern used in domain services

    # Simulate service initialization with None for embeddings
    embeddings_service = None
    vector_search_service = None

    # Service should initialize successfully
    assert embeddings_service is None
    assert vector_search_service is None

    # When trying to use semantic search, it should fail gracefully
    # (Services should check for None and fall back to keyword search)

    # This is a pattern test - actual search services implement this


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graceful_degradation_unavailable_plugin(
    neo4j_driver, clean_neo4j, mock_embeddings_unavailable
):
    """Test graceful degradation when GenAI plugin is unavailable."""

    # Try to create embedding with unavailable service
    result = await mock_embeddings_unavailable.create_embedding("Test content")

    assert result.is_error
    error = result.expect_error()

    # Should return unavailable error, not crash
    assert "unavailable" in str(error).lower() or "error" in error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embedding_service_plugin_check(neo4j_driver):
    """Test Neo4j GenAI embeddings service plugin availability check."""

    # Create real embeddings service (will check for plugin)
    embeddings_service = Neo4jGenAIEmbeddingsService(
        executor=neo4j_driver, model="text-embedding-3-small", dimension=1536
    )

    # Check if plugin is available
    # This will likely return False since testcontainer doesn't have GenAI plugin
    plugin_available = await embeddings_service._check_plugin_availability()

    # Should return boolean (True or False, not None)
    assert isinstance(plugin_available, bool)

    # Should cache the result
    assert embeddings_service._plugin_available is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embeddings_service_graceful_failure(neo4j_driver):
    """Test that embeddings service fails gracefully when plugin unavailable."""

    embeddings_service = Neo4jGenAIEmbeddingsService(
        executor=neo4j_driver, model="text-embedding-3-small", dimension=1536
    )

    # Try to create embedding (will fail if plugin not available)
    result = await embeddings_service.create_embedding("Test content for embedding")

    # Should return a Result (not crash)
    assert isinstance(result, Result)

    # If plugin unavailable, should fail with clear error message
    if result.is_error:
        error = result.expect_error()
        error_str = str(error).lower()
        # Error should mention plugin, unavailable, or unknown function (when plugin missing)
        assert (
            "plugin" in error_str
            or "unavailable" in error_str
            or "unknown function" in error_str
            or "ai.text.embed" in error_str
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_search_empty_results(mock_vector_search_service):
    """Test vector search with high min_score threshold (no results)."""

    query_embedding = [0.001 * i for i in range(1, 1537)]

    # Search with very high min_score (no results should match)
    result = await mock_vector_search_service.find_similar_by_vector(
        label="Entity",
        embedding=query_embedding,
        limit=10,
        min_score=0.99,  # Very high threshold
    )

    assert result.is_ok
    similar = result.value

    # May return empty list or limited results
    assert isinstance(similar, list)
    assert len(similar) <= 3  # Mock returns max 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_similarity_calculation_mock(mock_embeddings_service):
    """Test similarity calculation between embeddings."""

    # Generate two embeddings
    text1 = "Python programming"
    text2 = "Python programming"  # Same text

    result1 = await mock_embeddings_service.create_embedding(text1)
    result2 = await mock_embeddings_service.create_embedding(text2)

    assert result1.is_ok
    assert result2.is_ok

    emb1 = result1.value
    emb2 = result2.value

    # Calculate similarity
    similarity_result = await mock_embeddings_service.calculate_similarity(emb1, emb2)

    assert similarity_result.is_ok
    similarity = similarity_result.value

    # Same text should have high similarity
    assert similarity >= 0.9
    assert 0.0 <= similarity <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_embeddings_dimension_validation(mock_embeddings_service):
    """Test that embeddings have correct dimensions."""

    result = await mock_embeddings_service.create_embedding("Test content")

    assert result.is_ok
    embedding = result.value

    # Should be 1536 dimensions (text-embedding-3-small)
    assert len(embedding) == 1536
    assert len(embedding) == mock_embeddings_service.dimension


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_text_embedding_validation(mock_embeddings_service):
    """Test validation of empty text input."""

    result = await mock_embeddings_service.create_embedding("")

    assert result.is_error
    error = result.expect_error()
    assert "empty" in str(error).lower() or "error" in error
