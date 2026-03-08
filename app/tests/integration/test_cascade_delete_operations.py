"""
Integration tests for cascade delete operations.

Tests the delete() method with cascade=True and cascade=False behaviors
in UniversalNeo4jBackend.

These tests verify the bug fix where cascade parameter was previously ignored.

Date: January 2026
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.curriculum import Curriculum
from core.models.enums import Domain, EntityStatus, Priority, SELCategory
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task as Task
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestCascadeDeleteTrue:
    """Integration tests for delete() with cascade=True."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def task_backend(self, neo4j_driver, clean_neo4j):
        """Create Task backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](
            neo4j_driver, "Entity", Curriculum, default_filters={"entity_type": "task"}
        )

    @pytest_asyncio.fixture
    async def tasks_service(self, task_backend):
        """Create TasksCoreService."""
        return TasksCoreService(backend=task_backend)

    async def test_cascade_delete_removes_entity(self, ku_backend):
        """Test cascade=True successfully deletes entity."""
        # Create entity
        ku = Curriculum(
            uid="ku:cascade-delete-1",
            title="To Delete",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        create_result = await ku_backend.create(ku)
        assert create_result.is_ok

        # Delete with cascade
        delete_result = await ku_backend.delete("ku:cascade-delete-1", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify entity is gone
        get_result = await ku_backend.get("ku:cascade-delete-1")
        assert get_result.is_ok
        assert get_result.value is None

    async def test_cascade_delete_removes_relationships(self, ku_backend):
        """Test cascade=True removes all relationships."""
        # Create two KUs with a relationship
        ku1 = Curriculum(
            uid="ku:cascade-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:cascade-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        # Create relationship (Entity uses REQUIRES_KNOWLEDGE for prerequisites)
        rel_result = await ku_backend.create_relationships_batch(
            [("ku:cascade-source", "ku:cascade-target", "REQUIRES_KNOWLEDGE", None)]
        )
        assert rel_result.is_ok

        # Verify relationship exists
        has_rel = await ku_backend.has_relationship(
            "ku:cascade-source", "ku:cascade-target", RelationshipName.REQUIRES_KNOWLEDGE
        )
        assert has_rel.is_ok
        assert has_rel.value is True

        # Delete source with cascade
        delete_result = await ku_backend.delete("ku:cascade-source", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify relationship is gone (source deleted)
        has_rel_after = await ku_backend.has_relationship(
            "ku:cascade-source", "ku:cascade-target", RelationshipName.REQUIRES_KNOWLEDGE
        )
        assert has_rel_after.is_ok
        assert has_rel_after.value is False

    async def test_cascade_delete_preserves_related_entities(self, ku_backend):
        """Test cascade=True does NOT delete connected entities."""
        # Create two KUs with a relationship
        ku1 = Curriculum(
            uid="ku:preserve-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:preserve-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        # Create relationship (Entity uses REQUIRES_KNOWLEDGE)
        await ku_backend.create_relationships_batch(
            [("ku:preserve-source", "ku:preserve-target", "REQUIRES_KNOWLEDGE", None)]
        )

        # Delete source with cascade
        await ku_backend.delete("ku:preserve-source", cascade=True)

        # Target entity should still exist
        get_target = await ku_backend.get("ku:preserve-target")
        assert get_target.is_ok
        assert get_target.value is not None
        assert get_target.value.uid == "ku:preserve-target"

    async def test_cascade_delete_multiple_relationships(self, ku_backend):
        """Test cascade=True works with multiple relationships."""
        # Create central node and many related nodes
        center = Curriculum(
            uid="ku:multi-center",
            title="Center",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(center)

        # Create 5 related nodes
        for i in range(5):
            related = Curriculum(
                uid=f"ku:multi-related-{i}",
                title=f"Related {i}",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            await ku_backend.create(related)

        # Create relationships to all (Entity uses REQUIRES_KNOWLEDGE)
        relationships = [
            ("ku:multi-center", f"ku:multi-related-{i}", "REQUIRES_KNOWLEDGE", None)
            for i in range(5)
        ]
        await ku_backend.create_relationships_batch(relationships)

        # Verify count before delete
        count_before = await ku_backend.count_related(
            "ku:multi-center", RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
        )
        assert count_before.is_ok
        assert count_before.value == 5

        # Delete center with cascade
        delete_result = await ku_backend.delete("ku:multi-center", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify center is gone
        get_center = await ku_backend.get("ku:multi-center")
        assert get_center.is_ok
        assert get_center.value is None

        # All related nodes should still exist
        for i in range(5):
            get_related = await ku_backend.get(f"ku:multi-related-{i}")
            assert get_related.is_ok
            assert get_related.value is not None

    async def test_cascade_delete_cross_domain(self, task_backend, ku_backend, tasks_service):
        """Test cascade=True cleans up cross-domain relationships."""
        # Create Task and KU
        task = Task(
            uid="task:cross-domain",
            title="Cross Domain Task",
            description="Test",
            user_uid="user.test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        await tasks_service.create(task)

        ku = Curriculum(
            uid="ku:cross-domain",
            title="Cross Domain KU",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku)

        # Create cross-domain relationship
        await task_backend.create_relationships_batch(
            [("task:cross-domain", "ku:cross-domain", "APPLIES_KNOWLEDGE", None)]
        )

        # Verify relationship exists
        has_rel = await task_backend.has_relationship(
            "task:cross-domain", "ku:cross-domain", RelationshipName.APPLIES_KNOWLEDGE
        )
        assert has_rel.is_ok
        assert has_rel.value is True

        # Delete task with cascade
        delete_result = await task_backend.delete("task:cross-domain", cascade=True)
        assert delete_result.is_ok

        # KU should still exist
        get_ku = await ku_backend.get("ku:cross-domain")
        assert get_ku.is_ok
        assert get_ku.value is not None


@pytest.mark.asyncio
class TestCascadeDeleteFalse:
    """Integration tests for delete() with cascade=False."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    async def test_non_cascade_delete_no_relationships(self, ku_backend):
        """Test cascade=False deletes entity with no relationships."""
        # Create isolated entity
        ku = Curriculum(
            uid="ku:isolated-delete",
            title="Isolated",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku)

        # Delete without cascade (should succeed - no relationships)
        delete_result = await ku_backend.delete("ku:isolated-delete", cascade=False)
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify entity is gone
        get_result = await ku_backend.get("ku:isolated-delete")
        assert get_result.is_ok
        assert get_result.value is None

    async def test_non_cascade_delete_with_relationships_fails(self, ku_backend):
        """Test cascade=False fails when entity has relationships."""
        # Create two KUs with a relationship
        ku1 = Curriculum(
            uid="ku:non-cascade-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:non-cascade-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        # Create relationship (Entity uses REQUIRES_KNOWLEDGE)
        await ku_backend.create_relationships_batch(
            [("ku:non-cascade-source", "ku:non-cascade-target", "REQUIRES_KNOWLEDGE", None)]
        )

        # Delete source WITHOUT cascade (should fail)
        delete_result = await ku_backend.delete("ku:non-cascade-source", cascade=False)
        assert delete_result.is_error

    async def test_non_cascade_delete_error_message(self, ku_backend):
        """Test cascade=False provides descriptive error message."""
        # Create KUs with relationship
        ku1 = Curriculum(
            uid="ku:error-msg-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:error-msg-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        await ku_backend.create_relationships_batch(
            [("ku:error-msg-source", "ku:error-msg-target", "REQUIRES_KNOWLEDGE", None)]
        )

        # Delete without cascade
        delete_result = await ku_backend.delete("ku:error-msg-source", cascade=False)

        assert delete_result.is_error
        error_msg = str(delete_result.error)
        # Error message should mention relationships
        assert "relationship" in error_msg.lower()
        # Error message should suggest using cascade=True
        assert "cascade" in error_msg.lower()

    async def test_non_cascade_delete_preserves_entity(self, ku_backend):
        """Test cascade=False preserves entity after failed delete."""
        # Create KUs with relationship
        ku1 = Curriculum(
            uid="ku:preserve-entity",
            title="Preserved",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:preserve-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        await ku_backend.create_relationships_batch(
            [("ku:preserve-entity", "ku:preserve-target", "REQUIRES_KNOWLEDGE", None)]
        )

        # Attempt delete without cascade (will fail)
        await ku_backend.delete("ku:preserve-entity", cascade=False)

        # Entity should still exist
        get_result = await ku_backend.get("ku:preserve-entity")
        assert get_result.is_ok
        assert get_result.value is not None
        assert get_result.value.title == "Preserved"

    async def test_non_cascade_delete_preserves_relationships(self, ku_backend):
        """Test cascade=False preserves relationships after failed delete."""
        # Create KUs with relationship
        ku1 = Curriculum(
            uid="ku:preserve-rel-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:preserve-rel-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        await ku_backend.create_relationships_batch(
            [("ku:preserve-rel-source", "ku:preserve-rel-target", "REQUIRES_KNOWLEDGE", None)]
        )

        # Attempt delete without cascade (will fail)
        await ku_backend.delete("ku:preserve-rel-source", cascade=False)

        # Relationship should still exist
        has_rel = await ku_backend.has_relationship(
            "ku:preserve-rel-source",
            "ku:preserve-rel-target",
            RelationshipName.REQUIRES_KNOWLEDGE,
        )
        assert has_rel.is_ok
        assert has_rel.value is True


@pytest.mark.asyncio
class TestDeleteEdgeCases:
    """Integration tests for delete() edge cases."""

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver, clean_neo4j):
        """Create KU backend with clean database."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    async def test_delete_nonexistent_entity(self, ku_backend):
        """Test deleting non-existent entity returns Ok(False)."""
        delete_result = await ku_backend.delete("ku:nonexistent", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is False

    async def test_delete_idempotent(self, ku_backend):
        """Test multiple deletes don't error."""
        # Create entity
        ku = Curriculum(
            uid="ku:idempotent-delete",
            title="Idempotent",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku)

        # Delete first time
        result1 = await ku_backend.delete("ku:idempotent-delete", cascade=True)
        assert result1.is_ok
        assert result1.value is True

        # Delete second time (already gone)
        result2 = await ku_backend.delete("ku:idempotent-delete", cascade=True)
        assert result2.is_ok
        assert result2.value is False  # Returns False because nothing was deleted

    async def test_delete_bidirectional_relationships(self, ku_backend):
        """Test cascade=True cleans up both incoming and outgoing relationships."""
        # Create 3 KUs: A -> B -> C (B has both incoming and outgoing)
        nodes = [
            Curriculum(
                uid="ku:bidir-a",
                title="A",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Curriculum(
                uid="ku:bidir-b",
                title="B",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
            Curriculum(
                uid="ku:bidir-c",
                title="C",
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            ),
        ]
        for node in nodes:
            await ku_backend.create(node)

        # A -> B and B -> C (Entity uses REQUIRES_KNOWLEDGE)
        await ku_backend.create_relationships_batch(
            [
                ("ku:bidir-a", "ku:bidir-b", "REQUIRES_KNOWLEDGE", None),
                ("ku:bidir-b", "ku:bidir-c", "REQUIRES_KNOWLEDGE", None),
            ]
        )

        # Delete B (has both incoming from A and outgoing to C)
        delete_result = await ku_backend.delete("ku:bidir-b", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is True

        # A should have no outgoing relationships now
        count_a = await ku_backend.count_related(
            "ku:bidir-a", RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
        )
        assert count_a.is_ok
        assert count_a.value == 0

        # C should have no incoming relationships now
        count_c = await ku_backend.count_related(
            "ku:bidir-c", RelationshipName.REQUIRES_KNOWLEDGE, "incoming"
        )
        assert count_c.is_ok
        assert count_c.value == 0

    async def test_delete_with_relationship_properties(self, ku_backend):
        """Test cascade=True works when relationships have properties."""
        # Create KUs with relationship that has properties
        ku1 = Curriculum(
            uid="ku:props-source",
            title="Source",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        ku2 = Curriculum(
            uid="ku:props-target",
            title="Target",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_AWARENESS,
        )
        await ku_backend.create(ku1)
        await ku_backend.create(ku2)

        # Create relationship with properties (Entity uses REQUIRES_KNOWLEDGE)
        await ku_backend.create_relationships_batch(
            [
                (
                    "ku:props-source",
                    "ku:props-target",
                    "REQUIRES_KNOWLEDGE",
                    {"confidence": 0.9, "strength": 1.0, "notes": "Important"},
                )
            ]
        )

        # Delete source with cascade (properties shouldn't prevent deletion)
        delete_result = await ku_backend.delete("ku:props-source", cascade=True)
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify deleted
        get_result = await ku_backend.get("ku:props-source")
        assert get_result.is_ok
        assert get_result.value is None
