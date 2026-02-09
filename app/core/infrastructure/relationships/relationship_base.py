"""
Relationship Base Components
=============================

Shared base classes and mixins for entities with relationships.
Follows SKUEL's principle of "one way forward" - providing a single,
consistent way to handle relationships across all entity types.

This eliminates duplication between knowledge_unit.py, lp_unified.py,
and other relationship-bearing entities.
"""

from dataclasses import dataclass, field

from core.models.enums import RelationshipType


@dataclass
class RelationshipMixin:
    """
    Base mixin for entities with relationships.

    Provides common relationship fields and helper methods that all
    relationship-bearing entities should have. This ensures consistency
    across KnowledgeUnit, LearningPath, and other entities.
    """

    # Core learning flow relationships
    prerequisite_uids: list[str] = field(default_factory=list)
    enables_uids: list[str] = field(default_factory=list)
    builds_on_uids: list[str] = field(default_factory=list)

    # Lateral relationships
    related_uids: list[str] = field(default_factory=list)
    see_also_uids: list[str] = field(default_factory=list)

    # Application relationships
    applies_to_uids: list[str] = field(default_factory=list)
    used_by_uids: list[str] = field(default_factory=list)

    # Domain relationships
    domain_uids: list[str] = field(default_factory=list)

    @property
    def has_prerequisites(self) -> bool:
        """Check if this entity has prerequisites"""
        return bool(self.prerequisite_uids or self.builds_on_uids)

    @property
    def has_dependencies(self) -> bool:
        """Check if this entity has any dependencies"""
        return bool(self.prerequisite_uids or self.builds_on_uids or self.enables_uids)

    @property
    def all_relationship_uids(self) -> set[str]:
        """
        Get all UIDs referenced by this entity.
        Useful for graph traversal and dependency checking.
        """
        uids = set()

        # Add all list-based relationships
        for uid_list in [
            self.prerequisite_uids,
            self.enables_uids,
            self.builds_on_uids,
            self.related_uids,
            self.see_also_uids,
            self.applies_to_uids,
            self.used_by_uids,
            self.domain_uids,
        ]:
            uids.update(uid_list)

        return uids

    def get_relationships_by_type(self, rel_type: RelationshipType) -> list[str]:
        """
        Get UIDs for a specific relationship type.

        ALIASING DESIGN (Intentional):
        This method maps multiple RelationshipType enum values to the same
        underlying UID list. This is intentional to provide flexibility at
        the mixin level:

        - REQUIRES, PREREQUISITE, PREREQUISITE_FOR -> prerequisite_uids
        - RELATED_TO, RELATED -> related_uids

        This allows callers to use domain-appropriate terminology while
        the mixin maintains a simplified internal structure.

        NOTE: The semantic layer (KuSemanticService) uses SemanticRelationshipType
        directly WITHOUT aliasing - it operates at a different abstraction level
        where relationship semantics are preserved precisely.

        Current usage: Internal only (remove_relationship method).

        Args:
            rel_type: The relationship type to query

        Returns:
            List of target UIDs for that relationship type
        """
        mapping = {
            RelationshipType.REQUIRES: self.prerequisite_uids,
            RelationshipType.PREREQUISITE: self.prerequisite_uids,
            RelationshipType.PREREQUISITE_FOR: self.prerequisite_uids,
            RelationshipType.ENABLES: self.enables_uids,
            RelationshipType.BUILDS_ON: self.builds_on_uids,
            RelationshipType.RELATED_TO: self.related_uids,
            RelationshipType.RELATED: self.related_uids,
            RelationshipType.APPLIES_TO: self.applies_to_uids,
            RelationshipType.USED_BY: self.used_by_uids,
        }
        return mapping.get(rel_type, [])

    def add_relationship(self, rel_type: RelationshipType, target_uid: str) -> None:
        """Add a relationship of specified type to target"""
        if rel_type in {RelationshipType.REQUIRES, RelationshipType.PREREQUISITE}:
            if target_uid not in self.prerequisite_uids:
                self.prerequisite_uids.append(target_uid)
        elif rel_type == RelationshipType.ENABLES:
            if target_uid not in self.enables_uids:
                self.enables_uids.append(target_uid)
        elif rel_type == RelationshipType.BUILDS_ON:
            if target_uid not in self.builds_on_uids:
                self.builds_on_uids.append(target_uid)
        elif (
            rel_type in {RelationshipType.RELATED_TO, RelationshipType.RELATED}
            and target_uid not in self.related_uids
        ):
            self.related_uids.append(target_uid)
        # Add more as needed

    def remove_relationship(self, rel_type: RelationshipType, target_uid: str) -> None:
        """Remove a relationship of specified type to target"""
        relationships = self.get_relationships_by_type(rel_type)
        if target_uid in relationships:
            relationships.remove(target_uid)


@dataclass
class HierarchicalRelationshipMixin(RelationshipMixin):
    """
    Extended mixin for entities with hierarchical relationships.

    Adds parent-child relationships on top of base relationships.
    """

    # Hierarchy
    parent_uid: str | None = None
    child_uids: list[str] = field(default_factory=list)

    @property
    def is_root(self) -> bool:
        """Check if this is a root node (no parent)"""
        return self.parent_uid is None

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf node (no children)"""
        return len(self.child_uids) == 0

    @property
    def all_relationship_uids(self) -> set[str]:
        """Override to include hierarchical relationships"""
        uids = super().all_relationship_uids

        if self.parent_uid:
            uids.add(self.parent_uid)
        uids.update(self.child_uids)

        return uids

    def add_child(self, child_uid: str) -> None:
        """Add a child relationship"""
        if child_uid not in self.child_uids:
            self.child_uids.append(child_uid)

    def remove_child(self, child_uid: str) -> None:
        """Remove a child relationship"""
        if child_uid in self.child_uids:
            self.child_uids.remove(child_uid)


@dataclass
class LearningRelationshipMixin(RelationshipMixin):
    """
    Extended mixin for learning-specific relationships.

    Adds learning paths, resources, and alternative versions.
    """

    # Learning path integration
    learning_path_uids: list[str] = field(default_factory=list)
    learning_step_uids: list[str] = field(default_factory=list)

    # Resources and practice
    resource_uids: list[str] = field(default_factory=list)
    exercise_uids: list[str] = field(default_factory=list)
    assessment_uids: list[str] = field(default_factory=list)

    # Alternative versions
    alternative_explanation_uids: list[str] = field(default_factory=list)
    simplified_version_uid: str | None = None
    advanced_version_uid: str | None = None

    # Semantic groupings
    concept_group_uid: str | None = None
    skill_cluster_uid: str | None = None

    @property
    def has_learning_paths(self) -> bool:
        """Check if this entity is part of any learning paths"""
        return bool(self.learning_path_uids or self.learning_step_uids)

    @property
    def has_resources(self) -> bool:
        """Check if this entity has associated resources"""
        return bool(self.resource_uids or self.exercise_uids or self.assessment_uids)

    @property
    def has_alternatives(self) -> bool:
        """Check if this entity has alternative versions"""
        return bool(
            self.alternative_explanation_uids
            or self.simplified_version_uid
            or self.advanced_version_uid
        )

    @property
    def all_relationship_uids(self) -> set[str]:
        """Override to include learning-specific relationships"""
        uids = super().all_relationship_uids

        # Add learning paths
        uids.update(self.learning_path_uids)
        uids.update(self.learning_step_uids)

        # Add resources
        uids.update(self.resource_uids)
        uids.update(self.exercise_uids)
        uids.update(self.assessment_uids)

        # Add alternatives
        uids.update(self.alternative_explanation_uids)

        # Add single UIDs
        for uid in [
            self.simplified_version_uid,
            self.advanced_version_uid,
            self.concept_group_uid,
            self.skill_cluster_uid,
        ]:
            if uid:
                uids.add(uid)

        return uids


@dataclass
class FullRelationshipMixin(HierarchicalRelationshipMixin, LearningRelationshipMixin):
    """
    Complete relationship mixin combining all relationship types.

    Use this for entities like KnowledgeUnit that need all relationship types.
    """

    pass


def validate_no_self_references(entity_uid: str, relationships: set[str]) -> None:
    """
    Validate that an entity doesn't reference itself.

    Args:
        entity_uid: The UID of the entity
        relationships: Set of relationship UIDs to check

    Raises:
        ValueError: If self-reference is found
    """
    if entity_uid in relationships:
        raise ValueError(f"Entity {entity_uid} cannot reference itself in relationships")


def merge_relationships(primary: RelationshipMixin, secondary: RelationshipMixin) -> None:
    """
    Merge relationships from secondary into primary.

    Updates primary in-place with unique relationships from secondary.

    Args:
        primary: The relationship set to update,
        secondary: The relationship set to merge from
    """
    # Merge prerequisite UIDs
    for uid in secondary.prerequisite_uids:
        if uid not in primary.prerequisite_uids:
            primary.prerequisite_uids.append(uid)

    # Merge enables UIDs
    for uid in secondary.enables_uids:
        if uid not in primary.enables_uids:
            primary.enables_uids.append(uid)

    # Continue for other relationship types...
    for uid in secondary.builds_on_uids:
        if uid not in primary.builds_on_uids:
            primary.builds_on_uids.append(uid)

    for uid in secondary.related_uids:
        if uid not in primary.related_uids:
            primary.related_uids.append(uid)


def find_circular_dependencies(
    start_uid: str,
    relationships: dict[str, list[str]],
    visited: set[str] | None = None,
    path: list[str] | None = None,
) -> list[str] | None:
    """
    Find circular dependencies in relationship graph.

    Args:
        start_uid: Starting entity UID,
        relationships: Map of entity UID to prerequisite UIDs,
        visited: Set of visited UIDs (for recursion),
        path: Current path (for recursion)

    Returns:
        List of UIDs forming a cycle, or None if no cycle
    """
    if visited is None:
        visited = set()
    if path is None:
        path = []

    if start_uid in path:
        # Found a cycle
        cycle_start = path.index(start_uid)
        return [*path[cycle_start:], start_uid]

    if start_uid in visited:
        return None

    visited.add(start_uid)
    path.append(start_uid)

    # Check prerequisites
    for prereq_uid in relationships.get(start_uid, []):
        cycle = find_circular_dependencies(prereq_uid, relationships, visited, path.copy())
        if cycle:
            return cycle

    return None
