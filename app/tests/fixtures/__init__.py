"""
Test Fixtures - Service Factories & Mock Services
==================================================

Test infrastructure that mirrors production service composition.

This module provides factory functions for creating services in tests
using the same composition pattern as production, while allowing
behavior customization for testing.

Philosophy:
- Tests should use the same composition as production
- Service constructors create sub-components internally
- Factory functions provide mock backends/drivers
- Behavior can be customized per test without breaking encapsulation

Available Fixtures:
- service_factories: Mock service factories for domain services
- embedding_fixtures: Mock embeddings and vector search services

Usage:
    from tests.fixtures.service_factories import create_moc_service_for_testing
    from tests.fixtures.embedding_fixtures import services_with_embeddings

    def test_something(services_with_embeddings):
        service = create_moc_service_for_testing()
        # Test using service facade methods with mock AI services
"""

# Export fixtures for easy importing
from tests.fixtures.embedding_fixtures import (
    mock_embedding_vector,
    mock_embeddings_service,
    mock_embeddings_unavailable,
    mock_vector_search_service,
    mock_vector_search_unavailable,
    services_with_embeddings,
)
from tests.fixtures.service_factories import (
    create_adaptive_lp_facade_for_testing,
    create_askesis_user_context_for_testing,
    create_finance_service_for_testing,
    create_knowledge_state_for_testing,
    create_mock_backend,
    create_mock_backend_for_base_service,
    create_mock_driver,
    create_moc_service_for_testing,
    create_tasks_service_for_testing,
    create_unified_user_context_for_testing,
)

__all__ = [
    # Service factories
    "create_moc_service_for_testing",
    "create_unified_user_context_for_testing",
    "create_finance_service_for_testing",
    "create_tasks_service_for_testing",
    "create_adaptive_lp_facade_for_testing",
    "create_askesis_user_context_for_testing",
    "create_knowledge_state_for_testing",
    "create_mock_backend",
    "create_mock_backend_for_base_service",
    "create_mock_driver",
    # Embedding fixtures
    "mock_embedding_vector",
    "mock_embeddings_service",
    "mock_embeddings_unavailable",
    "mock_vector_search_service",
    "mock_vector_search_unavailable",
    "services_with_embeddings",
]
