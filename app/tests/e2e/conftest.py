"""
E2E Test Fixtures
=================

Imports fixtures from integration tests for use in E2E tests.

E2E tests use the same Neo4j testcontainer and fixtures as integration tests,
but test complete workflows from start to finish.
"""

import pytest_asyncio

# Import all integration test fixtures for E2E tests
from tests.integration.conftest import (
    clean_neo4j,
    create_moc_test_user,
    create_relationship,
    create_test_users,
    ensure_test_users,
    events_backend,
    goals_backend,
    habits_backend,
    ingestion_service,
    ku_backend,
    lp_relationship_service,
    mock_graph_intel,
    mock_intelligence_service,
    neo4j_container,
    neo4j_driver,
    neo4j_uri,
    populated_test_data,
    tasks_backend,
    temp_yaml_dir,
    test_user,
    user_service,
)

# ========================================================================
# E2E-SPECIFIC FIXTURES (Embedding Worker - January 2026)
# ========================================================================


@pytest_asyncio.fixture
async def event_bus():
    """Create event bus for e2e tests."""
    from adapters.infrastructure.event_bus import InMemoryEventBus

    return InMemoryEventBus()


@pytest_asyncio.fixture
async def embeddings_service():
    """Mock embeddings service for e2e tests — avoids real OpenAI calls."""
    from unittest.mock import Mock

    from core.utils.result_simplified import Result

    mock = Mock()
    mock.model = "BAAI/bge-large-en-v1.5"

    async def fake_batch_embeddings(texts: list[str]) -> Result:
        fake_vector = [0.1] * 1024
        return Result.ok([fake_vector for _ in texts])

    mock.create_batch_embeddings = fake_batch_embeddings
    return mock


@pytest_asyncio.fixture
async def embedding_worker(event_bus, embeddings_service, neo4j_driver):
    """Create embedding background worker for e2e tests."""
    from unittest.mock import Mock

    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.services.background.embedding_worker import EmbeddingBackgroundWorker

    # Mock config for embedding version
    mock_config = Mock()
    mock_config.genai.embedding_version = "v1"

    return EmbeddingBackgroundWorker(
        event_bus=event_bus,
        embeddings_service=embeddings_service,
        executor=Neo4jQueryExecutor(neo4j_driver),
        config=mock_config,
        batch_size=25,
        batch_interval_seconds=2,  # Short interval for tests (production uses 30s)
    )


# Re-export all fixtures so they're available to E2E tests
__all__ = [
    "neo4j_container",
    "neo4j_uri",
    "neo4j_driver",
    "ensure_test_users",
    "clean_neo4j",
    "temp_yaml_dir",
    "ku_backend",
    "mock_intelligence_service",
    "mock_graph_intel",
    # "article_service",  # Not defined in this conftest
    "ingestion_service",
    "tasks_backend",
    "events_backend",
    "goals_backend",
    "habits_backend",
    "test_user",
    "user_service",
    "create_test_users",
    "create_moc_test_user",
    "populated_test_data",
    "create_relationship",
    "lp_relationship_service",
    # E2E-specific fixtures
    "event_bus",
    "embeddings_service",
    "embedding_worker",
]
