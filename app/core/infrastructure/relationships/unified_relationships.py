"""
Unified Relationship System
============================

This module extends the relationship system to work across all entity types,
enabling tasks, events, habits, and learning sessions to be interconnected.

The unified system allows for:
- Cross-entity dependencies
- Parent-child hierarchies across types
- Related entity discovery
- Relationship-aware calendar rendering
- Semantic relationship precision via RDF-inspired thinking

Now integrates with semantic_relationships.py for richer relationship semantics.
"""

__version__ = "1.1"


from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
    SemanticTriple,
)
from core.infrastructure.relationships.semantic_relationships import (
    is_blocking_relationship as is_semantic_blocking,
)
from core.models.shared_enums import ActivityStatus, ActivityType, RelationshipType, SystemConstants

# Protocols
from core.services.protocols import HasMetrics, HasStreaks, HasUID, MetricsLike, StreaksLike
from core.services.protocols.calendar_protocol import CalendarTrackable

if TYPE_CHECKING:
    from core.models.progress_unified import UnifiedProgress  # type: ignore[import-not-found]


# ============================================================================
# RELATIONSHIP TYPE HELPER FUNCTIONS
# ============================================================================


def is_blocking_relationship(rel_type: RelationshipType) -> bool:
    """Check if this relationship type blocks progress"""
    return rel_type in {
        RelationshipType.BLOCKS,
        RelationshipType.REQUIRES,
        RelationshipType.PREREQUISITE_FOR,
        RelationshipType.PREREQUISITE,
    }


def is_hierarchical_relationship(rel_type: RelationshipType) -> bool:
    """Check if this represents a hierarchy"""
    return rel_type in {
        RelationshipType.PARENT_OF,
        RelationshipType.CHILD_OF,
        RelationshipType.SUBTASK_OF,
        RelationshipType.PART_OF,
        RelationshipType.PARENT_CHILD,
    }


def is_temporal_relationship(rel_type: RelationshipType) -> bool:
    """Check if this is a time-based relationship"""
    return rel_type in {
        RelationshipType.BEFORE,
        RelationshipType.AFTER,
        RelationshipType.DURING,
        RelationshipType.OVERLAPS,
    }


def get_inverse_relationship(rel_type: RelationshipType) -> RelationshipType | None:
    """Get the inverse relationship type"""
    inverses = {
        RelationshipType.BLOCKS: RelationshipType.REQUIRES,
        RelationshipType.REQUIRES: RelationshipType.BLOCKS,
        RelationshipType.PARENT_OF: RelationshipType.CHILD_OF,
        RelationshipType.CHILD_OF: RelationshipType.PARENT_OF,
        RelationshipType.BEFORE: RelationshipType.AFTER,
        RelationshipType.AFTER: RelationshipType.BEFORE,
        RelationshipType.ENABLES: RelationshipType.REQUIRES,
        RelationshipType.PREREQUISITE_FOR: RelationshipType.BUILDS_ON,
        RelationshipType.PREREQUISITE: RelationshipType.BUILDS_ON,
        RelationshipType.BUILDS_ON: RelationshipType.PREREQUISITE_FOR,
        RelationshipType.TRIGGERS: RelationshipType.REQUIRES,
        RelationshipType.REPLACES: RelationshipType.REQUIRES,
    }
    return inverses.get(rel_type)


# ============================================================================
# ENTITY RELATIONSHIP
# ============================================================================


@dataclass(frozen=True)
class EntityRelationship:
    """
    Represents a relationship between two calendar-trackable entities.

    This is a value object that captures the relationship metadata.
    Supports both generic RelationshipType and semantic relationships.
    """

    from_uid: str  # Source entity UID
    to_uid: str  # Target entity UID
    relationship_type: RelationshipType

    # Optional semantic relationship for richer meaning
    semantic_type: SemanticRelationshipType | None = None
    semantic_metadata: RelationshipMetadata | None = None

    # Entity type hints (for optimization)
    from_type: ActivityType | None = None
    to_type: ActivityType | None = None

    # Relationship metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Relationship constraints
    is_mandatory: bool = False  # Must be maintained
    is_inferred: bool = False  # System-inferred vs user-defined

    def __hash__(self) -> int:
        return hash((self.from_uid, self.to_uid, self.relationship_type))

    def to_semantic_triple(self) -> SemanticTriple:
        """
        Convert to semantic triple representation.

        If semantic_type is set, use it directly. Otherwise, convert
        generic relationship_type to semantic equivalent.
        """
        if self.semantic_type and self.semantic_metadata:
            return SemanticTriple(
                subject=self.from_uid,
                predicate=self.semantic_type,
                object=self.to_uid,
                metadata=self.semantic_metadata,
            )
        else:
            # Convert generic to semantic using to_semantic() method
            semantic_pred = SemanticRelationshipType.to_semantic(self.relationship_type)
            return SemanticTriple(
                subject=self.from_uid,
                predicate=semantic_pred,
                object=self.to_uid,
                metadata=RelationshipMetadata(
                    source="generic_conversion",
                    confidence=ConfidenceLevel.STANDARD,  # Lower confidence for auto-converted
                    properties=self.metadata,
                ),
            )

    @property
    def is_blocking(self) -> bool:
        """Check if this relationship blocks progress."""
        if self.semantic_type:
            return is_semantic_blocking(self.semantic_type)
        return is_blocking_relationship(self.relationship_type)

    def is_satisfied_by(self, entity_statuses: dict[str, ActivityStatus]) -> bool:
        """
        Check if this relationship is satisfied given entity statuses.

        Used for dependency checking.
        """
        if not is_blocking_relationship(self.relationship_type):
            return True

        from_status = entity_statuses.get(self.from_uid)
        if not from_status:
            return False

        if self.relationship_type == RelationshipType.BLOCKS:
            # Blocking relationship is satisfied if source is completed
            return from_status == ActivityStatus.COMPLETED
        elif self.relationship_type == RelationshipType.REQUIRES:
            # Requirement is satisfied if target is available
            to_status = entity_statuses.get(self.to_uid)
            return to_status in {
                ActivityStatus.COMPLETED,
                ActivityStatus.IN_PROGRESS,
                ActivityStatus.SCHEDULED,
            }
        elif self.relationship_type == RelationshipType.PREREQUISITE_FOR:
            # Prerequisite is satisfied if source is completed
            return from_status == ActivityStatus.COMPLETED

        return True


# ============================================================================
# RELATIONSHIP GRAPH
# ============================================================================


@dataclass
class RelationshipGraph:
    """
    Manages the graph of relationships between entities.

    Provides efficient querying and traversal of entity relationships.
    """

    relationships: list[EntityRelationship] = field(default_factory=list)

    # Indexes for fast lookup
    _by_from: dict[str, list[EntityRelationship]] = field(default_factory=dict)
    _by_to: dict[str, list[EntityRelationship]] = field(default_factory=dict)
    _by_type: dict[RelationshipType, list[EntityRelationship]] = field(default_factory=dict)

    def add_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipType, **kwargs: Any
    ) -> EntityRelationship:
        """Add a new relationship to the graph"""
        relationship = EntityRelationship(
            from_uid=from_uid, to_uid=to_uid, relationship_type=relationship_type, **kwargs
        )

        self.relationships.append(relationship)

        # Update indexes
        if from_uid not in self._by_from:
            self._by_from[from_uid] = []
        self._by_from[from_uid].append(relationship)

        if to_uid not in self._by_to:
            self._by_to[to_uid] = []
        self._by_to[to_uid].append(relationship)

        if relationship_type not in self._by_type:
            self._by_type[relationship_type] = []
        self._by_type[relationship_type].append(relationship)

        return relationship

    def get_relationships_from(self, uid: str) -> list[EntityRelationship]:
        """Get all relationships originating from an entity"""
        return self._by_from.get(uid, [])

    def get_relationships_to(self, uid: str) -> list[EntityRelationship]:
        """Get all relationships targeting an entity"""
        return self._by_to.get(uid, [])

    def get_related_uids(
        self, uid: str, relationship_types: set[RelationshipType] | None = None
    ) -> set[str]:
        """Get UIDs of all related entities"""
        related = set()

        # Outgoing relationships
        for rel in self.get_relationships_from(uid):
            if not relationship_types or rel.relationship_type in relationship_types:
                related.add(rel.to_uid)

        # Incoming relationships
        for rel in self.get_relationships_to(uid):
            if not relationship_types or rel.relationship_type in relationship_types:
                related.add(rel.from_uid)

        return related

    def get_dependencies(self, uid: str) -> set[str]:
        """Get UIDs of entities this one depends on"""
        blocking_types = {
            RelationshipType.BLOCKS,
            RelationshipType.REQUIRES,
            RelationshipType.PREREQUISITE_FOR,
        }

        dependencies = set()
        for rel in self.get_relationships_to(uid):
            if rel.relationship_type in blocking_types:
                dependencies.add(rel.from_uid)

        return dependencies

    def get_dependents(self, uid: str) -> set[str]:
        """Get UIDs of entities that depend on this one"""
        blocking_types = {
            RelationshipType.BLOCKS,
            RelationshipType.REQUIRES,
            RelationshipType.PREREQUISITE_FOR,
        }

        dependents = set()
        for rel in self.get_relationships_from(uid):
            if rel.relationship_type in blocking_types:
                dependents.add(rel.to_uid)

        return dependents

    def get_children(self, uid: str) -> set[str]:
        """Get UIDs of child entities"""
        child_types = {RelationshipType.PARENT_OF, RelationshipType.SUBTASK_OF}

        children = set()
        for rel in self.get_relationships_from(uid):
            if rel.relationship_type in child_types:
                children.add(rel.to_uid)

        return children

    def get_parent(self, uid: str) -> str | None:
        """Get UID of parent entity (assumes single parent)"""
        parent_types = {RelationshipType.CHILD_OF, RelationshipType.SUBTASK_OF}

        for rel in self.get_relationships_from(uid):
            if rel.relationship_type in parent_types:
                return rel.to_uid

        return None

    def find_conflicts(self, entities: list[CalendarTrackable]) -> list[tuple[str, str]]:
        """Find scheduling conflicts between entities"""
        conflicts = []

        # Check explicit conflict relationships
        conflicts.extend(
            [
                (rel.from_uid, rel.to_uid)
                for rel in self._by_type.get(RelationshipType.CONFLICTS_WITH, [])
            ]
        )

        # Check for time window overlaps
        {e.uid: e for e in entities}

        for i, entity1 in enumerate(entities):
            windows1 = entity1.get_calendar_windows()

            for entity2 in entities[i + 1 :]:
                windows2 = entity2.get_calendar_windows()

                # Check if any windows overlap
                for w1 in windows1:
                    for w2 in windows2:
                        if w1.overlaps_with(w2):
                            conflicts.append((entity1.uid, entity2.uid))
                            break

        return conflicts

    def can_start(self, uid: str, entity_statuses: dict[str, ActivityStatus]) -> bool:
        """Check if an entity can start given current statuses"""
        dependencies = self.get_dependencies(uid)

        for dep_uid in dependencies:
            status = entity_statuses.get(dep_uid)
            if status != ActivityStatus.COMPLETED:
                return False

        return True

    def topological_sort(self, uids: set[str]) -> list[str]:
        """
        Sort UIDs in dependency order (dependencies first).

        Returns a list where each entity appears after its dependencies.
        """
        # Build adjacency list for the subgraph
        adj = {uid: set() for uid in uids}
        in_degree = {uid: 0 for uid in uids}

        for uid in uids:
            for rel in self.get_relationships_from(uid):
                if rel.to_uid in uids and is_blocking_relationship(rel.relationship_type):
                    adj[uid].add(rel.to_uid)
                    in_degree[rel.to_uid] += 1

        # Kahn's algorithm
        queue = [uid for uid in uids if in_degree[uid] == 0]
        result = []

        while queue:
            uid = queue.pop(0)
            result.append(uid)

            for next_uid in adj[uid]:
                in_degree[next_uid] -= 1
                if in_degree[next_uid] == 0:
                    queue.append(next_uid)

        # If we couldn't sort all nodes, there's a cycle
        if len(result) != len(uids):
            # Return original order for cyclic dependencies
            return list(uids)

        return result


# ============================================================================
# RELATIONSHIP-AWARE MIXIN
# ============================================================================


class RelationshipAware:
    """
    Mixin to make entities relationship-aware.

    Add this to entity classes to give them relationship capabilities.
    """

    def __init__(self) -> None:
        self._relationship_graph: RelationshipGraph | None = None

    def set_relationship_graph(self, graph: RelationshipGraph):
        """Attach a relationship graph to this entity"""
        self._relationship_graph = graph

    def get_dependencies(self) -> set[str]:
        """Get UIDs of entities this depends on"""
        if not self._relationship_graph or not isinstance(self, HasUID):
            return set()
        return self._relationship_graph.get_dependencies(self.uid)

    def get_dependents(self) -> set[str]:
        """Get UIDs of entities that depend on this"""
        if not self._relationship_graph or not isinstance(self, HasUID):
            return set()
        return self._relationship_graph.get_dependents(self.uid)

    def get_all_related(self) -> set[str]:
        """Get UIDs of all related entities"""
        if not self._relationship_graph or not isinstance(self, HasUID):
            return set()
        return self._relationship_graph.get_related_uids(self.uid)

    def can_start(self, entity_statuses: dict[str, ActivityStatus]) -> bool:
        """Check if this entity can start given current statuses"""
        if not self._relationship_graph or not isinstance(self, HasUID):
            return True
        return self._relationship_graph.can_start(self.uid, entity_statuses)


# ============================================================================
# RELATIONSHIP BUILDER
# ============================================================================


class RelationshipBuilder:
    """
    Fluent interface for building entity relationships.

    Makes it easy to create complex relationship graphs.
    """

    def __init__(self, graph: RelationshipGraph | None = None) -> None:
        self.graph = graph or RelationshipGraph()
        self._from_uid: str | None = None
        self._relationship_type: RelationshipType | None = None

    def from_entity(self, uid: str) -> "RelationshipBuilder":
        """Start building a relationship from an entity"""
        self._from_uid = uid
        return self

    def blocks(self, uid: str) -> "RelationshipBuilder":
        """Add a blocking relationship"""
        if self._from_uid:
            self.graph.add_relationship(self._from_uid, uid, RelationshipType.BLOCKS)
        return self

    def requires(self, uid: str) -> "RelationshipBuilder":
        """Add a requirement relationship"""
        if self._from_uid:
            self.graph.add_relationship(self._from_uid, uid, RelationshipType.REQUIRES)
        return self

    def parent_of(self, uid: str) -> "RelationshipBuilder":
        """Add a parent relationship"""
        if self._from_uid:
            self.graph.add_relationship(self._from_uid, uid, RelationshipType.PARENT_OF)
            # Also add inverse
            self.graph.add_relationship(uid, self._from_uid, RelationshipType.CHILD_OF)
        return self

    def related_to(self, uid: str) -> "RelationshipBuilder":
        """Add a general relationship"""
        if self._from_uid:
            self.graph.add_relationship(self._from_uid, uid, RelationshipType.RELATED_TO)
        return self

    def triggers(self, uid: str) -> "RelationshipBuilder":
        """Add a trigger relationship (for habit chains)"""
        if self._from_uid:
            self.graph.add_relationship(self._from_uid, uid, RelationshipType.TRIGGERS)
        return self

    def build(self) -> RelationshipGraph:
        """Return the built graph"""
        return self.graph


# ============================================================================
# PROGRESS-AWARE RELATIONSHIPS
# ============================================================================


@dataclass(frozen=True)
class ProgressAwareRelationship(EntityRelationship):
    """
    Extended relationship that considers progress in satisfaction checks.

    This allows relationships to specify progress requirements, such as:
    - "Must be 80% complete"
    - "Requires mastery level of 0.7"
    - "Needs at least 3 practice sessions"
    """

    # Progress requirements
    required_completion_percentage: float = 100.0  # Default: must be complete
    required_mastery_level: float = 0.0  # Default: no mastery required
    required_practice_count: int = 0  # Default: no practice required
    required_time_spent_minutes: int = 0  # Default: no time requirement

    # Quality requirements
    required_quality_score: float = 0.0  # Default: any quality
    required_success_rate: float = 0.0  # For habits: success rate

    def is_satisfied_by_progress(self, progress_map: dict[str, "UnifiedProgress"]) -> bool:
        """
        Check if relationship is satisfied based on progress.

        Args:
            progress_map: Map of entity_uid to UnifiedProgress

        Returns:
            True if all progress requirements are met
        """
        # Get progress for the source entity
        from_progress = progress_map.get(self.from_uid)
        if not from_progress:
            return False  # No progress means not satisfied

        # Check if progress has metrics
        if not isinstance(from_progress, HasMetrics):
            return False

        # Check if metrics satisfy protocol
        if not isinstance(from_progress.metrics, MetricsLike):
            return False

        # Check completion requirement
        if from_progress.metrics.completion_percentage < self.required_completion_percentage:
            return False

        # Check mastery requirement
        if from_progress.metrics.mastery_level < self.required_mastery_level:
            return False

        # Check practice requirement
        if from_progress.metrics.practice_count < self.required_practice_count:
            return False

        # Check time requirement
        if from_progress.metrics.time_spent_minutes < self.required_time_spent_minutes:
            return False

        # Check quality requirement
        if from_progress.metrics.quality_score < self.required_quality_score:
            return False

        # Check success rate for habits
        if (
            self.required_success_rate > 0
            and isinstance(from_progress, HasStreaks)
            and from_progress.streaks
            and isinstance(from_progress.streaks, StreaksLike)
            and from_progress.streaks.success_rate < self.required_success_rate
        ):
            return False

        # Special handling for different relationship types
        if self.relationship_type == RelationshipType.PREREQUISITE_FOR:
            # Prerequisites typically need high mastery
            return from_progress.metrics.mastery_level >= max(
                SystemConstants.DEFAULT_CONFIDENCE_THRESHOLD, self.required_mastery_level
            )
        elif self.relationship_type == RelationshipType.BLOCKS:
            # Blocking relationships need completion
            return from_progress.metrics.completion_percentage >= 1.0
        elif self.relationship_type == RelationshipType.REQUIRES:
            # Requirements are satisfied if available (started)
            return from_progress.metrics.completion_percentage > 0

        return True

    def get_completion_gap(self, current_progress: "UnifiedProgress") -> dict[str, float]:
        """
        Calculate how far the current progress is from satisfying requirements.

        Returns:
            Dictionary of metric names to gap values (0 means satisfied)
        """
        gaps = {}

        if current_progress.metrics.completion_percentage < self.required_completion_percentage:
            gaps["completion"] = (
                self.required_completion_percentage - current_progress.metrics.completion_percentage
            )

        if current_progress.metrics.mastery_level < self.required_mastery_level:
            gaps["mastery"] = self.required_mastery_level - current_progress.metrics.mastery_level

        if current_progress.metrics.practice_count < self.required_practice_count:
            gaps["practice"] = (
                self.required_practice_count - current_progress.metrics.practice_count
            )

        if current_progress.metrics.time_spent_minutes < self.required_time_spent_minutes:
            gaps["time"] = (
                self.required_time_spent_minutes - current_progress.metrics.time_spent_minutes
            )

        return gaps


# ============================================================================
# EXTENDED RELATIONSHIP GRAPH
# ============================================================================


class ProgressAwareRelationshipGraph(RelationshipGraph):
    """
    Extended relationship graph that understands progress requirements.
    """

    def add_progress_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipType,
        required_completion: float = 100.0,
        required_mastery: float = 0.0,
        **kwargs: Any,
    ) -> ProgressAwareRelationship:
        """Add a progress-aware relationship"""
        relationship = ProgressAwareRelationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=relationship_type,
            required_completion_percentage=required_completion,
            required_mastery_level=required_mastery,
            **kwargs,
        )

        self.relationships.append(relationship)

        # Update indexes
        if from_uid not in self._by_from:
            self._by_from[from_uid] = []
        self._by_from[from_uid].append(relationship)

        if to_uid not in self._by_to:
            self._by_to[to_uid] = []
        self._by_to[to_uid].append(relationship)

        if relationship_type not in self._by_type:
            self._by_type[relationship_type] = []
        self._by_type[relationship_type].append(relationship)

        return relationship

    def can_start_with_progress(self, uid: str, progress_map: dict[str, "UnifiedProgress"]) -> bool:
        """
        Check if an entity can start given progress on dependencies.

        Args:
            uid: Entity UID to check,
            progress_map: Map of entity_uid to UnifiedProgress

        Returns:
            True if all progress requirements are met
        """
        dependencies = self.get_dependencies(uid)

        for dep_uid in dependencies:
            # Find the relationship
            for rel in self.get_relationships_to(uid):
                if rel.from_uid == dep_uid:
                    if isinstance(rel, ProgressAwareRelationship):
                        if not rel.is_satisfied_by_progress(progress_map):
                            return False
                    else:
                        # Regular relationship - check basic completion
                        progress = progress_map.get(dep_uid)
                        if not progress or not progress.metrics.is_complete():
                            return False

        return True

    def get_ready_items(
        self, all_uids: set[str], progress_map: dict[str, "UnifiedProgress"]
    ) -> list[str]:
        """
        Get items that are ready to start based on progress.

        Args:
            all_uids: All entity UIDs to consider,
            progress_map: Current progress for each entity

        Returns:
            List of UIDs that can be started
        """
        ready = []

        for uid in all_uids:
            # Skip if already started or completed
            progress = progress_map.get(uid)
            if progress and progress.status in {
                ActivityStatus.IN_PROGRESS,
                ActivityStatus.COMPLETED,
            }:
                continue

            # Check if dependencies are satisfied
            if self.can_start_with_progress(uid, progress_map):
                ready.append(uid)

        return ready

    def calculate_critical_path(
        self, start_uid: str, end_uid: str, _progress_map: dict[str, "UnifiedProgress"]
    ) -> list[str]:
        """
        Calculate the critical path considering progress requirements.

        This finds the path with the most remaining work.

        Args:
            start_uid: Starting entity,
            end_uid: Target entity,
            progress_map: Current progress

        Returns:
            List of UIDs forming the critical path
        """
        # This would implement a modified critical path algorithm
        # that considers progress requirements
        # For now, return simple path
        return [start_uid, end_uid]


# ============================================================================
# PROGRESS-AWARE BUILDER
# ============================================================================


class ProgressAwareRelationshipBuilder(RelationshipBuilder):
    """
    Builder for creating progress-aware relationships.
    """

    graph: ProgressAwareRelationshipGraph  # Override parent type annotation

    def __init__(self, graph: ProgressAwareRelationshipGraph | None = None) -> None:
        self.graph = graph or ProgressAwareRelationshipGraph()
        self._from_uid: str | None = None
        self._completion: float = 100.0
        self._mastery: float = 0.0

    def with_completion(self, percentage: float) -> "ProgressAwareRelationshipBuilder":
        """Set required completion percentage"""
        self._completion = percentage
        return self

    def with_mastery(self, level: float) -> "ProgressAwareRelationshipBuilder":
        """Set required mastery level"""
        self._mastery = level
        return self

    def blocks_with_progress(
        self, uid: str, completion: float = 100.0
    ) -> "ProgressAwareRelationshipBuilder":
        """Add blocking relationship with progress requirement"""
        if self._from_uid:
            self.graph.add_progress_relationship(
                self._from_uid,
                uid,
                RelationshipType.BLOCKS,
                required_completion=completion,
                required_mastery=self._mastery,
            )
        return self

    def requires_with_mastery(
        self, uid: str, mastery: float = SystemConstants.DEFAULT_CONFIDENCE_THRESHOLD
    ) -> "ProgressAwareRelationshipBuilder":
        """Add requirement with mastery level"""
        if self._from_uid:
            self.graph.add_progress_relationship(
                self._from_uid,
                uid,
                RelationshipType.REQUIRES,
                required_completion=self._completion,
                required_mastery=mastery,
            )
        return self

    def prerequisite_with_mastery(
        self, uid: str, mastery: float = SystemConstants.MASTERY_THRESHOLD
    ) -> "ProgressAwareRelationshipBuilder":
        """Add prerequisite with mastery requirement"""
        if self._from_uid:
            self.graph.add_progress_relationship(
                self._from_uid,
                uid,
                RelationshipType.PREREQUISITE_FOR,
                required_completion=100.0,  # Prerequisites must be complete
                required_mastery=mastery,
            )
        return self


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_dependency(
    from_uid: str, to_uid: str, metadata: dict[str, Any] | None = None
) -> EntityRelationship:
    """Create a simple dependency relationship"""
    return EntityRelationship(
        from_uid=from_uid,
        to_uid=to_uid,
        relationship_type=RelationshipType.BLOCKS,
        metadata=metadata or {},
    )


def create_hierarchy(
    parent_uid: str, child_uid: str, metadata: dict[str, Any] | None = None
) -> EntityRelationship:
    """Create a parent-child hierarchy relationship"""
    return EntityRelationship(
        from_uid=child_uid,
        to_uid=parent_uid,
        relationship_type=RelationshipType.CHILD_OF,
        metadata=metadata or {},
    )


def create_progress_dependency(
    from_uid: str,
    to_uid: str,
    required_completion: float = 100.0,
    required_mastery: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> ProgressAwareRelationship:
    """Create a progress-aware dependency relationship"""
    # ProgressAwareRelationship inherits all fields from EntityRelationship
    # and adds progress-specific fields
    return ProgressAwareRelationship(
        from_uid=from_uid,
        to_uid=to_uid,
        relationship_type=RelationshipType.BLOCKS,
        metadata=metadata or {},
        # Progress-specific fields
        required_completion_percentage=required_completion,
        required_mastery_level=required_mastery,
        required_practice_count=0,
        required_time_spent_minutes=0,
        required_quality_score=0.0,
        required_success_rate=0.0,
    )


def create_task_hierarchy(parent_uid: str, child_uids: list[str]) -> RelationshipGraph:
    """Helper to create a task hierarchy"""
    builder = RelationshipBuilder()

    for child_uid in child_uids:
        builder.from_entity(parent_uid).parent_of(child_uid)

    return builder.build()


def create_dependency_chain(uids: list[str]) -> RelationshipGraph:
    """Helper to create a dependency chain (A -> B -> C)"""
    builder = RelationshipBuilder()

    for i in range(len(uids) - 1):
        builder.from_entity(uids[i]).blocks(uids[i + 1])

    return builder.build()


def create_habit_chain(trigger_uid: str, habit_uids: list[str]) -> RelationshipGraph:
    """Helper to create a habit chain"""
    builder = RelationshipBuilder()

    builder.from_entity(trigger_uid).triggers(habit_uids[0])

    for i in range(len(habit_uids) - 1):
        builder.from_entity(habit_uids[i]).triggers(habit_uids[i + 1])

    return builder.build()
