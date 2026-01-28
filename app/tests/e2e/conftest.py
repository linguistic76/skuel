"""
E2E Test Fixtures
=================

Imports fixtures from integration tests for use in E2E tests.

E2E tests use the same Neo4j testcontainer and fixtures as integration tests,
but test complete workflows from start to finish.
"""

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
    ku_service,
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
    "ku_service",
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
]
