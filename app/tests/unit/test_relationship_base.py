"""
Unit tests for relationship base mixins.

Tests the HierarchicalRelationshipMixin and related functionality
to prevent regression of the is_root property bug (parent_uid tuple default).
"""

from dataclasses import dataclass, field

import pytest

from core.infrastructure.relationships.relationship_base import (
    FullRelationshipMixin,
    HierarchicalRelationshipMixin,
    find_circular_dependencies,
    validate_no_self_references,
)
from core.models.shared_enums import RelationshipType


@dataclass
class SampleHierarchicalEntity(HierarchicalRelationshipMixin):
    """Sample entity for hierarchy testing."""

    # Fields with defaults to work with mixin inheritance
    uid: str = field(default="test")
    title: str = field(default="Test")


@dataclass
class SampleFullEntity(FullRelationshipMixin):
    """Sample entity for full relationship testing."""

    uid: str = field(default="test")
    title: str = field(default="Test")


class TestIsRootProperty:
    """Tests for is_root property - regression test for tuple default bug."""

    def test_is_root_when_parent_uid_is_none(self):
        """Entity without parent should be root."""
        entity = SampleHierarchicalEntity(
            uid="test_001",
            title="Root Entity",
            parent_uid=None,
        )
        assert entity.is_root is True

    def test_is_root_when_parent_uid_is_set(self):
        """Entity with parent should not be root."""
        entity = SampleHierarchicalEntity(
            uid="test_002",
            title="Child Entity",
            parent_uid="parent_001",
        )
        assert entity.is_root is False

    def test_default_parent_uid_is_none_not_tuple(self):
        """
        Default parent_uid should be None, not (None,) tuple.

        This is the regression test for the bug where parent_uid
        was defaulted to (None,) instead of None.
        """
        entity = SampleHierarchicalEntity(
            uid="test_003",
            title="Default Parent Entity",
        )
        # Verify parent_uid is exactly None, not a tuple
        assert entity.parent_uid is None
        assert entity.parent_uid != (None,)
        assert entity.is_root is True


class TestIsLeafProperty:
    """Tests for is_leaf property."""

    def test_is_leaf_when_no_children(self):
        """Entity without children should be leaf."""
        entity = SampleHierarchicalEntity(
            uid="test_001",
            title="Leaf Entity",
        )
        assert entity.is_leaf is True

    def test_is_leaf_when_has_children(self):
        """Entity with children should not be leaf."""
        entity = SampleHierarchicalEntity(
            uid="test_001",
            title="Parent Entity",
            child_uids=["child_001", "child_002"],
        )
        assert entity.is_leaf is False


class TestChildManagement:
    """Tests for add_child and remove_child methods."""

    def test_add_child(self):
        """Adding a child should update child_uids."""
        entity = SampleHierarchicalEntity(uid="parent")
        entity.add_child("child_001")
        assert "child_001" in entity.child_uids
        assert not entity.is_leaf

    def test_add_child_idempotent(self):
        """Adding same child twice should not duplicate."""
        entity = SampleHierarchicalEntity(uid="parent")
        entity.add_child("child_001")
        entity.add_child("child_001")
        assert entity.child_uids.count("child_001") == 1

    def test_remove_child(self):
        """Removing a child should update child_uids."""
        entity = SampleHierarchicalEntity(uid="parent", child_uids=["child_001"])
        entity.remove_child("child_001")
        assert "child_001" not in entity.child_uids
        assert entity.is_leaf


class TestRelationshipMixin:
    """Tests for base RelationshipMixin."""

    def test_has_prerequisites_true(self):
        """Entity with prerequisites should return True."""
        entity = SampleHierarchicalEntity(uid="test", prerequisite_uids=["prereq_001"])
        assert entity.has_prerequisites is True

    def test_has_prerequisites_false(self):
        """Entity without prerequisites should return False."""
        entity = SampleHierarchicalEntity(uid="test")
        assert entity.has_prerequisites is False

    def test_all_relationship_uids(self):
        """all_relationship_uids should return set of all related UIDs."""
        entity = SampleHierarchicalEntity(
            uid="test",
            prerequisite_uids=["prereq_001"],
            enables_uids=["enables_001"],
            parent_uid="parent_001",
            child_uids=["child_001", "child_002"],
        )
        all_uids = entity.all_relationship_uids
        assert "prereq_001" in all_uids
        assert "enables_001" in all_uids
        assert "parent_001" in all_uids
        assert "child_001" in all_uids
        assert "child_002" in all_uids


class TestGetRelationshipsByType:
    """Tests for get_relationships_by_type with aliasing."""

    def test_requires_returns_prerequisite_uids(self):
        """REQUIRES should return prerequisite_uids (aliasing)."""
        entity = SampleHierarchicalEntity(uid="test", prerequisite_uids=["prereq_001"])
        result = entity.get_relationships_by_type(RelationshipType.REQUIRES)
        assert result == ["prereq_001"]

    def test_prerequisite_returns_same_list(self):
        """PREREQUISITE should return same list as REQUIRES (aliasing)."""
        entity = SampleHierarchicalEntity(uid="test", prerequisite_uids=["prereq_001"])
        requires_result = entity.get_relationships_by_type(RelationshipType.REQUIRES)
        prereq_result = entity.get_relationships_by_type(RelationshipType.PREREQUISITE)
        # Both should return the same list (same reference)
        assert requires_result is prereq_result

    def test_enables_returns_enables_uids(self):
        """ENABLES should return enables_uids."""
        entity = SampleHierarchicalEntity(uid="test", enables_uids=["enables_001"])
        result = entity.get_relationships_by_type(RelationshipType.ENABLES)
        assert result == ["enables_001"]

    def test_unknown_type_returns_empty_list(self):
        """Unknown relationship type should return empty list."""
        entity = SampleHierarchicalEntity(uid="test")
        # Use a type that's not in the mapping
        result = entity.get_relationships_by_type(RelationshipType.PART_OF)
        assert result == []


class TestValidationHelpers:
    """Tests for validation helper functions."""

    def test_validate_no_self_references_passes(self):
        """Validation should pass when no self-reference."""
        # Should not raise
        validate_no_self_references("entity_001", {"entity_002", "entity_003"})

    def test_validate_no_self_references_fails(self):
        """Validation should fail when self-reference exists."""
        with pytest.raises(ValueError, match="cannot reference itself"):
            validate_no_self_references("entity_001", {"entity_001", "entity_002"})

    def test_find_circular_dependencies_no_cycle(self):
        """Should return None when no circular dependencies."""
        relationships = {
            "a": ["b"],
            "b": ["c"],
            "c": [],
        }
        result = find_circular_dependencies("a", relationships)
        assert result is None

    def test_find_circular_dependencies_with_cycle(self):
        """Should return cycle path when circular dependency exists."""
        relationships = {
            "a": ["b"],
            "b": ["c"],
            "c": ["a"],  # Cycle back to a
        }
        result = find_circular_dependencies("a", relationships)
        assert result is not None
        assert "a" in result
