"""
Relationship Validation
=======================

Centralized relationship validation to prevent scattering across files.
Following SKUEL's principle of single source of truth.

This harmonizes validation logic from knowledge_unit.py, lp_unified.py,
and unified_relationships.py.
"""

from typing import Any

from core.models.enums import ActivityStatus, RelationshipType


class RelationshipValidator:
    """
    Central validator for all relationship operations.

    Provides consistent validation across all entity types.
    """

    @staticmethod
    def validate_no_self_reference(
        entity_uid: str, target_uids: list[str], relationship_type: RelationshipType
    ) -> None:
        """
        Validate that an entity doesn't reference itself.

        Args:
            entity_uid: The entity's UID,
            target_uids: UIDs this entity relates to,
            relationship_type: Type of relationship

        Raises:
            ValueError: If self-reference found
        """
        if entity_uid in target_uids:
            raise ValueError(
                f"Entity {entity_uid} cannot have {relationship_type.value} relationship to itself"
            )

    @staticmethod
    def validate_relationship_consistency(
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipType,
        existing_relationships: dict[tuple[str, str], RelationshipType],
    ) -> None:
        """
        Validate that a new relationship doesn't conflict with existing ones.

        Args:
            from_uid: Source entity,
            to_uid: Target entity,
            relationship_type: Proposed relationship type,
            existing_relationships: Map of (from, to) -> type

        Raises:
            ValueError: If conflicting relationship exists
        """
        # Check for direct conflict
        existing = existing_relationships.get((from_uid, to_uid))
        if existing and not RelationshipValidator._can_coexist(existing, relationship_type):
            raise ValueError(
                f"Cannot add {relationship_type.value} between {from_uid} "
                f"and {to_uid}: conflicts with existing {existing.value}"
            )

        # Check for inverse conflict
        inverse = existing_relationships.get((to_uid, from_uid))
        if inverse and not RelationshipValidator._can_coexist_inverse(inverse, relationship_type):
            raise ValueError(
                f"Cannot add {relationship_type.value} from {from_uid} "
                f"to {to_uid}: conflicts with inverse {inverse.value}"
            )

    @staticmethod
    def _can_coexist(existing: RelationshipType, new: RelationshipType) -> bool:
        """Check if two relationship types can coexist"""
        # These pairs cannot coexist
        conflicts = [
            {RelationshipType.BLOCKS, RelationshipType.ENABLES},
            {RelationshipType.PARENT_OF, RelationshipType.CHILD_OF},
            {RelationshipType.BEFORE, RelationshipType.AFTER},
        ]

        for conflict_set in conflicts:
            if existing in conflict_set and new in conflict_set:
                return False

        return True

    @staticmethod
    def _can_coexist_inverse(existing: RelationshipType, new: RelationshipType) -> bool:
        """Check if relationships can exist in opposite directions"""
        # Parent-child must be consistent (can't both be parents of each other)
        # Blocking relationships must be acyclic (would create deadlock)
        return not (
            (existing == RelationshipType.PARENT_OF and new == RelationshipType.PARENT_OF)
            or (existing == RelationshipType.BLOCKS and new == RelationshipType.BLOCKS)
        )

    @staticmethod
    def validate_hierarchy(
        entity_uid: str,
        parent_uid: str | None,
        child_uids: list[str],
        all_relationships: dict[str, list[str]],
    ) -> None:
        """
        Validate hierarchical relationships (parent-child).

        Args:
            entity_uid: The entity being validated,
            parent_uid: Proposed parent,
            child_uids: Proposed children,
            all_relationships: Map of all parent-child relationships

        Raises:
            ValueError: If hierarchy would be invalid
        """
        # Can't be own parent
        if parent_uid == entity_uid:
            raise ValueError(f"{entity_uid} cannot be its own parent")

        # Can't be own child
        if entity_uid in child_uids:
            raise ValueError(f"{entity_uid} cannot be its own child")

        # Check for cycles in hierarchy
        if parent_uid and RelationshipValidator._would_create_hierarchy_cycle(
            entity_uid, parent_uid, all_relationships
        ):
            raise ValueError(f"Setting {parent_uid} as parent of {entity_uid} would create a cycle")

    @staticmethod
    def _would_create_hierarchy_cycle(
        child: str, proposed_parent: str, relationships: dict[str, list[str]]
    ) -> bool:
        """Check if adding a parent relationship would create a cycle"""
        # Traverse up from proposed parent
        current = proposed_parent
        visited = set()

        while current:
            if current == child:
                return True  # Found cycle

            if current in visited:
                break  # Avoid infinite loop

            visited.add(current)

            # Get parent of current
            parents = relationships.get(current, [])
            current = parents[0] if parents else None

        return False

    @staticmethod
    def _find_prerequisite_cycle(
        start_uid: str,
        prerequisites_map: dict[str, list[str]],
        visited: set[str] | None = None,
        path: list[str] | None = None,
    ) -> list[str] | None:
        """Find circular dependencies in prerequisites"""
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
        for prereq_uid in prerequisites_map.get(start_uid, []):
            cycle = RelationshipValidator._find_prerequisite_cycle(
                prereq_uid, prerequisites_map, visited, path.copy()
            )
            if cycle:
                return cycle

        return None

    @staticmethod
    def validate_prerequisites(
        entity_uid: str, prerequisite_uids: list[str], all_prerequisites: dict[str, list[str]]
    ) -> None:
        """
        Validate prerequisite relationships.

        Args:
            entity_uid: The entity being validated,
            prerequisite_uids: Proposed prerequisites,
            all_prerequisites: Map of all prerequisite relationships

        Raises:
            ValueError: If prerequisites would be invalid
        """
        # Can't be own prerequisite
        if entity_uid in prerequisite_uids:
            raise ValueError(f"{entity_uid} cannot be its own prerequisite")

        # Check for circular prerequisites
        test_map = dict(all_prerequisites)
        test_map[entity_uid] = prerequisite_uids

        # Use inline cycle detection instead of importing
        cycle = RelationshipValidator._find_prerequisite_cycle(entity_uid, test_map)
        if cycle:
            raise ValueError(f"Circular prerequisite dependency: {' -> '.join(cycle)}")

    @staticmethod
    def validate_progress_requirements(
        required_completion: float,
        required_mastery: float,
        required_practice_count: int = 0,
        required_time_minutes: int = 0,
    ) -> None:
        """
        Validate progress requirement values.

        Args:
            required_completion: Required completion percentage (0-100),
            required_mastery: Required mastery level (0-1),
            required_practice_count: Required practice sessions,
            required_time_minutes: Required time investment

        Raises:
            ValueError: If requirements are invalid
        """
        if not 0 <= required_completion <= 100:
            raise ValueError(f"Required completion must be 0-100, got {required_completion}")

        if not 0 <= required_mastery <= 1:
            raise ValueError(f"Required mastery must be 0-1, got {required_mastery}")

        if required_practice_count < 0:
            raise ValueError(
                f"Required practice count cannot be negative: {required_practice_count}"
            )

        if required_time_minutes < 0:
            raise ValueError(f"Required time cannot be negative: {required_time_minutes}")

    @staticmethod
    def validate_relationship_metadata(
        metadata: dict[str, Any], relationship_type: RelationshipType
    ) -> None:
        """
        Validate metadata for a specific relationship type.

        Args:
            metadata: Relationship metadata,
            relationship_type: Type of relationship

        Raises:
            ValueError: If metadata is invalid for this relationship type
        """
        # Validate strength/confidence values if present
        if "strength" in metadata:
            strength = metadata["strength"]
            if not 0 <= strength <= 1:
                raise ValueError(f"Strength must be 0-1, got {strength}")

        if "confidence" in metadata:
            confidence = metadata["confidence"]
            if not 0 <= confidence <= 1:
                raise ValueError(f"Confidence must be 0-1, got {confidence}")

        # Validate semantic distance if present
        if "semantic_distance" in metadata:
            distance = metadata["semantic_distance"]
            if distance < 0:
                raise ValueError(f"Semantic distance cannot be negative: {distance}")

        # Type-specific validation
        if relationship_type == RelationshipType.BLOCKS and metadata.get("is_optional", False):
            # Blocking relationships should not be optional
            raise ValueError("Blocking relationships cannot be optional")

    @staticmethod
    def validate_entity_can_have_relationship(
        entity_type: Any, relationship_type: RelationshipType
    ) -> None:
        """
        Validate that an entity type can have a specific relationship type.

        Args:
            entity_type: Type of the entity,
            relationship_type: Proposed relationship type

        Raises:
            ValueError: If this entity type cannot have this relationship
        """
        # Example: Events might not support prerequisite relationships
        # This would be customized based on your domain rules
        pass

    @staticmethod
    def validate_relationship_transition(
        entity_uid: str,
        from_status: ActivityStatus,
        to_status: ActivityStatus,
        blocking_relationships: list[tuple[str, ActivityStatus]],
    ) -> None:
        """
        Validate that a status transition is valid given relationships.

        Args:
            entity_uid: Entity attempting transition,
            from_status: Current status,
            to_status: Desired status,
            blocking_relationships: List of (blocker_uid, blocker_status) tuples

        Raises:
            ValueError: If transition is blocked
        """
        # Can't start if blocked by incomplete dependencies
        if (
            from_status in {ActivityStatus.DRAFT, ActivityStatus.SCHEDULED}
            and to_status == ActivityStatus.IN_PROGRESS
        ):
            for blocker_uid, blocker_status in blocking_relationships:
                if blocker_status != ActivityStatus.COMPLETED:
                    raise ValueError(
                        f"Cannot start {entity_uid}: blocked by incomplete "
                        f"dependency {blocker_uid} (status: {blocker_status.value})"
                    )


class RelationshipSanitizer:
    """
    Sanitize and clean relationship data.
    """

    @staticmethod
    def remove_duplicates(uid_list: list[str]) -> list[str]:
        """Remove duplicate UIDs while preserving order"""
        seen = set()
        result = []
        for uid in uid_list:
            if uid not in seen:
                seen.add(uid)
                result.append(uid)
        return result

    @staticmethod
    def remove_self_references(entity_uid: str, uid_list: list[str]) -> list[str]:
        """Remove any self-references from a UID list"""
        return [uid for uid in uid_list if uid != entity_uid]

    @staticmethod
    def clean_relationships(
        entity_uid: str, relationships: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        """
        Clean all relationships for an entity.

        Args:
            entity_uid: The entity's UID,
            relationships: Map of relationship type to UID lists

        Returns:
            Cleaned relationships
        """
        cleaned = {}

        for rel_type, uid_list in relationships.items():
            # Remove self-references
            clean_list = RelationshipSanitizer.remove_self_references(entity_uid, uid_list)
            # Remove duplicates
            clean_list = RelationshipSanitizer.remove_duplicates(clean_list)

            if clean_list:  # Only include non-empty lists
                cleaned[rel_type] = clean_list

        return cleaned

    @staticmethod
    def merge_relationship_lists(
        primary: list[str], secondary: list[str], preserve_order: bool = True
    ) -> list[str]:
        """
        Merge two relationship lists without duplicates.

        Args:
            primary: Primary list (takes precedence),
            secondary: Secondary list to merge,
            preserve_order: Whether to preserve order

        Returns:
            Merged list without duplicates
        """
        if preserve_order:
            # Preserve order from both lists
            result = list(primary)
            for uid in secondary:
                if uid not in result:
                    result.append(uid)
            return result
        else:
            # Just return unique values
            return list(set(primary) | set(secondary))


class RelationshipAnalyzer:
    """
    Analyze relationships for patterns and issues.
    """

    @staticmethod
    def find_orphans(all_uids: set[str], relationships: dict[str, list[str]]) -> set[str]:
        """Find entities with no relationships"""
        connected = set()

        for from_uid, to_uids in relationships.items():
            connected.add(from_uid)
            connected.update(to_uids)

        return all_uids - connected

    @staticmethod
    def find_hubs(
        relationships: dict[str, list[str]], threshold: int = 10
    ) -> list[tuple[str, int]]:
        """
        Find hub entities with many relationships.

        Returns:
            List of (uid, connection_count) tuples
        """
        connection_counts = {}

        # Count outgoing
        for from_uid, to_uids in relationships.items():
            connection_counts[from_uid] = connection_counts.get(from_uid, 0) + len(to_uids)

            # Count incoming
            for to_uid in to_uids:
                connection_counts[to_uid] = connection_counts.get(to_uid, 0) + 1

        # Filter to hubs
        hubs = [(uid, count) for uid, count in connection_counts.items() if count >= threshold]

        # Sort by connection count
        def get_hub_connection_count(hub) -> int:
            return hub[1]

        hubs.sort(key=get_hub_connection_count, reverse=True)

        return hubs

    @staticmethod
    def calculate_relationship_density(entity_count: int, relationship_count: int) -> float:
        """
        Calculate the density of the relationship graph.

        Returns:
            Density between 0 and 1 (1 = fully connected)
        """
        if entity_count <= 1:
            return 0.0

        max_possible = entity_count * (entity_count - 1)
        return relationship_count / max_possible if max_possible > 0 else 0.0
