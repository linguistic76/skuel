"""
End-to-End Fixtures
===================

Local to ``tests/integration/e2e/``: the embedding background worker over a
real ``EmbeddingsBackend``. Everything else these tests use — the session
testcontainer (``neo4j_driver``), ``clean_neo4j``, ``ku_backend``, ``event_bus``
— comes from ``tests/integration/conftest.py`` by pytest's conftest discovery;
nothing is re-imported here.

The graph-backed service deliberately does NOT reuse the parent conftest's
``embeddings_service`` name: that one is mock-backed (tests override its
methods), this one writes vectors and version metadata into the container.
One name, one thing.
"""

import pytest


@pytest.fixture
def graph_backed_embeddings_service(neo4j_driver):
    """Real EmbeddingsService over a real EmbeddingsBackend, with a stubbed model call.

    Only the inference client's ``embed`` is stubbed (no embedding-API calls);
    the service + backend are real and wired to the test container, so the
    worker's per-item generation (create_embedding) and storage
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


@pytest.fixture
def embedding_worker(event_bus, graph_backed_embeddings_service):
    """Embedding background worker on the shared bus, batching every 2 s (production: 30 s)."""
    from core.services.background.embedding_worker import EmbeddingBackgroundWorker

    return EmbeddingBackgroundWorker(
        event_bus=event_bus,
        embeddings_service=graph_backed_embeddings_service,
        batch_size=25,
        batch_interval_seconds=2,
    )
