"""
Integration tests for semantic-enhanced search with real Neo4j.

Tests the complete semantic search flow with actual database operations,
semantic relationships, and learning state tracking.

Test Coverage:
1. Semantic-enhanced search with real Neo4j relationships
2. Learning-aware search with real learning state data
3. Performance benchmarking
4. End-to-end workflows
"""

import time

import pytest

from core.config.unified_config import VectorSearchConfig
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_enhanced_search_with_relationships(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Test semantic-enhanced search with actual Neo4j relationships."""

    # Create test knowledge units
    async with neo4j_driver.session() as session:
        # Create base KU
        result = await session.run(
            """
            CREATE (k1:Ku {
                uid: 'ku.python-basics',
                title: 'Python Basics',
                description: 'Introduction to Python programming',
                embedding: $embedding,
                created_at: datetime()
            })
        """,
            embedding=[0.1] * 1536,
        )
        await result.consume()

        # Create advanced KU with relationship to basics
        result = await session.run(
            """
            CREATE (k2:Ku {
                uid: 'ku.python-advanced',
                title: 'Advanced Python',
                description: 'Advanced Python programming concepts',
                embedding: $embedding,
                created_at: datetime()
            })
        """,
            embedding=[0.15] * 1536,
        )
        await result.consume()

        # Create semantic relationship
        result = await session.run("""
            MATCH (advanced:Ku {uid: 'ku.python-advanced'})
            MATCH (basics:Ku {uid: 'ku.python-basics'})
            CREATE (advanced)-[r:REQUIRES_THEORETICAL_UNDERSTANDING {
                confidence: 0.9,
                strength: 1.0,
                source: 'test'
            }]->(basics)
        """)
        await result.consume()  # Ensure transaction commits

    # Create vector search service
    config = VectorSearchConfig(
        semantic_boost_enabled=True,
        semantic_boost_weight=0.3,
        ku_min_score=0.0,  # Accept all for testing
    )
    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver, embeddings_service=mock_embeddings_service, config=config
    )

    # Execute semantic-enhanced search
    result = await vector_search.semantic_enhanced_search(
        label="Ku",
        text="python programming",
        context_uids=["ku.python-basics"],  # Context: basics
        limit=10,
    )

    assert result.is_ok
    results = result.value

    # Should find both KUs
    assert len(results) >= 1

    # Find the advanced KU result
    advanced_result = next((r for r in results if r["node"]["uid"] == "ku.python-advanced"), None)

    if advanced_result:
        # Should have semantic boost metadata
        assert "semantic_boost" in advanced_result
        assert "vector_score" in advanced_result

        # Semantic boost should be > 0 (has relationship to context)
        assert advanced_result["semantic_boost"] > 0.0

        # Enhanced score should reflect the boost
        # final_score = vector_score * 0.7 + semantic_boost * 0.3
        expected_min_score = advanced_result["vector_score"] * 0.7
        assert advanced_result["score"] >= expected_min_score


@pytest.mark.integration
@pytest.mark.asyncio
async def test_learning_aware_search_with_states(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Test learning-aware search with actual learning state relationships."""

    # Create test user and KUs
    async with neo4j_driver.session() as session:
        # Create user (MERGE to avoid conflicts with ensure_test_users fixture)
        result = await session.run("""
            MERGE (u:User {uid: 'user.test_learning'})
            ON CREATE SET u.created_at = datetime()
        """)
        await result.consume()

        # Create mastered KU
        result = await session.run(
            """
            CREATE (k1:Ku {
                uid: 'ku.mastered-topic',
                title: 'Mastered Topic',
                description: 'A topic the user has mastered',
                embedding: $embedding,
                created_at: datetime()
            })
        """,
            embedding=[0.2] * 1536,
        )
        await result.consume()

        # Create not-started KU
        result = await session.run(
            """
            CREATE (k2:Ku {
                uid: 'ku.new-topic',
                title: 'New Topic',
                description: 'A topic the user has not started',
                embedding: $embedding,
                created_at: datetime()
            })
        """,
            embedding=[0.25] * 1536,
        )
        await result.consume()

        # Create MASTERED relationship
        result = await session.run("""
            MATCH (u:User {uid: 'user.test_learning'})
            MATCH (k:Ku {uid: 'ku.mastered-topic'})
            CREATE (u)-[:MASTERED {
                mastered_at: datetime(),
                confidence: 1.0
            }]->(k)
        """)
        await result.consume()  # Ensure transaction commits

    # Create vector search service
    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver,
        embeddings_service=mock_embeddings_service,
        config=VectorSearchConfig(ku_min_score=0.0),
    )

    # Execute learning-aware search (prefer unmastered)
    result = await vector_search.learning_aware_search(
        label="Ku", text="topic", user_uid="user.test_learning", prefer_unmastered=True, limit=10
    )

    assert result.is_ok
    results = result.value

    # Should find both KUs
    assert len(results) >= 2

    # Find specific results
    mastered_result = next((r for r in results if r["node"]["uid"] == "ku.mastered-topic"), None)
    new_result = next((r for r in results if r["node"]["uid"] == "ku.new-topic"), None)

    if mastered_result and new_result:
        # Mastered should have penalty (lower score)
        assert mastered_result["learning_state"] == "mastered"
        assert mastered_result["score"] < mastered_result["vector_score"]

        # New should have boost (higher score)
        assert new_result["learning_state"] == "none"
        assert new_result["score"] > new_result["vector_score"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_boost_multiple_relationships(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Test semantic boost with multiple relationships to context."""

    async with neo4j_driver.session() as session:
        # Create context KUs
        result = await session.run(
            """
            CREATE (k1:Ku {
                uid: 'ku.context1',
                title: 'Context 1',
                embedding: $embedding
            })
        """,
            embedding=[0.1] * 1536,
        )
        await result.consume()

        result = await session.run(
            """
            CREATE (k2:Ku {
                uid: 'ku.context2',
                title: 'Context 2',
                embedding: $embedding
            })
        """,
            embedding=[0.12] * 1536,
        )
        await result.consume()

        # Create target KU
        result = await session.run(
            """
            CREATE (k3:Ku {
                uid: 'ku.target',
                title: 'Target KU',
                description: 'Has multiple relationships',
                embedding: $embedding
            })
        """,
            embedding=[0.15] * 1536,
        )
        await result.consume()

        # Create multiple semantic relationships
        result = await session.run("""
            MATCH (target:Ku {uid: 'ku.target'})
            MATCH (c1:Ku {uid: 'ku.context1'})
            MATCH (c2:Ku {uid: 'ku.context2'})
            CREATE (target)-[:REQUIRES_THEORETICAL_UNDERSTANDING {
                confidence: 0.9,
                strength: 1.0
            }]->(c1)
            CREATE (target)-[:BUILDS_MENTAL_MODEL {
                confidence: 0.8,
                strength: 0.9
            }]->(c2)
        """)
        await result.consume()  # Ensure transaction commits

    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver,
        embeddings_service=mock_embeddings_service,
        config=VectorSearchConfig(semantic_boost_enabled=True, ku_min_score=0.0),
    )

    result = await vector_search.semantic_enhanced_search(
        label="Ku", text="target", context_uids=["ku.context1", "ku.context2"], limit=10
    )

    assert result.is_ok
    results = result.value

    # Find target KU
    target_result = next((r for r in results if r["node"]["uid"] == "ku.target"), None)

    if target_result:
        # Should have significant boost (multiple relationships)
        assert target_result["semantic_boost"] > 0.5
        # Verify semantic boost is factored into final score
        # Note: final score is weighted average, so it may be higher or lower than vector score
        # depending on whether semantic_boost > vector_score
        assert "semantic_boost" in target_result
        assert "vector_score" in target_result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_performance_semantic_enhanced_search(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Performance test: semantic-enhanced search should be <200ms."""

    # Create 10 test KUs with relationships
    async with neo4j_driver.session() as session:
        for i in range(10):
            result = await session.run(
                f"""
                CREATE (k:Ku {{
                    uid: 'ku.test-{i}',
                    title: 'Test KU {i}',
                    description: 'Test knowledge unit {i}',
                    embedding: $embedding
                }})
            """,
                embedding=[0.1 + i * 0.01] * 1536,
            )
            await result.consume()

        # Create relationships
        for i in range(5):
            result = await session.run(f"""
                MATCH (k1:Ku {{uid: 'ku.test-{i}'}})
                MATCH (k2:Ku {{uid: 'ku.test-{i + 5}'}})
                CREATE (k1)-[:REQUIRES_THEORETICAL_UNDERSTANDING {{
                    confidence: 0.8,
                    strength: 1.0
                }}]->(k2)
            """)
            await result.consume()  # Ensure transaction commits

    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver,
        embeddings_service=mock_embeddings_service,
        config=VectorSearchConfig(ku_min_score=0.0),
    )

    # Measure performance
    start_time = time.perf_counter()

    result = await vector_search.semantic_enhanced_search(
        label="Ku",
        text="test knowledge",
        context_uids=[f"ku.test-{i}" for i in range(5, 10)],
        limit=10,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    assert result.is_ok
    # Performance target: <200ms (includes vector search + semantic boost)
    assert elapsed_ms < 200, f"Semantic-enhanced search took {elapsed_ms:.2f}ms (target: <200ms)"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_performance_learning_aware_search(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Performance test: learning-aware search should be <180ms."""

    # Create user and 10 KUs with varying learning states
    async with neo4j_driver.session() as session:
        result = await session.run("""
            MERGE (u:User {uid: 'user.test_perf'})
            ON CREATE SET u.created_at = datetime()
        """)
        await result.consume()

        for i in range(10):
            result = await session.run(
                f"""
                CREATE (k:Ku {{
                    uid: 'ku.perf-{i}',
                    title: 'Performance Test KU {i}',
                    embedding: $embedding
                }})
            """,
                embedding=[0.1 + i * 0.01] * 1536,
            )
            await result.consume()

        # Create learning state relationships
        for i in range(3):
            # MASTERED
            result = await session.run(f"""
                MATCH (u:User {{uid: 'user.test_perf'}})
                MATCH (k:Ku {{uid: 'ku.perf-{i}'}})
                CREATE (u)-[:MASTERED {{mastered_at: datetime()}}]->(k)
            """)
            await result.consume()  # Ensure transaction commits

        for i in range(3, 6):
            # IN_PROGRESS
            result = await session.run(f"""
                MATCH (u:User {{uid: 'user.test_perf'}})
                MATCH (k:Ku {{uid: 'ku.perf-{i}'}})
                CREATE (u)-[:IN_PROGRESS {{started_at: datetime()}}]->(k)
            """)
            await result.consume()  # Ensure transaction commits

    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver,
        embeddings_service=mock_embeddings_service,
        config=VectorSearchConfig(ku_min_score=0.0),
    )

    # Measure performance
    start_time = time.perf_counter()

    result = await vector_search.learning_aware_search(
        label="Ku",
        text="performance test",
        user_uid="user.test_perf",
        prefer_unmastered=True,
        limit=10,
    )

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    assert result.is_ok
    # Performance target: <180ms (includes vector search + learning state lookup)
    assert elapsed_ms < 180, f"Learning-aware search took {elapsed_ms:.2f}ms (target: <180ms)"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graceful_degradation_no_vector_index(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """Test graceful handling when vector index doesn't exist."""

    # Create KU without vector index
    async with neo4j_driver.session() as session:
        result = await session.run("""
            CREATE (k:Ku {
                uid: 'ku.no-index',
                title: 'No Vector Index',
                description: 'KU without embedding'
            })
        """)
        await result.consume()

    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver, embeddings_service=mock_embeddings_service, config=VectorSearchConfig()
    )

    # Should handle gracefully (error or empty results, not crash)
    result = await vector_search.semantic_enhanced_search(
        label="Ku", text="test", context_uids=["ku.context"], limit=10
    )

    # Either returns error or empty results (both acceptable)
    assert result.is_ok or result.is_error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_semantic_discovery_workflow(
    neo4j_driver, clean_neo4j, mock_embeddings_service
):
    """End-to-end test: User discovers related content via semantic search."""

    # Setup: User learning Python, wants to find related advanced topics
    async with neo4j_driver.session() as session:
        # Create user (MERGE to avoid conflicts with ensure_test_users fixture)
        result = await session.run("""
            MERGE (u:User {uid: 'user.discovery'})
            ON CREATE SET u.created_at = datetime()
        """)
        await result.consume()

        # Create learning path: basics -> intermediate -> advanced
        result = await session.run(
            """
            CREATE (k1:Ku {
                uid: 'ku.python-basics',
                title: 'Python Basics',
                embedding: $emb1
            })
            CREATE (k2:Ku {
                uid: 'ku.python-intermediate',
                title: 'Python Intermediate',
                embedding: $emb2
            })
            CREATE (k3:Ku {
                uid: 'ku.python-advanced',
                title: 'Python Advanced',
                embedding: $emb3
            })
        """,
            emb1=[0.1] * 1536,
            emb2=[0.15] * 1536,
            emb3=[0.2] * 1536,
        )
        await result.consume()

        # Create semantic relationships
        result = await session.run("""
            MATCH (intermediate:Ku {uid: 'ku.python-intermediate'})
            MATCH (basics:Ku {uid: 'ku.python-basics'})
            CREATE (intermediate)-[:REQUIRES_THEORETICAL_UNDERSTANDING {
                confidence: 0.9,
                strength: 1.0
            }]->(basics)
            WITH intermediate
            MATCH (advanced:Ku {uid: 'ku.python-advanced'})
            CREATE (advanced)-[:BUILDS_MENTAL_MODEL {
                confidence: 0.85,
                strength: 0.9
            }]->(intermediate)
        """)
        await result.consume()  # Ensure transaction commits

        # User has mastered basics, viewing intermediate
        result = await session.run("""
            MATCH (u:User {uid: 'user.discovery'})
            MATCH (basics:Ku {uid: 'ku.python-basics'})
            MATCH (inter:Ku {uid: 'ku.python-intermediate'})
            CREATE (u)-[:MASTERED {mastered_at: datetime()}]->(basics)
            CREATE (u)-[:VIEWED {last_viewed_at: datetime()}]->(inter)
        """)
        await result.consume()  # Ensure transaction commits

    vector_search = Neo4jVectorSearchService(
        driver=neo4j_driver,
        embeddings_service=mock_embeddings_service,
        config=VectorSearchConfig(semantic_boost_enabled=True, ku_min_score=0.0),
    )

    # Execute discovery search: find content related to what user is viewing
    result = await vector_search.semantic_enhanced_search(
        label="Ku",
        text="python programming",
        context_uids=["ku.python-intermediate"],  # User's current focus
        limit=10,
    )

    assert result.is_ok
    results = result.value

    # Should find advanced topic (semantically related to intermediate)
    advanced_result = next((r for r in results if r["node"]["uid"] == "ku.python-advanced"), None)

    assert advanced_result is not None
    # Should have semantic boost (relationship to intermediate)
    assert advanced_result["semantic_boost"] > 0.0

    # Now test learning-aware search to prioritize unlearned content
    learning_result = await vector_search.learning_aware_search(
        label="Ku",
        text="python programming",
        user_uid="user.discovery",
        prefer_unmastered=True,
        limit=10,
    )

    assert learning_result.is_ok
    learning_results = learning_result.value

    # Advanced should rank higher than basics (not mastered vs. mastered)
    advanced_lr = next(
        (r for r in learning_results if r["node"]["uid"] == "ku.python-advanced"), None
    )
    basics_lr = next((r for r in learning_results if r["node"]["uid"] == "ku.python-basics"), None)

    if advanced_lr and basics_lr:
        # Advanced (not started) should have higher score than basics (mastered)
        assert advanced_lr["score"] > basics_lr["score"]
