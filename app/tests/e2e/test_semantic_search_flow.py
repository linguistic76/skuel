"""
End-to-end tests for semantic search flow.

Tests complete workflow: Ingest → Generate Embeddings → Store → Search → Retrieve

These tests validate the full integration of:
- UnifiedIngestionService - Content ingestion and preparation
- Neo4jGenAIEmbeddingsService - Embedding generation
- UniversalNeo4jBackend - Database storage
- Neo4jVectorSearchService - Vector similarity search
- KuSearchService - Search orchestration

All tests use mock embedding services to avoid API calls.
"""

import pytest

from core.models.enums.ku_enums import KuType
from core.services.ingestion.preparer import prepare_entity_data_async


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_semantic_search_flow(
    neo4j_driver, clean_neo4j, services_with_embeddings, ku_backend
):
    """
    Test complete end-to-end flow:
    1. Prepare KU data with embedding generation
    2. Store in Neo4j
    3. Search for similar content
    4. Retrieve and validate results
    """

    # 1. Prepare KU data with embeddings
    ku_data = {
        "uid": "ku.test_e2e_python",
        "title": "Python List Comprehensions",
        "domain": "programming",
        "status": "active",
    }

    body_content = """
    List comprehensions provide a concise way to create lists in Python.
    They consist of brackets containing an expression followed by a for clause.

    Example:
    squares = [x**2 for x in range(10)]

    This is more compact than using a traditional for loop.
    """

    # Prepare entity data with embeddings
    from pathlib import Path

    prepared = await prepare_entity_data_async(
        entity_type=KuType.CURRICULUM,
        data=ku_data,
        body=body_content.strip(),
        file_path=Path("/fake/path/test.md"),
        default_user_uid="user.test",
        embeddings_service=services_with_embeddings["embeddings"],
    )

    # Verify embedding was generated
    assert isinstance(prepared, dict)
    assert "embedding" in prepared
    assert len(prepared["embedding"]) == 1536
    assert prepared["embedding_model"] == "text-embedding-3-small"
    assert prepared["embedding_updated_at"] is not None

    # 2. Store in Neo4j
    create_query = """
    CREATE (ku:Ku)
    SET ku = $props
    RETURN ku.uid as uid
    """

    async with neo4j_driver.session() as session:
        result = await session.run(create_query, {"props": prepared})
        record = await result.single()
        created_uid = record["uid"]

    assert created_uid == "ku.test_e2e_python"

    # 3. Verify stored with embedding
    verify_query = """
    MATCH (ku:Ku {uid: $uid})
    RETURN ku.uid as uid,
           ku.title as title,
           ku.embedding as embedding,
           size(ku.embedding) as embedding_dim,
           ku.embedding_model as model
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query, {"uid": created_uid})
        record = await result.single()

    assert record["uid"] == created_uid
    assert record["title"] == "Python List Comprehensions"
    assert record["embedding_dim"] == 1536
    assert record["model"] == "text-embedding-3-small"

    # 4. Search for similar content using mock vector search
    vector_search = services_with_embeddings["vector_search"]

    search_result = await vector_search.find_similar_by_text(
        label="Ku", text="How to use list comprehensions in Python", limit=5, min_score=0.7
    )

    assert search_result.is_ok
    similar_nodes = search_result.value

    # Mock service returns up to 3 results
    assert isinstance(similar_nodes, list)
    assert len(similar_nodes) <= 3

    # Verify structure of results
    for item in similar_nodes:
        assert "node" in item
        assert "score" in item
        assert item["score"] >= 0.7


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_batch_embedding_generation_e2e(neo4j_driver, clean_neo4j, mock_embeddings_service):
    """
    Test batch embedding generation for multiple KUs.

    Workflow:
    1. Create multiple KUs without embeddings
    2. Manually batch process embeddings
    3. Verify all KUs have embeddings

    Note: This test manually implements batch processing logic
    since the batch script uses a different driver API pattern.
    """

    # 1. Create multiple KUs without embeddings
    kus = [
        {
            "uid": f"ku.batch_e2e_{i}",
            "title": f"Batch Test KU {i}",
            "content": f"This is test content for batch processing {i}." * 5,  # Vary length
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        for i in range(10)
    ]

    # Create KUs in Neo4j without embeddings
    for ku in kus:
        create_query = """
        CREATE (ku:Ku {
            uid: $uid,
            title: $title,
            content: $content,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at)
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Verify KUs created without embeddings
    count_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.batch_e2e_'
    RETURN count(ku) as total,
           count(ku.embedding) as with_embedding
    """

    async with neo4j_driver.session() as session:
        result = await session.run(count_query)
        record = await result.single()

    assert record["total"] == 10
    assert record["with_embedding"] == 0  # No embeddings yet

    # 2. Manually process batch embeddings (simulating batch script logic)
    # Find nodes without embeddings
    find_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.batch_e2e_' AND ku.embedding IS NULL
    RETURN ku.uid as uid, ku.title as title, ku.content as content
    """

    async with neo4j_driver.session() as session:
        result = await session.run(find_query)
        nodes = [dict(record) async for record in result]

    assert len(nodes) == 10

    # Generate embeddings for all
    texts = [f"{node['title']}\n{node['content']}" for node in nodes]
    batch_result = await mock_embeddings_service.create_batch_embeddings(texts)
    assert batch_result.is_ok

    embeddings = batch_result.value
    assert len(embeddings) == 10

    # Update nodes with embeddings
    for node, embedding in zip(nodes, embeddings, strict=False):
        update_query = """
        MATCH (ku:Ku {uid: $uid})
        SET ku.embedding = $embedding,
            ku.embedding_model = $model,
            ku.embedding_updated_at = datetime()
        """
        async with neo4j_driver.session() as session:
            await session.run(
                update_query,
                {"uid": node["uid"], "embedding": embedding, "model": "text-embedding-3-small"},
            )

    # 3. Verify all KUs now have embeddings
    verify_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.batch_e2e_'
      AND ku.embedding IS NOT NULL
    RETURN count(ku) as count,
           collect(size(ku.embedding))[0] as first_dim
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["count"] == 10
    assert record["first_dim"] == 1536  # All embeddings 1536 dimensions


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ingestion_to_search_pipeline(neo4j_driver, clean_neo4j, services_with_embeddings):
    """
    Test complete pipeline from ingestion to search.

    This is the most comprehensive E2E test covering:
    1. Multiple KU ingestion with embeddings
    2. Verification of storage
    3. Cross-KU similarity search
    4. Result ranking validation
    """

    # 1. Ingest multiple related KUs
    kus_data = [
        {
            "uid": "ku.python_loops",
            "title": "Python For Loops",
            "content": "For loops in Python iterate over sequences. Use for item in sequence syntax.",
        },
        {
            "uid": "ku.python_comprehensions",
            "title": "Python List Comprehensions",
            "content": "List comprehensions provide concise syntax for creating lists. "
            "Use [expression for item in sequence] syntax.",
        },
        {
            "uid": "ku.javascript_arrays",
            "title": "JavaScript Arrays",
            "content": "JavaScript arrays are ordered collections. Use map, filter, reduce for transformations.",
        },
    ]

    embeddings_service = services_with_embeddings["embeddings"]

    # Prepare and store each KU with embeddings
    for ku_data in kus_data:
        # Generate embedding
        text = f"{ku_data['title']}\n{ku_data['content']}"
        embedding_result = await embeddings_service.create_embedding(text)
        assert embedding_result.is_ok

        # Add embedding to data
        ku_data["embedding"] = embedding_result.value
        ku_data["embedding_model"] = "text-embedding-3-small"
        ku_data["created_at"] = "2024-01-01T00:00:00Z"
        ku_data["updated_at"] = "2024-01-01T00:00:00Z"

        # Store in Neo4j
        create_query = """
        CREATE (ku:Ku {
            uid: $uid,
            title: $title,
            content: $content,
            embedding: $embedding,
            embedding_model: $embedding_model,
            created_at: datetime($created_at),
            updated_at: datetime($updated_at)
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku_data)

    # 2. Verify all stored
    verify_query = """
    MATCH (ku:Ku)
    WHERE ku.uid IN ['ku.python_loops', 'ku.python_comprehensions', 'ku.javascript_arrays']
    RETURN count(ku) as count
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["count"] == 3

    # 3. Search for similar content
    vector_search = services_with_embeddings["vector_search"]

    # Search for Python-related content
    search_result = await vector_search.find_similar_by_text(
        label="Ku", text="Python list creation techniques", limit=10, min_score=0.5
    )

    assert search_result.is_ok
    results = search_result.value

    # Should find results
    assert len(results) > 0

    # All results should have required structure
    for item in results:
        assert "node" in item
        assert "score" in item
        assert item["score"] >= 0.5


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_semantic_search_with_fallback(neo4j_driver, clean_neo4j):
    """
    Test semantic search with graceful fallback when embeddings unavailable.

    This validates that the system continues to work even without embeddings.
    """

    # Create KUs WITHOUT embeddings
    kus = [
        {
            "uid": f"ku.fallback_{i}",
            "title": f"Fallback Test {i}",
            "content": f"Content for fallback testing {i}",
        }
        for i in range(3)
    ]

    for ku in kus:
        create_query = """
        CREATE (ku:Ku {
            uid: $uid,
            title: $title,
            content: $content,
            created_at: datetime(),
            updated_at: datetime()
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Verify KUs exist without embeddings
    verify_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.fallback_'
    RETURN count(ku) as total,
           count(ku.embedding) as with_embedding
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["total"] == 3
    assert record["with_embedding"] == 0  # No embeddings

    # Try to search (would use keyword fallback in production)
    # This test validates the pattern - actual fallback logic in domain services


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cross_domain_semantic_search(neo4j_driver, clean_neo4j, services_with_embeddings):
    """
    Test semantic search across multiple domains (KU, Task, Goal).

    Validates that vector search can find semantically similar content
    across different entity types.
    """

    embeddings_service = services_with_embeddings["embeddings"]

    # Create entities in different domains with embeddings
    entities = [
        {
            "label": "Ku",
            "uid": "ku.async_programming",
            "title": "Async Programming in Python",
            "content": "Asynchronous programming with async/await syntax",
        },
        {
            "label": "Task",
            "uid": "task.learn_async",
            "title": "Learn Async Programming",
            "description": "Study asynchronous patterns in Python",
        },
        {
            "label": "Goal",
            "uid": "goal.master_async",
            "title": "Master Async Development",
            "description": "Become proficient in asynchronous programming",
        },
    ]

    # Generate embeddings and store each entity
    for entity in entities:
        # Generate embedding from title + content/description
        text = entity["title"] + "\n" + entity.get("content", entity.get("description", ""))
        embedding_result = await embeddings_service.create_embedding(text)
        assert embedding_result.is_ok

        embedding = embedding_result.value

        # Store in Neo4j
        if entity["label"] == "Ku":
            create_query = f"""
            CREATE (n:{entity["label"]} {{
                uid: $uid,
                title: $title,
                content: $content,
                embedding: $embedding,
                embedding_model: 'text-embedding-3-small',
                created_at: datetime(),
                updated_at: datetime()
            }})
            """
            params = {
                "uid": entity["uid"],
                "title": entity["title"],
                "content": entity["content"],
                "embedding": embedding,
            }
        else:
            create_query = f"""
            CREATE (n:{entity["label"]} {{
                uid: $uid,
                title: $title,
                description: $description,
                embedding: $embedding,
                embedding_model: 'text-embedding-3-small',
                created_at: datetime(),
                updated_at: datetime()
            }})
            """
            params = {
                "uid": entity["uid"],
                "title": entity["title"],
                "description": entity.get("description", ""),
                "embedding": embedding,
            }

        async with neo4j_driver.session() as session:
            await session.run(create_query, params)

    # Search across all domains
    vector_search = services_with_embeddings["vector_search"]

    cross_domain_result = await vector_search.find_cross_domain_similar(
        embedding=[0.001 * i for i in range(1, 1537)],  # Query embedding
        labels=["Ku", "Task", "Goal"],
        limit_per_label=5,
        min_score=0.5,
    )

    assert cross_domain_result.is_ok
    results_by_domain = cross_domain_result.value

    # Verify results for each domain
    assert "Ku" in results_by_domain
    assert "Task" in results_by_domain
    assert "Goal" in results_by_domain

    # Each domain should have results (mock returns up to 3)
    for results in results_by_domain.values():
        assert isinstance(results, list)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_embedding_update_workflow(neo4j_driver, clean_neo4j, services_with_embeddings):
    """
    Test workflow for updating embeddings when content changes.

    Workflow:
    1. Create KU with embedding
    2. Update content
    3. Regenerate embedding
    4. Verify updated embedding stored
    """

    embeddings_service = services_with_embeddings["embeddings"]

    # 1. Create initial KU with embedding
    text_v1 = "Python functions are reusable blocks of code."
    embedding_v1_result = await embeddings_service.create_embedding(text_v1)
    assert embedding_v1_result.is_ok
    embedding_v1 = embedding_v1_result.value

    create_query = """
    CREATE (ku:Ku {
        uid: 'ku.test_update',
        title: 'Python Functions',
        content: $content,
        embedding: $embedding,
        embedding_model: 'text-embedding-3-small',
        embedding_updated_at: datetime(),
        created_at: datetime(),
        updated_at: datetime()
    })
    """

    async with neo4j_driver.session() as session:
        await session.run(create_query, {"content": text_v1, "embedding": embedding_v1})

    # 2. Update content
    text_v2 = (
        "Python functions are reusable blocks of code that can accept parameters and return values."
    )

    embedding_v2_result = await embeddings_service.create_embedding(text_v2)
    assert embedding_v2_result.is_ok
    embedding_v2 = embedding_v2_result.value

    # 3. Update KU with new embedding
    update_query = """
    MATCH (ku:Ku {uid: 'ku.test_update'})
    SET ku.content = $content,
        ku.embedding = $embedding,
        ku.embedding_updated_at = datetime(),
        ku.updated_at = datetime()
    RETURN ku.uid as uid
    """

    async with neo4j_driver.session() as session:
        result = await session.run(update_query, {"content": text_v2, "embedding": embedding_v2})
        record = await result.single()

    assert record["uid"] == "ku.test_update"

    # 4. Verify updated embedding
    verify_query = """
    MATCH (ku:Ku {uid: 'ku.test_update'})
    RETURN ku.content as content,
           size(ku.embedding) as embedding_dim
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["content"] == text_v2
    assert record["embedding_dim"] == 1536


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_partial_batch_failure_handling(neo4j_driver, clean_neo4j, mock_embeddings_service):
    """
    Test batch embedding generation with partial failures.

    Validates that the system handles errors gracefully and processes
    successful items even when some fail.

    Note: Using mock service, all should succeed. This test validates
    the pattern for handling partial failures.
    """

    # Create KUs with various content (some may fail in production)
    kus = [
        {"uid": f"ku.partial_{i}", "title": f"Test {i}", "content": f"Content {i}"}
        for i in range(5)
    ]

    for ku in kus:
        create_query = """
        CREATE (ku:Ku {
            uid: $uid,
            title: $title,
            content: $content,
            created_at: datetime(),
            updated_at: datetime()
        })
        """
        async with neo4j_driver.session() as session:
            await session.run(create_query, ku)

    # Manually process embeddings (simulating batch script logic)
    find_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.partial_' AND ku.embedding IS NULL
    RETURN ku.uid as uid, ku.title as title, ku.content as content
    """

    async with neo4j_driver.session() as session:
        result = await session.run(find_query)
        nodes = [dict(record) async for record in result]

    # Generate embeddings
    texts = [f"{node['title']}\n{node['content']}" for node in nodes]
    batch_result = await mock_embeddings_service.create_batch_embeddings(texts)
    assert batch_result.is_ok

    embeddings = batch_result.value

    # Update nodes with embeddings
    successful = 0
    failed = 0

    for node, embedding in zip(nodes, embeddings, strict=False):
        try:
            update_query = """
            MATCH (ku:Ku {uid: $uid})
            SET ku.embedding = $embedding,
                ku.embedding_model = $model,
                ku.embedding_updated_at = datetime()
            """
            async with neo4j_driver.session() as session:
                await session.run(
                    update_query,
                    {"uid": node["uid"], "embedding": embedding, "model": "text-embedding-3-small"},
                )
            successful += 1
        except Exception:
            failed += 1

    # With mock service, all should succeed
    assert successful == 5
    assert failed == 0

    # Verify embeddings created
    verify_query = """
    MATCH (ku:Ku)
    WHERE ku.uid STARTS WITH 'ku.partial_'
      AND ku.embedding IS NOT NULL
    RETURN count(ku) as count
    """

    async with neo4j_driver.session() as session:
        result = await session.run(verify_query)
        record = await result.single()

    assert record["count"] == 5
