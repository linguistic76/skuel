"""
Graph-Native Relationship Modeling
===================================

Applies the Cypher-native approach from unified_relationships.py to
knowledge units and learning paths. Instead of storing UIDs in lists,
relationships become first-class graph edges with properties.

This provides:
- Direct Neo4j edge modeling
- Bidirectional traversal
- Relationship properties and constraints
- Graph algorithms (cycles, dependencies, etc.)
"""

from dataclasses import dataclass
from typing import Any, Protocol

from core.models.enums import RelationshipType
from core.models.unified_relationships import (  # type: ignore[import-not-found]
    EntityRelationship,
    ProgressAwareRelationship,
    ProgressAwareRelationshipGraph,
    RelationshipGraph,
)

# ============================================================================
# KNOWLEDGE RELATIONSHIP EXTENSIONS
# ============================================================================


@dataclass(frozen=True)
class KnowledgeRelationship(EntityRelationship):
    """
    Knowledge-specific relationship with semantic properties.

    Extends base EntityRelationship with knowledge domain concepts.
    """

    # Knowledge-specific metadata
    strength: float = 1.0  # Relationship strength (0.0-1.0)
    confidence: float = 1.0  # Confidence in relationship (0.0-1.0)

    # Semantic properties
    semantic_distance: float | None = None  # From vector embeddings
    co_occurrence_count: int = 0  # How often these appear together

    # Learning context
    difficulty_gap: float | None = None  # Difficulty difference
    typical_learning_order: int | None = None  # Suggested sequence

    def to_cypher_properties(self) -> dict[str, Any]:
        """Convert to properties for Neo4j edge creation"""
        props = {
            "type": self.relationship_type.value,
            "strength": self.strength,
            "confidence": self.confidence,
        }

        if self.semantic_distance is not None:
            props["semantic_distance"] = self.semantic_distance
        if self.co_occurrence_count > 0:
            props["co_occurrence_count"] = self.co_occurrence_count
        if self.difficulty_gap is not None:
            props["difficulty_gap"] = self.difficulty_gap
        if self.typical_learning_order is not None:
            props["typical_learning_order"] = self.typical_learning_order

        # Add base metadata
        props.update(self.metadata)

        return props

    def to_cypher_create(self) -> str:
        """Generate Cypher CREATE statement for this relationship"""
        props_str = ", ".join(f"{k}: ${k}" for k in self.to_cypher_properties())
        return f"""
        MATCH (from:Ku {{uid: $from_uid}})
        MATCH (to:Ku {{uid: $to_uid}})
        CREATE (from)-[r:{self.relationship_type.value} {{{props_str}}}]->(to)
        RETURN r
        """


@dataclass(frozen=True)
class LearningPathRelationship(ProgressAwareRelationship):
    """
    Learning path specific relationship with progress requirements.

    Extends ProgressAwareRelationship for learning paths and steps.
    """

    # Learning path specific
    is_optional: bool = False  # Can be skipped,
    is_review: bool = False  # Review/reinforcement relationship

    # Adaptive learning
    alternative_path_uid: str | None = None  # Alternative if this fails,
    skip_condition: str | None = None  # Condition to skip (e.g., "mastery > 0.9")

    # Time estimates
    estimated_transition_minutes: int = 0  # Time between steps

    def to_cypher_properties(self) -> dict[str, Any]:
        """Convert to properties for Neo4j edge creation"""
        props = {
            "type": self.relationship_type.value,
            "required_completion": self.required_completion_percentage,
            "required_mastery": self.required_mastery_level,
            "is_optional": self.is_optional,
            "is_review": self.is_review,
        }

        if self.alternative_path_uid:
            props["alternative_path_uid"] = self.alternative_path_uid
        if self.skip_condition:
            props["skip_condition"] = self.skip_condition
        if self.estimated_transition_minutes > 0:
            props["estimated_transition_minutes"] = self.estimated_transition_minutes

        # Add progress requirements
        if self.required_practice_count > 0:
            props["required_practice_count"] = self.required_practice_count
        if self.required_time_spent_minutes > 0:
            props["required_time_spent_minutes"] = self.required_time_spent_minutes

        props.update(self.metadata)

        return props


# ============================================================================
# GRAPH-NATIVE ENTITY PROTOCOLS
# ============================================================================


class GraphNativeEntity(Protocol):
    """Protocol for entities that use graph-native relationships"""

    uid: str

    def get_relationships(self) -> list[EntityRelationship]:
        """Get all relationships for this entity"""
        ...

    def to_cypher_node(self) -> str:
        """Convert to Cypher node creation"""
        ...


# ============================================================================
# KNOWLEDGE GRAPH WITH NATIVE RELATIONSHIPS
# ============================================================================


class KnowledgeRelationshipGraph(RelationshipGraph):
    """
    Knowledge-specific relationship graph with semantic operations.
    """

    def add_knowledge_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipType,
        strength: float = 1.0,
        confidence: float = 1.0,
        semantic_distance: float | None = None,
        **kwargs: Any,
    ) -> KnowledgeRelationship:
        """Add a knowledge-specific relationship"""
        relationship = KnowledgeRelationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=relationship_type,
            strength=strength,
            confidence=confidence,
            semantic_distance=semantic_distance,
            **kwargs,
        )

        self.relationships.append(relationship)
        self._update_indexes(relationship)

        return relationship

    def _update_indexes(self, relationship: EntityRelationship) -> None:
        """Update internal indexes"""
        if relationship.from_uid not in self._by_from:
            self._by_from[relationship.from_uid] = []
        self._by_from[relationship.from_uid].append(relationship)

        if relationship.to_uid not in self._by_to:
            self._by_to[relationship.to_uid] = []
        self._by_to[relationship.to_uid].append(relationship)

        if relationship.relationship_type not in self._by_type:
            self._by_type[relationship.relationship_type] = []
        self._by_type[relationship.relationship_type].append(relationship)

    def find_semantic_neighbors(
        self, uid: str, max_distance: float = 0.5, limit: int = 10
    ) -> list[tuple[str, float]]:
        """Find semantically similar knowledge units"""
        neighbors = [
            (rel.to_uid, rel.semantic_distance)
            for rel in self.get_relationships_from(uid)
            if isinstance(rel, KnowledgeRelationship)
            and rel.semantic_distance
            and rel.semantic_distance <= max_distance
        ]

        # Sort by distance
        def get_neighbor_distance(neighbor) -> int:
            return neighbor[1]

        neighbors.sort(key=get_neighbor_distance)

        return neighbors[:limit]

    def find_learning_sequence(self, start_uid: str, goal_uid: str) -> list[str]:
        """Find optimal learning sequence from start to goal"""
        # Use topological sort with learning order
        path = []
        visited = set()

        def dfs(uid: str) -> Any:
            if uid in visited or uid == goal_uid:
                return uid == goal_uid

            visited.add(uid)

            # Get relationships ordered by typical_learning_order
            relationships = self.get_relationships_from(uid)
            knowledge_rels = [r for r in relationships if isinstance(r, KnowledgeRelationship)]

            def get_learning_order(rel) -> int:
                return rel.typical_learning_order or 999

            knowledge_rels.sort(key=get_learning_order)

            for rel in knowledge_rels:
                if rel.relationship_type in {
                    RelationshipType.ENABLES,
                    RelationshipType.PREREQUISITE_FOR,
                } and dfs(rel.to_uid):
                    path.append(uid)
                    return True

            return False

        if dfs(start_uid):
            path.reverse()
            path.append(goal_uid)
            return path

        return []

    def calculate_knowledge_coverage(
        self, learned_uids: set[str], all_uids: set[str]
    ) -> dict[str, float]:
        """Calculate how well learned knowledge covers unlearned topics"""
        coverage = {}

        for unlearned_uid in all_uids - learned_uids:
            # Check how many prerequisites are satisfied
            prerequisites = self.get_dependencies(unlearned_uid)
            if prerequisites:
                satisfied = len(prerequisites & learned_uids)
                coverage[unlearned_uid] = satisfied / len(prerequisites)
            else:
                coverage[unlearned_uid] = 0.0

        return coverage


# ============================================================================
# LEARNING PATH GRAPH WITH PROGRESS
# ============================================================================


class LearningPathGraph(ProgressAwareRelationshipGraph):
    """
    Learning path specific graph with adaptive features.
    """

    def add_learning_step_relationship(
        self,
        from_step_uid: str,
        to_step_uid: str,
        relationship_type: RelationshipType = RelationshipType.ENABLES,
        required_completion: float = 100.0,
        required_mastery: float = 0.0,
        is_optional: bool = False,
        **kwargs: Any,
    ) -> LearningPathRelationship:
        """Add relationship between learning steps"""
        relationship = LearningPathRelationship(
            from_uid=from_step_uid,
            to_uid=to_step_uid,
            relationship_type=relationship_type,
            required_completion_percentage=required_completion,
            required_mastery_level=required_mastery,
            is_optional=is_optional,
            **kwargs,
        )

        self.relationships.append(relationship)
        self._update_indexes(relationship)

        return relationship

    def _update_indexes(self, relationship: EntityRelationship) -> None:
        """Update internal indexes"""
        if relationship.from_uid not in self._by_from:
            self._by_from[relationship.from_uid] = []
        self._by_from[relationship.from_uid].append(relationship)

        if relationship.to_uid not in self._by_to:
            self._by_to[relationship.to_uid] = []
        self._by_to[relationship.to_uid].append(relationship)

        if relationship.relationship_type not in self._by_type:
            self._by_type[relationship.relationship_type] = []
        self._by_type[relationship.relationship_type].append(relationship)

    def get_adaptive_next_step(
        self,
        current_step_uid: str,
        progress_map: dict[str, Any],
        user_performance: dict[str, float],
    ) -> str | None:
        """Get next step based on progress and performance"""
        # Get relationships from current step
        relationships = self.get_relationships_from(current_step_uid)

        for rel in relationships:
            if isinstance(rel, LearningPathRelationship):
                # Check skip condition
                if rel.skip_condition and self._evaluate_condition(
                    rel.skip_condition, user_performance
                ):
                    continue

                # Check if optional and struggling
                if rel.is_optional and user_performance.get("struggling", False):
                    continue

                # Check progress requirements
                if rel.is_satisfied_by_progress(progress_map):
                    return rel.to_uid

                # Try alternative if available
                if rel.alternative_path_uid:
                    return rel.alternative_path_uid

        return None

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a skip condition"""
        # Simple evaluation - in practice would use safe eval
        # Example: "mastery > 0.9"
        if "mastery > " in condition:
            threshold = float(condition.split("> ")[1])
            return context.get("mastery", 0) > threshold
        return False

    def find_review_opportunities(self, completed_steps: set[str]) -> list[str]:
        """Find steps that should be reviewed"""
        review_steps = []

        for step_uid in completed_steps:
            relationships = self.get_relationships_from(step_uid)

            review_steps.extend(
                [
                    rel.to_uid
                    for rel in relationships
                    if isinstance(rel, LearningPathRelationship) and rel.is_review
                ]
            )

        return review_steps


# ============================================================================
# MIGRATION HELPERS
# ============================================================================


def migrate_knowledge_unit_to_graph(
    knowledge_unit: Any, graph: KnowledgeRelationshipGraph | None = None
) -> KnowledgeRelationshipGraph:
    """
    Migrate a KnowledgeUnit with UID lists to graph-native relationships.

    This helps transition from the list-based approach to graph-native.
    """
    if graph is None:
        graph = KnowledgeRelationshipGraph()

    uid = knowledge_unit.uid

    # Convert prerequisite UIDs to relationships
    for prereq_uid in getattr(knowledge_unit, "prerequisite_uids", []):
        graph.add_knowledge_relationship(
            from_uid=prereq_uid, to_uid=uid, relationship_type=RelationshipType.PREREQUISITE_FOR
        )

    # Convert enables UIDs
    for enables_uid in getattr(knowledge_unit, "enables_uids", []):
        graph.add_knowledge_relationship(
            from_uid=uid, to_uid=enables_uid, relationship_type=RelationshipType.ENABLES
        )

    # Convert related UIDs
    for related_uid in getattr(knowledge_unit, "related_concept_uids", []):
        graph.add_knowledge_relationship(
            from_uid=uid,
            to_uid=related_uid,
            relationship_type=RelationshipType.RELATED_TO,
            # Bidirectional
            metadata={"bidirectional": True},
        )

    # Convert parent-child
    from core.services.protocols import HasParentUID

    if isinstance(knowledge_unit, HasParentUID) and knowledge_unit.parent_uid:
        graph.add_knowledge_relationship(
            from_uid=knowledge_unit.parent_uid,
            to_uid=uid,
            relationship_type=RelationshipType.PARENT_OF,
        )

    for child_uid in getattr(knowledge_unit, "child_uids", []):
        graph.add_knowledge_relationship(
            from_uid=uid, to_uid=child_uid, relationship_type=RelationshipType.PARENT_OF
        )

    return graph


def migrate_learning_path_to_graph(
    learning_path: Any, graph: LearningPathGraph | None = None
) -> LearningPathGraph:
    """
    Migrate a LearningPath with embedded steps to graph-native relationships.
    """
    if graph is None:
        graph = LearningPathGraph()

    steps = getattr(learning_path, "steps", [])

    # Create sequential relationships between steps
    for i in range(len(steps) - 1):
        current_step = steps[i]
        next_step = steps[i + 1]

        graph.add_learning_step_relationship(
            from_step_uid=current_step.uid,
            to_step_uid=next_step.uid,
            relationship_type=RelationshipType.ENABLES,
            required_completion=100.0,  # Must complete before moving on
            is_optional=False,
        )

    # Add prerequisite relationships from step data
    for step in steps:
        for prereq_uid in getattr(step, "prerequisite_uids", []):
            graph.add_learning_step_relationship(
                from_step_uid=prereq_uid,
                to_step_uid=step.uid,
                relationship_type=RelationshipType.PREREQUISITE_FOR,
                required_mastery=0.7,  # Need good understanding
            )

    return graph


# ============================================================================
# CYPHER QUERY GENERATORS
# ============================================================================


def generate_relationship_cypher(relationships: list[EntityRelationship]) -> str:
    """
    Generate Cypher query to create relationships in Neo4j.

    This allows direct storage of relationships as edges.
    """
    queries = []

    for rel in relationships:
        if isinstance(rel, KnowledgeRelationship):
            queries.append(rel.to_cypher_create())
        else:
            # Generic relationship
            props = ", ".join(f"{k}: ${k}" for k, v in rel.metadata.items())
            query = f"""
            MATCH (from {{uid: '{rel.from_uid}'}})
            MATCH (to {{uid: '{rel.to_uid}'}})
            CREATE (from)-[:{rel.relationship_type.value} {{{props}}}]->(to)
            """
            queries.append(query)

    return "\n".join(queries)


def load_relationships_from_cypher(cypher_result: list[dict]) -> RelationshipGraph:
    """
    Load relationships from Neo4j query result into graph.

    Reconstructs the graph from database edges.
    """
    graph = RelationshipGraph()

    for record in cypher_result:
        rel_data = record.get("r")  # Relationship data
        if rel_data:
            graph.add_relationship(
                from_uid=rel_data.get("from_uid"),
                to_uid=rel_data.get("to_uid"),
                relationship_type=RelationshipType[rel_data.get("type")],
                metadata=rel_data.get("properties", {}),
            )

    return graph
