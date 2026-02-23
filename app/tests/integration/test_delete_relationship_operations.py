"""
Integration tests for delete relationship operations.

Tests the delete_relationship() and delete_relationships_batch() protocol methods
added to address the architectural gap in relationship management.

Date: November 16, 2025
"""

from datetime import date

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, EntityStatus, Priority, SELCategory
from core.models.curriculum.curriculum import Curriculum
from core.models.task.task import Task as Task
from core.models.relationship_names import RelationshipName
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestDeleteRelationshipOperations:
    """Integration tests for relationship deletion operations."""

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with clean database."""
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"ku_type": "task"}
        )

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver):
        """Create KU backend for creating knowledge units."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def tasks_service(self, tasks_backend):
        """Create TasksCoreService."""
        return TasksCoreService(backend=tasks_backend)

    async def test_delete_single_relationship(self, tasks_backend, tasks_service, ku_backend):
        """Test deleting a single relationship."""
        # Create a knowledge unit first
        ku = Curriculum(
            uid="ku:test-knowledge",
            title="Test Knowledge",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku_result = await ku_backend.create(ku)
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"

        # Create a task
        task = Task(
            uid="task:delete_test_1",
            title="Test Delete Relationship",
            description="Test task for delete",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create a relationship (tuples use strings)
        create_rel_result = await tasks_backend.create_relationships_batch(
            [("task:delete_test_1", "ku:test-knowledge", "APPLIES_KNOWLEDGE", None)]
        )
        assert create_rel_result.is_ok
        assert create_rel_result.value == 1

        # Verify relationship exists (methods use enums)
        has_rel_result = await tasks_backend.has_relationship(
            from_uid="task:delete_test_1",
            to_uid="ku:test-knowledge",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert has_rel_result.is_ok
        assert has_rel_result.value is True

        # Delete the relationship
        delete_result = await tasks_backend.delete_relationship(
            from_uid="task:delete_test_1",
            to_uid="ku:test-knowledge",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify relationship no longer exists
        has_rel_after_result = await tasks_backend.has_relationship(
            from_uid="task:delete_test_1",
            to_uid="ku:test-knowledge",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert has_rel_after_result.is_ok
        assert has_rel_after_result.value is False

    async def test_delete_relationship_idempotent(self, tasks_backend):
        """Test that deleting non-existent relationship succeeds (idempotent)."""
        # Delete a relationship that doesn't exist
        delete_result = await tasks_backend.delete_relationship(
            from_uid="task:nonexistent",
            to_uid="ku:nonexistent",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        # Should succeed even if relationship didn't exist
        assert delete_result.is_ok
        assert delete_result.value is True

    async def test_delete_relationships_batch(self, tasks_backend, tasks_service, ku_backend):
        """Test batch deletion of multiple relationships."""
        # Create knowledge units first
        for ku_uid, title in [
            ("ku:python", "Python"),
            ("ku:algorithms", "Algorithms"),
            ("ku:databases", "Databases"),
        ]:
            ku = Curriculum(
                uid=ku_uid,
                title=title,
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            await ku_backend.create(ku)

        # Create a task (with due_date since HIGH priority)
        task = Task(
            uid="task:batch_delete_test",
            title="Test Batch Delete",
            description="Test task for batch delete",
            user_uid="user.test",
            priority=Priority.HIGH,
            due_date=date.today(),
            status=EntityStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create multiple relationships (tuples use strings)
        relationships = [
            ("task:batch_delete_test", "ku:python", "APPLIES_KNOWLEDGE", None),
            ("task:batch_delete_test", "ku:algorithms", "REQUIRES_KNOWLEDGE", None),
            ("task:batch_delete_test", "ku:databases", "APPLIES_KNOWLEDGE", None),
        ]
        create_result = await tasks_backend.create_relationships_batch(relationships)
        assert create_result.is_ok
        assert create_result.value == 3

        # Verify all relationships exist (use enums for methods)
        rel_types = [
            RelationshipName.APPLIES_KNOWLEDGE,
            RelationshipName.REQUIRES_KNOWLEDGE,
            RelationshipName.APPLIES_KNOWLEDGE,
        ]
        for (from_uid, to_uid, _, _), rel_type in zip(relationships, rel_types, strict=False):
            has_result = await tasks_backend.has_relationship(from_uid, to_uid, rel_type)
            assert has_result.is_ok
            assert has_result.value is True

        # Delete all relationships in batch (tuples use strings)
        rels_to_delete = [
            (from_uid, to_uid, rel_type_str) for from_uid, to_uid, rel_type_str, _ in relationships
        ]
        delete_result = await tasks_backend.delete_relationships_batch(rels_to_delete)
        assert delete_result.is_ok
        assert delete_result.value == 3  # All 3 deleted

        # Verify all relationships are gone
        for (from_uid, to_uid, _, _), rel_type in zip(relationships, rel_types, strict=False):
            has_result = await tasks_backend.has_relationship(from_uid, to_uid, rel_type)
            assert has_result.is_ok
            assert has_result.value is False

    async def test_delete_relationships_batch_partial(
        self, tasks_backend, tasks_service, ku_backend
    ):
        """Test batch delete with mix of existing and non-existing relationships."""
        # Create knowledge units first
        for ku_uid, title in [("ku:existing1", "Existing 1"), ("ku:existing2", "Existing 2")]:
            ku = Curriculum(
                uid=ku_uid,
                title=title,
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            await ku_backend.create(ku)

        # Create a task
        task = Task(
            uid="task:partial_delete_test",
            title="Test Partial Delete",
            description="Test task for partial batch delete",
            user_uid="user.test",
            priority=Priority.LOW,
            status=EntityStatus.DRAFT,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create only 2 relationships (tuples use strings)
        existing_rels = [
            ("task:partial_delete_test", "ku:existing1", "APPLIES_KNOWLEDGE", None),
            ("task:partial_delete_test", "ku:existing2", "REQUIRES_KNOWLEDGE", None),
        ]
        create_result = await tasks_backend.create_relationships_batch(existing_rels)
        assert create_result.is_ok
        assert create_result.value == 2

        # Try to delete 4 relationships (2 exist, 2 don't) - tuples use strings
        rels_to_delete = [
            ("task:partial_delete_test", "ku:existing1", "APPLIES_KNOWLEDGE"),
            ("task:partial_delete_test", "ku:existing2", "REQUIRES_KNOWLEDGE"),
            ("task:partial_delete_test", "ku:nonexistent1", "APPLIES_KNOWLEDGE"),
            ("task:partial_delete_test", "ku:nonexistent2", "REQUIRES_KNOWLEDGE"),
        ]
        delete_result = await tasks_backend.delete_relationships_batch(rels_to_delete)
        assert delete_result.is_ok
        # Should only delete the 2 that existed
        assert delete_result.value == 2

    async def test_delete_relationships_batch_empty(self, tasks_backend):
        """Test batch delete with empty list."""
        delete_result = await tasks_backend.delete_relationships_batch([])
        assert delete_result.is_ok
        assert delete_result.value == 0

    async def test_delete_relationship_count_related(
        self, tasks_backend, tasks_service, ku_backend
    ):
        """Test that delete operations work with count_related."""
        # Create knowledge units first
        for ku_uid, title in [
            ("ku:python", "Python"),
            ("ku:algorithms", "Algorithms"),
            ("ku:databases", "Databases"),
        ]:
            ku = Curriculum(
                uid=ku_uid,
                title=title,
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            await ku_backend.create(ku)

        # Create a task
        task = Task(
            uid="task:count_delete_test",
            title="Test Delete with Count",
            description="Test delete with count operations",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=EntityStatus.ACTIVE,
        )
        create_result = await tasks_service.create(task)
        assert create_result.is_ok

        # Create 3 APPLIES_KNOWLEDGE relationships (tuples use strings)
        relationships = [
            ("task:count_delete_test", "ku:python", "APPLIES_KNOWLEDGE", None),
            ("task:count_delete_test", "ku:algorithms", "APPLIES_KNOWLEDGE", None),
            ("task:count_delete_test", "ku:databases", "APPLIES_KNOWLEDGE", None),
        ]
        create_result = await tasks_backend.create_relationships_batch(relationships)
        assert create_result.is_ok

        # Count should be 3 (methods use enums)
        count_result = await tasks_backend.count_related(
            uid="task:count_delete_test",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            direction="outgoing",
        )
        assert count_result.is_ok
        assert count_result.value == 3

        # Delete one relationship
        delete_result = await tasks_backend.delete_relationship(
            from_uid="task:count_delete_test",
            to_uid="ku:python",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert delete_result.is_ok

        # Count should now be 2
        count_result = await tasks_backend.count_related(
            uid="task:count_delete_test",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            direction="outgoing",
        )
        assert count_result.is_ok
        assert count_result.value == 2

        # Delete remaining 2 in batch (tuples use strings)
        delete_result = await tasks_backend.delete_relationships_batch(
            [
                ("task:count_delete_test", "ku:algorithms", "APPLIES_KNOWLEDGE"),
                ("task:count_delete_test", "ku:databases", "APPLIES_KNOWLEDGE"),
            ]
        )
        assert delete_result.is_ok
        assert delete_result.value == 2

        # Count should now be 0
        count_result = await tasks_backend.count_related(
            uid="task:count_delete_test",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            direction="outgoing",
        )
        assert count_result.is_ok
        assert count_result.value == 0
