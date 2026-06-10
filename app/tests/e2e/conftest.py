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
async def embeddings_service(neo4j_driver):
    """Real EmbeddingsService with Neo4j-backed storage and a stubbed model call.

    Only the inference client's ``embed`` is stubbed (no real embedding-API
    calls); the service + backend are real and wired to the test container, so
    the worker's per-item generation (create_embedding) and storage
    (store_embedding_with_metadata) paths run for real, writing vectors AND
    version/model metadata to Neo4j.
    """
    from unittest.mock import AsyncMock, MagicMock

    from adapters.persistence.neo4j.embeddings_backend import EmbeddingsBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.services.embeddings_service import EmbeddingsService
    from core.utils.result_simplified import Result

    mock_client = MagicMock()
    mock_client.model = "test-embedder"
    mock_client.dimension = 1024
    mock_client.max_input_chars = 2000
    mock_client.embed = AsyncMock(return_value=Result.ok([0.1] * 1024))

    return EmbeddingsService(
        backend=EmbeddingsBackend(executor=Neo4jQueryExecutor(neo4j_driver)),
        embedding_client=mock_client,
    )


@pytest_asyncio.fixture
async def embedding_worker(event_bus, embeddings_service, neo4j_driver):
    """Create embedding background worker for e2e tests."""
    from core.services.background.embedding_worker import EmbeddingBackgroundWorker

    return EmbeddingBackgroundWorker(
        event_bus=event_bus,
        embeddings_service=embeddings_service,
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
    # "lesson_service",  # Not defined in this conftest
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
