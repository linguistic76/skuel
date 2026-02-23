"""
Relationship-First API Tests
============================

Tests for the fluent interface for Neo4j relationship operations.

Date: October 26, 2025
Updated: October 29, 2025 - Removed TraversalBuilder tests (archived)
"""

from typing import TYPE_CHECKING

import pytest

from adapters.persistence.neo4j.relationship_builders import RelationshipBuilder
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.task.task import Task as TaskPure

if TYPE_CHECKING:
    from unittest.mock import MagicMock


@pytest.mark.asyncio
class TestRelationshipFirstAPI:
    """Test suite for relationship-first fluent API."""

    async def test_relate_returns_builder(self, mock_driver):
        """Test that relate() returns a RelationshipBuilder instance."""
        backend = UniversalNeo4jBackend[TaskPure](mock_driver, "Ku", TaskPure)

        builder = backend.relate()

        assert isinstance(builder, RelationshipBuilder)
        assert builder._driver == mock_driver

    async def test_fluent_relationship_creation_syntax(self, mock_driver):
        """Test that the fluent API syntax matches the expected pattern."""
        backend = UniversalNeo4jBackend[TaskPure](mock_driver, "Ku", TaskPure)

        # Verify the syntax compiles and creates the expected chain
        builder = (
            backend.relate()
            .from_node("task.123")
            .via("APPLIES_KNOWLEDGE")
            .to_node("ku.456")
            .with_metadata(confidence=0.85, evidence="Applied in task")
        )

        # Verify builder state
        assert builder._from_uid == "task.123"
        assert builder._relationship_type == "APPLIES_KNOWLEDGE"
        assert builder._to_uid == "ku.456"
        assert builder._metadata["confidence"] == 0.85
        assert builder._metadata["evidence"] == "Applied in task"

    async def test_relationship_builder_with_labels(self, mock_driver):
        """Test relationship builder with node label optimization."""
        backend = UniversalNeo4jBackend[TaskPure](mock_driver, "Ku", TaskPure)

        builder = (
            backend.relate()
            .from_node("task.123", labels=["Ku"])
            .via("APPLIES_KNOWLEDGE")
            .to_node("ku.456", labels=["Ku"])
        )

        assert builder._from_labels == ["Ku"]
        assert builder._to_labels == ["Ku"]


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_driver() -> "MagicMock":
    """Create a mock Neo4j driver for testing."""
    from unittest.mock import AsyncMock, MagicMock

    driver = MagicMock()
    driver.session = MagicMock(return_value=AsyncMock())

    return driver


# ============================================================================
# INTEGRATION TEST NOTES
# ============================================================================

"""
Integration Tests (requires running Neo4j instance):

These tests verify the actual Neo4j operations. Run with:
    pytest tests/integration/test_relationship_first_api_integration.py

1. test_create_relationship_integration()
   - Create actual relationship in Neo4j
   - Verify relationship exists
   - Verify metadata is stored correctly

2. test_delete_relationship_integration()
   - Create relationship
   - Delete using fluent API
   - Verify relationship no longer exists

3. test_bidirectional_relationships_integration()
   - Create bidirectional relationships
   - Verify relationships exist in both directions
   - Test relationship metadata
"""
