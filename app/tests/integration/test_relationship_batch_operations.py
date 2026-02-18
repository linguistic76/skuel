"""
Integration tests for relationship batch operations.

Tests get_relationships_batch() and count_relationships_batch() protocol methods
for efficient batch queries on relationship edges.

Date: November 16, 2025
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.ku.ku_task import TaskKu as Task


@pytest.mark.asyncio
class TestRelationshipBatchOperations:
    """Integration tests for batch relationship query operations."""

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with clean database."""
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Ku", Task, default_filters={"ku_type": "task"}
        )

    async def test_get_relationships_batch_empty(self, tasks_backend):
        """Test batch metadata query with empty list."""
        result = await tasks_backend.get_relationships_batch([])
        assert result.is_ok
        assert result.value == []

    async def test_get_relationships_batch_nonexistent(self, tasks_backend):
        """Test batch metadata query for non-existent relationships."""
        relationships = [
            ("task:nonexistent1", "ku:python", "APPLIES_KNOWLEDGE"),
            ("task:nonexistent2", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ("task:nonexistent3", "ku:databases", "APPLIES_KNOWLEDGE"),
        ]
        result = await tasks_backend.get_relationships_batch(relationships)

        assert result.is_ok
        assert len(result.value) == 3
        # All should be empty dicts (relationships don't exist)
        for metadata in result.value:
            assert metadata == {}

    async def test_count_relationships_batch_empty(self, tasks_backend):
        """Test batch counting with empty list."""
        result = await tasks_backend.count_relationships_batch([])
        assert result.is_ok
        assert result.value == {}

    async def test_count_relationships_batch_nonexistent(self, tasks_backend):
        """Test batch counting for non-existent entities."""
        requests = [
            ("task:nonexistent1", "APPLIES_KNOWLEDGE", "outgoing"),
            ("task:nonexistent2", "REQUIRES_KNOWLEDGE", "outgoing"),
            ("ku:nonexistent", "ENABLES", "outgoing"),
        ]
        result = await tasks_backend.count_relationships_batch(requests)

        assert result.is_ok
        # All counts should be 0
        for count in result.value.values():
            assert count == 0

        # Should have entries for all requests
        assert len(result.value) == 3

    async def test_count_relationships_batch_different_directions(self, tasks_backend):
        """Test batch counting with different direction parameters."""
        requests = [
            ("task:123", "APPLIES_KNOWLEDGE", "outgoing"),
            ("task:456", "REQUIRES_KNOWLEDGE", "incoming"),
            ("ku:python", "ENABLES", "both"),
        ]
        result = await tasks_backend.count_relationships_batch(requests)

        assert result.is_ok
        assert len(result.value) == 3

        # Verify all keys are present
        assert ("task:123", "APPLIES_KNOWLEDGE", "outgoing") in result.value
        assert ("task:456", "REQUIRES_KNOWLEDGE", "incoming") in result.value
        assert ("ku:python", "ENABLES", "both") in result.value

    async def test_count_relationships_batch_default_direction(self, tasks_backend):
        """Test batch counting with None direction (defaults to outgoing)."""
        requests = [
            ("task:123", "APPLIES_KNOWLEDGE", None),
            ("task:456", "REQUIRES_KNOWLEDGE", None),
        ]
        result = await tasks_backend.count_relationships_batch(requests)

        assert result.is_ok
        # None should be treated as "outgoing"
        assert ("task:123", "APPLIES_KNOWLEDGE", "outgoing") in result.value
        assert ("task:456", "REQUIRES_KNOWLEDGE", "outgoing") in result.value
