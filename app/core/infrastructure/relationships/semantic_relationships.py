"""
Semantic Relationship System with RDF-Inspired Precision
========================================================

This module implements RDF triple thinking for semantic precision in relationships.
Rather than generic "REQUIRES_KNOWLEDGE" or "RELATED_TO", relationships carry precise semantic
meaning that makes the knowledge graph inherently more intelligent and queryable.

Key Principles:
- Every relationship carries semantic meaning
- Namespaces organize relationships by domain
- Triples (subject-predicate-object) are first-class citizens
- Relationships can carry metadata for richer context
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from core.constants import ConfidenceLevel
from core.models.enums import RelationshipType


class RelationshipNamespace(str, Enum):
    """
    RDF-inspired namespaces for organizing relationships by domain.

    Namespaces help organize and discover related relationship types,
    making it clear what domain a relationship belongs to.
    """

    LEARN = "learn"  # Learning/knowledge relationships
    TASK = "task"  # Task management relationships
    HABIT = "habit"  # Habit tracking relationships
    CROSS = "cross"  # Cross-domain relationships
    TIME = "time"  # Temporal relationships
    SKILL = "skill"  # Skill development relationships
    CONCEPT = "concept"  # Conceptual/theoretical relationships
    MOC = "moc"  # Map of Content relationships


class SemanticRelationshipType(str, Enum):
    """
    Semantically precise relationship types with namespace prefixes.

    These replace generic relationships like REQUIRES with specific semantic
    meanings that enable more intelligent queries and reasoning.
    """

    # ========== Learning Domain (learn:) ==========
    # Knowledge prerequisites and dependencies
    REQUIRES_THEORETICAL_UNDERSTANDING = "learn:requires_theoretical_understanding"
    REQUIRES_PRACTICAL_APPLICATION = "learn:requires_practical_application"
    REQUIRES_CONCEPTUAL_FOUNDATION = "learn:requires_conceptual_foundation"
    REQUIRES_TOOL_PROFICIENCY = "learn:requires_tool_proficiency"

    # Knowledge building and progression
    BUILDS_MENTAL_MODEL = "learn:builds_mental_model"
    EXTENDS_PATTERN = "learn:extends_pattern"
    DEEPENS_UNDERSTANDING = "learn:deepens_understanding"
    PROVIDES_FOUNDATION_FOR = "learn:provides_foundation_for"
    PROVIDES_PRACTICAL_APPLICATION = "learn:provides_practical_application"
    REINFORCES_KNOWLEDGE = "learn:reinforces_knowledge"
    INFORMED_BY_KNOWLEDGE = "learn:informed_by_knowledge"

    # Knowledge relationships
    CONTRASTS_WITH = "learn:contrasts_with"
    COMPLEMENTS = "learn:complements"
    ALTERNATIVE_APPROACH_TO = "learn:alternative_approach_to"
    SIMPLIFIES = "learn:simplifies"
    ELABORATES_ON = "learn:elaborates_on"
    ANALOGOUS_TO = "learn:analogous_to"
    REQUIRES_KNOWLEDGE = "learn:requires_knowledge"
    BUILDS_ON_FOUNDATION = "learn:builds_on_foundation"

    # ========== Task Domain (task:) ==========
    # Task dependencies
    BLOCKS_UNTIL_COMPLETE = "task:blocks_until_complete"
    ENABLES_START_OF = "task:enables_start_of"
    MUST_COMPLETE_BEFORE = "task:must_complete_before"
    CAN_PARALLEL_WITH = "task:can_parallel_with"
    CONTRIBUTES_TO_GOAL = "task:contributes_to_goal"
    SUPPORTS_GOAL_ACHIEVEMENT = "task:supports_goal_achievement"
    ENABLES_ACHIEVEMENT = "task:enables_achievement"

    # Task relationships
    SHARES_RESOURCES_WITH = "task:shares_resources_with"
    PRODUCES_INPUT_FOR = "task:produces_input_for"
    VALIDATES_OUTPUT_OF = "task:validates_output_of"
    REPLACES_DEPRECATED = "task:replaces_deprecated"

    # ========== Habit Domain (habit:) ==========
    # Habit chaining and progression
    TRIGGERS_AFTER = "habit:triggers_after"
    REINFORCES = "habit:reinforces"
    CHAINS_WITH = "habit:chains_with"
    SUBSTITUTES_FOR = "habit:substitutes_for"
    REINFORCES_THROUGH_REPETITION = "habit:reinforces_through_repetition"

    # Habit impact
    STRENGTHENS_PRACTICE = "habit:strengthens_practice"
    MAINTAINS_SKILL = "habit:maintains_skill"
    BUILDS_CAPACITY_FOR = "habit:builds_capacity_for"
    ALIGNS_WITH_PRINCIPLE = "habit:aligns_with_principle"

    # ========== Cross-Domain (cross:) ==========
    # Learning to practice bridges
    IMPLEMENTS_VIA_TASK = "cross:implements_via_task"
    PRACTICES_VIA_HABIT = "cross:practices_via_habit"
    PRACTICES_VIA_EVENT = "cross:practices_via_event"
    DEMONSTRATES_IN_PROJECT = "cross:demonstrates_in_project"
    APPLIES_KNOWLEDGE_TO = "cross:applies_knowledge_to"

    # Discovery and insights
    DISCOVERED_THROUGH = "cross:discovered_through"
    REVEALS_PATTERN_IN = "cross:reveals_pattern_in"
    SHARES_PRINCIPLE_WITH = "cross:shares_principle_with"
    CONNECTS_DOMAINS = "cross:connects_domains"
    SUPPORTS_ACHIEVEMENT = "cross:supports_achievement"
    RELATED_TO = "cross:related_to"

    # ========== Skill Domain (skill:) ==========
    # Skill development
    DEVELOPS_SKILL = "skill:develops_skill"
    PRACTICES_TECHNIQUE = "skill:practices_technique"
    PRACTICES_SKILL = "skill:practices_skill"
    MASTERS_THROUGH = "skill:masters_through"
    REQUIRES_SKILL_LEVEL = "skill:requires_skill_level"

    # ========== Conceptual Domain (concept:) ==========
    # Theoretical relationships
    DERIVES_FROM = "concept:derives_from"
    GENERALIZES = "concept:generalizes"
    SPECIALIZES = "concept:specializes"
    INSTANTIATES = "concept:instantiates"
    ABSTRACTS = "concept:abstracts"
    HAS_BROADER_CONCEPT = "concept:has_broader_concept"
    HAS_NARROWER_CONCEPT = "concept:has_narrower_concept"
    CHILD_OF = "concept:child_of"
    PART_OF_SYSTEM = "concept:part_of_system"

    # ========== Temporal Domain (time:) ==========
    # Time-based relationships
    OCCURS_BEFORE = "time:occurs_before"
    OCCURS_AFTER = "time:occurs_after"
    OCCURS_DURING = "time:occurs_during"
    DEADLINE_FOR = "time:deadline_for"
    SCHEDULED_WITH = "time:scheduled_with"

    # ========== Map of Content Domain (moc:) ==========
    # Content organization and navigation
    ORGANIZED_IN_MOC = "moc:organized_in"
    FEATURED_IN_MOC = "moc:featured_in"
    INTRODUCES_TOPIC = "moc:introduces_topic"
    PROVIDES_OVERVIEW_OF = "moc:provides_overview_of"

    # MOC relationships
    RELATED_MOC = "moc:related_to"
    PARENT_MOC_OF = "moc:parent_of"
    CHILD_MOC_OF = "moc:child_of"
    EXTENDS_MOC = "moc:extends"

    # Content aggregation
    AGGREGATES_KNOWLEDGE = "moc:aggregates_knowledge"
    BRIDGES_DOMAINS = "moc:bridges_domains"
    MAPS_LEARNING_PATH = "moc:maps_learning_path"
    CONNECTS_PRINCIPLES = "moc:connects_principles"

    @classmethod
    def to_semantic(cls, generic_type: RelationshipType) -> "SemanticRelationshipType":
        """
        Convert generic RelationshipType to semantic equivalent.

        This enables progressive enhancement from generic to semantic relationships.
        Migration path: generic → semantic with explicit meaning.
        """
        mapping = {
            RelationshipType.REQUIRES: cls.REQUIRES_CONCEPTUAL_FOUNDATION,
            RelationshipType.BLOCKS: cls.BLOCKS_UNTIL_COMPLETE,
            RelationshipType.ENABLES: cls.ENABLES_START_OF,
            RelationshipType.RELATED_TO: cls.SHARES_PRINCIPLE_WITH,
            RelationshipType.PREREQUISITE_FOR: cls.REQUIRES_THEORETICAL_UNDERSTANDING,
            RelationshipType.BEFORE: cls.OCCURS_BEFORE,
            RelationshipType.AFTER: cls.OCCURS_AFTER,
            RelationshipType.SUPPORTS: cls.PROVIDES_FOUNDATION_FOR,
            RelationshipType.CONTINUES: cls.EXTENDS_PATTERN,
            RelationshipType.REPLACES: cls.REPLACES_DEPRECATED,
            RelationshipType.PART_OF: cls.DEMONSTRATES_IN_PROJECT,
        }
        return mapping.get(generic_type, cls.SHARES_PRINCIPLE_WITH)

    def to_neo4j_name(self) -> str:
        """Convert semantic type to Neo4j relationship name."""
        return self.local_name.upper()

    @property
    def is_blocking(self) -> bool:
        """Check if this semantic type represents a blocking relationship."""
        blocking_types = {
            self.BLOCKS_UNTIL_COMPLETE,
            self.MUST_COMPLETE_BEFORE,
            self.REQUIRES_THEORETICAL_UNDERSTANDING,
            self.REQUIRES_PRACTICAL_APPLICATION,
            self.REQUIRES_CONCEPTUAL_FOUNDATION,
            self.REQUIRES_TOOL_PROFICIENCY,
        }
        return self in blocking_types

    @property
    def namespace(self) -> str:
        """Extract namespace from relationship type."""
        return self.value.split(":", 1)[0] if ":" in self.value else ""

    @property
    def local_name(self) -> str:
        """Extract local name without namespace prefix."""
        return self.value.split(":", 1)[1] if ":" in self.value else self.value

    def get_inverse(self) -> Optional["SemanticRelationshipType"]:
        """Get the inverse relationship if one exists."""
        inverses = {
            self.REQUIRES_THEORETICAL_UNDERSTANDING: self.PROVIDES_FOUNDATION_FOR,
            self.PROVIDES_FOUNDATION_FOR: self.REQUIRES_THEORETICAL_UNDERSTANDING,
            self.BLOCKS_UNTIL_COMPLETE: self.ENABLES_START_OF,
            self.ENABLES_START_OF: self.BLOCKS_UNTIL_COMPLETE,
            self.OCCURS_BEFORE: self.OCCURS_AFTER,
            self.OCCURS_AFTER: self.OCCURS_BEFORE,
            self.GENERALIZES: self.SPECIALIZES,
            self.SPECIALIZES: self.GENERALIZES,
            self.SIMPLIFIES: self.ELABORATES_ON,
            self.ELABORATES_ON: self.SIMPLIFIES,
        }
        return inverses.get(self)


@dataclass
class RelationshipMetadata:
    """
    Additional context for relationships, inspired by RDF reification.

    This allows relationships to carry rich metadata about confidence,
    source, temporal validity, and other contextual information.
    """

    confidence: float = 1.0  # Confidence in this relationship (0-1)
    source: str | None = None  # Where this relationship came from
    created_at: datetime = field(default_factory=datetime.now)
    valid_from: datetime | None = None  # When relationship becomes valid
    valid_until: datetime | None = None  # When relationship expires
    strength: float = 1.0  # Strength of relationship (0-1)
    evidence: list[str] = field(default_factory=list)  # Supporting evidence
    notes: str | None = None  # Human-readable notes
    properties: dict[str, Any] = field(default_factory=dict)  # Additional properties

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if relationship is valid at given time."""
        if self.valid_from and timestamp < self.valid_from:
            return False
        return not (self.valid_until and timestamp > self.valid_until)

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert metadata to Neo4j relationship properties."""
        props = {
            "confidence": self.confidence,
            "strength": self.strength,
            "created_at": self.created_at.isoformat(),
        }
        if self.source:
            props["source"] = self.source
        if self.valid_from:
            props["valid_from"] = self.valid_from.isoformat()
        if self.valid_until:
            props["valid_until"] = self.valid_until.isoformat()
        if self.evidence:
            props["evidence"] = self.evidence
        if self.notes:
            props["notes"] = self.notes
        props.update(self.properties)
        return props


@dataclass
class SemanticRelationship:
    """
    A semantic relationship between two entities.

    This represents a directed relationship with semantic meaning,
    confidence scoring, and rich metadata.
    """

    subject_uid: str  # Source entity
    predicate: SemanticRelationshipType  # Relationship type
    object_uid: str  # Target entity
    metadata: RelationshipMetadata = field(default_factory=RelationshipMetadata)

    def __init__(
        self,
        subject_uid: str,
        predicate: SemanticRelationshipType,
        object_uid: str,
        metadata: RelationshipMetadata | None = None,
    ) -> None:
        self.subject_uid = subject_uid
        self.predicate = predicate
        self.object_uid = object_uid
        self.metadata = metadata or RelationshipMetadata()

    def to_triple(self) -> "SemanticTriple":
        """Convert to SemanticTriple format."""
        return SemanticTriple(
            subject=self.subject_uid,
            predicate=self.predicate,
            object=self.object_uid,
            metadata=self.metadata,
        )

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"{self.subject_uid} --[{self.predicate.value}]--> {self.object_uid}"


@dataclass(frozen=True)
class SemanticTriple:
    """
    RDF-inspired triple with semantic precision.

    The fundamental unit of knowledge representation:
    subject-predicate-object with optional metadata.
    """

    subject: str  # Subject URI/ID
    predicate: SemanticRelationshipType  # Semantic relationship
    object: str  # Object URI/ID
    metadata: RelationshipMetadata = field(default_factory=RelationshipMetadata)

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"({self.subject}) --[{self.predicate.local_name}]--> ({self.object})"

    def to_cypher_merge(self) -> str:
        """Convert to Cypher MERGE statement."""
        rel_label = self.predicate.local_name.upper()
        props = self.metadata.to_neo4j_properties()

        # Build properties string
        props_str = ", ".join(f"{k}: ${k}" for k in props)

        return f"""
        MERGE (s {{uid: $subject}})
        MERGE (o {{uid: $object}})
        MERGE (s)-[r:{rel_label}]->(o)
        ON CREATE SET r = {{{props_str}}}
        ON MATCH SET r += {{{props_str}}}
        """

    def to_cypher_params(self) -> dict[str, Any]:
        """Get parameters for Cypher query."""
        params = {
            "subject": self.subject,
            "object": self.object,
        }
        params.update(self.metadata.to_neo4j_properties())
        return params

    def get_inverse(self) -> Optional["SemanticTriple"]:
        """Create inverse triple if relationship has an inverse."""
        inverse_predicate = self.predicate.get_inverse()
        if inverse_predicate:
            return SemanticTriple(
                subject=self.object,
                predicate=inverse_predicate,
                object=self.subject,
                metadata=self.metadata,
            )
        return None


class TripleBuilder:
    """
    Builder for creating semantic triples with consistent patterns.

    Provides fluent interface for constructing triples with metadata.
    """

    def __init__(self, subject: str) -> None:
        self._subject = subject
        self._triples: list[SemanticTriple] = []

    def requires_understanding(
        self, knowledge_uid: str, confidence: float = 1.0
    ) -> "TripleBuilder":
        """Add theoretical understanding requirement."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object=knowledge_uid,
            metadata=RelationshipMetadata(confidence=confidence),
        )
        self._triples.append(triple)
        return self

    def requires_practice(self, skill_uid: str, confidence: float = 1.0) -> "TripleBuilder":
        """Add practical application requirement."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
            object=skill_uid,
            metadata=RelationshipMetadata(confidence=confidence),
        )
        self._triples.append(triple)
        return self

    def builds_model(self, model_uid: str, strength: float = 1.0) -> "TripleBuilder":
        """Add mental model building relationship."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.BUILDS_MENTAL_MODEL,
            object=model_uid,
            metadata=RelationshipMetadata(strength=strength),
        )
        self._triples.append(triple)
        return self

    def enables_task(self, task_uid: str) -> "TripleBuilder":
        """Add task enablement relationship."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.ENABLES_START_OF,
            object=task_uid,
            metadata=RelationshipMetadata(),
        )
        self._triples.append(triple)
        return self

    def practiced_by_habit(self, habit_uid: str, strength: float = 1.0) -> "TripleBuilder":
        """Add habit practice relationship."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.PRACTICES_VIA_HABIT,
            object=habit_uid,
            metadata=RelationshipMetadata(strength=strength),
        )
        self._triples.append(triple)
        return self

    def contrasts_with(self, other_uid: str, notes: str | None = None) -> "TripleBuilder":
        """Add contrasting relationship."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=SemanticRelationshipType.CONTRASTS_WITH,
            object=other_uid,
            metadata=RelationshipMetadata(notes=notes),
        )
        self._triples.append(triple)
        return self

    def custom(
        self, predicate: SemanticRelationshipType, object_uid: str, **metadata_kwargs: Any
    ) -> "TripleBuilder":
        """Add custom semantic relationship."""
        triple = SemanticTriple(
            subject=self._subject,
            predicate=predicate,
            object=object_uid,
            metadata=RelationshipMetadata(**metadata_kwargs),
        )
        self._triples.append(triple)
        return self

    def build(self) -> list[SemanticTriple]:
        """Build and return all triples."""
        return self._triples

    def build_with_inverses(self) -> list[SemanticTriple]:
        """Build triples including inverse relationships where applicable."""
        all_triples = self._triples.copy()
        for triple in self._triples:
            inverse = triple.get_inverse()
            if inverse:
                all_triples.append(inverse)
        return all_triples


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def is_learning_relationship(rel_type: SemanticRelationshipType) -> bool:
    """Check if this is a learning domain relationship."""
    return rel_type.namespace == RelationshipNamespace.LEARN.value


def is_blocking_relationship(rel_type: SemanticRelationshipType) -> bool:
    """Check if this relationship blocks progress."""
    blocking_types = {
        SemanticRelationshipType.BLOCKS_UNTIL_COMPLETE,
        SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
        SemanticRelationshipType.REQUIRES_PRACTICAL_APPLICATION,
        SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
        SemanticRelationshipType.REQUIRES_TOOL_PROFICIENCY,
        SemanticRelationshipType.MUST_COMPLETE_BEFORE,
    }
    return rel_type in blocking_types


def get_relationship_category(rel_type: SemanticRelationshipType) -> str:
    """Get human-readable category for relationship type."""
    categories: dict[str, str] = {
        RelationshipNamespace.LEARN.value: "Learning",
        RelationshipNamespace.TASK.value: "Task Management",
        RelationshipNamespace.HABIT.value: "Habit Development",
        RelationshipNamespace.CROSS.value: "Cross-Domain",
        RelationshipNamespace.SKILL.value: "Skill Development",
        RelationshipNamespace.CONCEPT.value: "Conceptual",
        RelationshipNamespace.TIME.value: "Temporal",
    }
    namespace = rel_type.namespace
    return categories.get(namespace, "General")


def create_learning_path_relationships(
    path_uid: str,
    prerequisite_uids: list[str],
    outcome_uids: list[str],
    concepts_built: list[str] | None = None,
) -> list[SemanticTriple]:
    """
    Create semantic relationships for a learning path.

    This demonstrates how to use semantic relationships for
    rich learning path construction.
    """
    builder = TripleBuilder(path_uid)

    # Add prerequisites with different semantic meanings
    for prereq in prerequisite_uids:
        if prereq.startswith("theory_"):
            builder.requires_understanding(prereq, ConfidenceLevel.HIGH)
        elif prereq.startswith("skill_"):
            builder.requires_practice(prereq, ConfidenceLevel.STANDARD)
        else:
            builder.custom(
                SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION,
                prereq,
                confidence=ConfidenceLevel.STANDARD,
            )

    # Add outcomes
    for outcome in outcome_uids:
        builder.custom(SemanticRelationshipType.PROVIDES_FOUNDATION_FOR, outcome, strength=0.9)

    # Add concepts built
    if concepts_built:
        for concept in concepts_built:
            builder.builds_model(concept, strength=0.8)

    return builder.build()
