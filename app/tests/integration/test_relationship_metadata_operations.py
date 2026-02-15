"""
Integration tests for relationship metadata operations.

Tests get_relationship_metadata() and update_relationship_properties()
protocol methods for querying and updating edge properties.

Date: November 16, 2025
"""

from datetime import date, datetime

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, KuStatus, Priority, SELCategory
from core.models.ku.ku import Ku
from core.models.ku.ku import Ku as Task
from core.models.relationship_names import RelationshipName
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestRelationshipMetadataOperations:
    """Integration tests for relationship metadata query and update operations."""

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with clean database."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Task", Ku)

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver):
        """Create KU backend for creating knowledge units."""
        return UniversalNeo4jBackend[Ku](neo4j_driver, "Ku", Ku)

    @pytest_asyncio.fixture
    async def tasks_service(self, tasks_backend):
        """Create TasksCoreService."""
        return TasksCoreService(backend=tasks_backend)

    async def test_get_metadata_nonexistent_relationship(self, tasks_backend):
        """Test getting metadata for non-existent relationship returns None."""
        result = await tasks_backend.get_relationship_metadata(
            from_uid="task:nonexistent",
            to_uid="ku:nonexistent",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert result.is_ok
        assert result.value is None

    async def test_get_metadata_with_properties(self, tasks_backend, tasks_service, ku_backend):
        """Test getting metadata from relationship with properties."""
        # Create knowledge unit first
        ku = Ku(
            uid="ku:python",
            title="Python",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create a task
        task = Task(
            uid="task:metadata_test",
            title="Test Metadata",
            description="Test getting metadata",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=KuStatus.DRAFT,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create relationship with metadata (tuples use strings)
        properties = {
            "confidence": 0.85,
            "strength": 2.5,
            "created_at": datetime.now().isoformat(),
        }
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:metadata_test", "ku:python", "APPLIES_KNOWLEDGE", properties)]
        )
        assert create_rel_result.is_ok

        # Get metadata (methods use enums)
        metadata_result = await tasks_backend.get_relationship_metadata(
            from_uid="task:metadata_test",
            to_uid="ku:python",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert metadata_result.is_ok
        assert metadata_result.value is not None

        # Verify properties
        metadata = metadata_result.value
        assert metadata["confidence"] == 0.85
        assert metadata["strength"] == 2.5
        assert "created_at" in metadata

    async def test_update_properties_nonexistent_relationship(self, tasks_backend):
        """Test updating properties on non-existent relationship fails."""
        result = await tasks_backend.update_relationship_properties(
            from_uid="task:nonexistent",
            to_uid="ku:nonexistent",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            properties={"confidence": 0.9},
        )
        assert result.is_error
        # Should get a not found error

    async def test_update_properties_empty_dict(self, tasks_backend):
        """Test updating with empty properties dict succeeds (no-op)."""
        result = await tasks_backend.update_relationship_properties(
            from_uid="task:any",
            to_uid="ku:any",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            properties={},
        )
        assert result.is_ok
        assert result.value is True

    async def test_update_single_property(self, tasks_backend, tasks_service, ku_backend):
        """Test updating a single property preserves others."""
        # Create knowledge unit first
        ku = Ku(
            uid="ku:algorithms",
            title="Algorithms",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create task (HIGH priority requires due_date)
        task = Task(
            uid="task:update_single",
            title="Test Update Single",
            description="Test single property update",
            user_uid="user.test",
            priority=Priority.HIGH,
            due_date=date.today(),
            status=KuStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create relationship with multiple properties (tuples use strings)
        initial_props = {"confidence": 0.8, "strength": 1.5, "weight": 10}
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:update_single", "ku:algorithms", "APPLIES_KNOWLEDGE", initial_props)]
        )
        assert create_rel_result.is_ok

        # Update only confidence (methods use enums)
        update_result = await tasks_backend.update_relationship_properties(
            from_uid="task:update_single",
            to_uid="ku:algorithms",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            properties={"confidence": 0.95},
        )
        assert update_result.is_ok

        # Get metadata and verify
        metadata_result = await tasks_backend.get_relationship_metadata(
            from_uid="task:update_single",
            to_uid="ku:algorithms",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert metadata_result.is_ok
        metadata = metadata_result.value

        # Confidence updated, others preserved
        assert metadata["confidence"] == 0.95
        assert metadata["strength"] == 1.5
        assert metadata["weight"] == 10

    async def test_update_multiple_properties(self, tasks_backend, tasks_service, ku_backend):
        """Test updating multiple properties at once."""
        # Create knowledge unit first
        ku = Ku(
            uid="ku:databases",
            title="Databases",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create task
        task = Task(
            uid="task:update_multiple",
            title="Test Update Multiple",
            description="Test multiple property updates",
            user_uid="user.test",
            priority=Priority.LOW,
            status=KuStatus.DRAFT,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create relationship with initial properties (tuples use strings)
        initial_props = {
            "confidence": 0.5,
            "strength": 1.0,
            "traversal_count": 0,
            "last_updated": "2025-01-01",
        }
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:update_multiple", "ku:databases", "REQUIRES_KNOWLEDGE", initial_props)]
        )
        assert create_rel_result.is_ok

        # Update multiple properties (methods use enums)
        now = datetime.now().isoformat()
        update_result = await tasks_backend.update_relationship_properties(
            from_uid="task:update_multiple",
            to_uid="ku:databases",
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
            properties={
                "confidence": 0.9,
                "traversal_count": 5,
                "last_updated": now,
            },
        )
        assert update_result.is_ok

        # Get metadata and verify
        metadata_result = await tasks_backend.get_relationship_metadata(
            from_uid="task:update_multiple",
            to_uid="ku:databases",
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
        )
        assert metadata_result.is_ok
        metadata = metadata_result.value

        # Updated properties
        assert metadata["confidence"] == 0.9
        assert metadata["traversal_count"] == 5
        assert metadata["last_updated"] == now
        # Preserved property
        assert metadata["strength"] == 1.0

    async def test_add_new_properties(self, tasks_backend, tasks_service, ku_backend):
        """Test adding new properties to relationship that didn't have them."""
        # Create knowledge unit first
        ku = Ku(
            uid="ku:testing",
            title="Testing",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create task
        task = Task(
            uid="task:add_props",
            title="Test Add Properties",
            description="Test adding new properties",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=KuStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create relationship with minimal properties (tuples use strings)
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:add_props", "ku:testing", "APPLIES_KNOWLEDGE", {"confidence": 0.7})]
        )
        assert create_rel_result.is_ok

        # Add new properties (methods use enums)
        update_result = await tasks_backend.update_relationship_properties(
            from_uid="task:add_props",
            to_uid="ku:testing",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            properties={
                "new_field": "new_value",
                "complexity_score": 7.5,
                "tags": ["important", "review"],
            },
        )
        assert update_result.is_ok

        # Get metadata and verify
        metadata_result = await tasks_backend.get_relationship_metadata(
            from_uid="task:add_props",
            to_uid="ku:testing",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert metadata_result.is_ok
        metadata = metadata_result.value

        # Original property preserved
        assert metadata["confidence"] == 0.7
        # New properties added
        assert metadata["new_field"] == "new_value"
        assert metadata["complexity_score"] == 7.5
        assert metadata["tags"] == ["important", "review"]

    async def test_increment_counter_pattern(self, tasks_backend, tasks_service, ku_backend):
        """Test common pattern: get, increment, update."""
        # Create knowledge unit first
        ku = Ku(
            uid="ku:patterns",
            title="Patterns",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create task
        task = Task(
            uid="task:counter",
            title="Test Counter",
            description="Test counter increment pattern",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=KuStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create relationship with counter (tuples use strings)
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:counter", "ku:patterns", "APPLIES_KNOWLEDGE", {"access_count": 0})]
        )
        assert create_rel_result.is_ok

        # Simulate 3 accesses (get, increment, update pattern)
        for _ in range(3):
            # Get current count (methods use enums)
            metadata_result = await tasks_backend.get_relationship_metadata(
                from_uid="task:counter",
                to_uid="ku:patterns",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            )
            assert metadata_result.is_ok
            current_count = metadata_result.value["access_count"]

            # Increment
            update_result = await tasks_backend.update_relationship_properties(
                from_uid="task:counter",
                to_uid="ku:patterns",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                properties={"access_count": current_count + 1},
            )
            assert update_result.is_ok

        # Verify final count
        metadata_result = await tasks_backend.get_relationship_metadata(
            from_uid="task:counter",
            to_uid="ku:patterns",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert metadata_result.is_ok
        assert metadata_result.value["access_count"] == 3
