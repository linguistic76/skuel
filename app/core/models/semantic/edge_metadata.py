"""
Edge Metadata Models
====================

Metadata stored on Neo4j relationship edges for Phase 4 graph-native migration.

Phase 4 Graph-Native Migration (October 6, 2025):
- Rich edge properties instead of simple relationships
- Confidence, strength, semantic distance on every edge
- Learning properties: difficulty gaps, typical order
- Temporal tracking: when created, how often traversed
- User-specific relationships possible

See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md Phase 4
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EdgeMetadata:
    """
    Metadata stored on Neo4j relationship edges.

    This provides rich context for every relationship in the graph:
    - Semantic properties: confidence, strength, distance
    - Learning properties: difficulty gaps, typical learning order
    - Temporal properties: creation time, traversal tracking
    - Source tracking: manual, inferred, AI-generated
    """

    # =========================================================================
    # SEMANTIC PROPERTIES
    # =========================================================================

    confidence: float = 1.0
    """
    How confident are we in this relationship? (0-1 scale)

    - 1.0: Explicitly defined by user or domain expert
    - 0.7-0.9: Inferred from strong signals (content analysis, co-occurrence)
    - 0.4-0.6: Suggested by AI, needs validation
    - 0.1-0.3: Weak signal, exploratory connection
    """

    strength: float = 1.0
    """
    How strong is this connection? (0-1 scale)

    - 1.0: Critical prerequisite, must understand to proceed
    - 0.7-0.9: Important relationship, strongly recommended
    - 0.4-0.6: Helpful relationship, good to know
    - 0.1-0.3: Tangential relationship, optional context
    """

    semantic_distance: float | None = None
    """
    Vector embedding distance between entities (0-1 scale, lower = more similar).

    Computed from content embeddings when available.
    Useful for ranking search results and discovering related concepts.
    """

    # =========================================================================
    # LEARNING PROPERTIES
    # =========================================================================

    difficulty_gap: float | None = None
    """
    Difficulty delta between source and target nodes.

    Positive values: Target is harder than source (typical prerequisite)
    Negative values: Target is easier (review relationship)
    Zero: Similar difficulty level (lateral relationship)
    """

    typical_learning_order: int | None = None
    """
    Suggested sequence number in learning path (1-indexed).

    For curriculum planning - tracks where this relationship typically
    appears in learning sequences. Multiple relationships can have same order
    (parallel learning).
    """

    co_occurrence_count: int = 0
    """
    How often these entities appear together in learning contexts.

    Incremented when:
    - Both appear in same learning step
    - Both appear in same task
    - Both appear in same journal entry
    - Both appear in same conversation

    Higher counts suggest stronger practical connection.
    """

    # =========================================================================
    # TEMPORAL PROPERTIES
    # =========================================================================

    created_at: datetime = field(default_factory=datetime.now)
    """When this relationship was created."""

    last_traversed: datetime | None = None
    """
    When this relationship was last traversed in a query or learning path.

    Used for:
    - Tracking relationship usage patterns
    - Identifying frequently-used vs dormant relationships
    - Temporal analysis of learning patterns
    """

    traversal_count: int = 0
    """
    How many times this relationship has been traversed.

    Incremented when:
    - Relationship queried via get_prerequisites(), get_enables(), etc.
    - Learning path includes this relationship
    - User explicitly navigates this connection

    High counts indicate important, frequently-used relationships.
    """

    # =========================================================================
    # USER-SPECIFIC PROPERTIES
    # =========================================================================

    user_specific: bool = False
    """
    Is this relationship user-specific?

    True: Relationship exists only for this user (personalized learning)
    False: Global relationship, visible to all users
    """

    user_uid: str | None = None
    """
    UID of user this relationship belongs to (if user_specific=True).

    Enables personalized learning paths while maintaining global graph structure.
    """

    # =========================================================================
    # SOURCE TRACKING
    # =========================================================================

    source: str = "manual"
    """
    How was this relationship created? (provenance classification)

    - "manual": Explicitly created by user or domain expert
    - "inferred": Automatically inferred from content analysis
    - "ai_generated": Suggested by AI/LLM
    - "user_created": Created by user during learning
    - "curriculum": Defined in curriculum/learning path
    - "semantic": Discovered via semantic similarity
    - "expert_verified": Verified by domain expert
    - "research_verified": Backed by research paper
    """

    evidence: list[str] = field(default_factory=list)
    """
    Why should we trust this relationship? (supporting references)

    Multiple pieces of evidence can support one relationship:
    - Citations: "Chapter 3, Deep Work by Cal Newport"
    - Data: "87% prerequisite completion correlation (n=1,247)"
    - Expert verification: "Verified by Dr. Smith (Stanford CS) on 2024-03-15"
    - User observations: "Noticed while working on Project Apollo"
    - Curriculum alignment: "ACM CS2023 curriculum sequence"
    - Research: "Smith et al. (2023) - Learning sequence analysis"

    Evidence is COMPLEMENTARY to source:
    - source = classification (categorical: manual, ai_generated, etc.)
    - evidence = grounding (factual references: citations, data, observations)
    """

    notes: str | None = None
    """
    Additional human context not captured by evidence.

    Useful for:
    - Optional/conditional relationships
    - Domain-specific considerations
    - Historical context
    - Future considerations
    """

    # =========================================================================
    # CONVERSION METHODS
    # =========================================================================

    def to_neo4j_properties(self) -> dict[str, Any]:
        """
        Convert to Neo4j-compatible properties for edge creation.

        Only includes non-None values to keep edges lightweight.
        Datetimes converted to ISO format strings.
        """
        props = {
            "confidence": self.confidence,
            "strength": self.strength,
            "created_at": self.created_at.isoformat(),
            "traversal_count": self.traversal_count,
            "source": self.source,
        }

        # Optional semantic properties
        if self.semantic_distance is not None:
            props["semantic_distance"] = self.semantic_distance

        # Optional learning properties
        if self.difficulty_gap is not None:
            props["difficulty_gap"] = self.difficulty_gap
        if self.typical_learning_order is not None:
            props["typical_learning_order"] = self.typical_learning_order
        if self.co_occurrence_count > 0:
            props["co_occurrence_count"] = self.co_occurrence_count

        # Optional temporal properties
        if self.last_traversed:
            props["last_traversed"] = self.last_traversed.isoformat()

        # Optional user-specific properties
        if self.user_specific:
            props["user_specific"] = True
            if self.user_uid:
                props["user_uid"] = self.user_uid

        # Optional evidence (stored as JSON array in Neo4j)
        if self.evidence:
            props["evidence"] = self.evidence

        # Optional notes
        if self.notes:
            props["notes"] = self.notes

        return props

    @classmethod
    def from_neo4j_properties(cls, props: dict[str, Any]) -> "EdgeMetadata":
        """
        Reconstruct EdgeMetadata from Neo4j edge properties.

        Handles missing properties gracefully with defaults.
        Converts ISO datetime strings back to datetime objects.
        """
        return cls(
            confidence=props.get("confidence", 1.0),
            strength=props.get("strength", 1.0),
            semantic_distance=props.get("semantic_distance"),
            difficulty_gap=props.get("difficulty_gap"),
            typical_learning_order=props.get("typical_learning_order"),
            co_occurrence_count=props.get("co_occurrence_count", 0),
            created_at=datetime.fromisoformat(props["created_at"])
            if "created_at" in props
            else datetime.now(),
            last_traversed=datetime.fromisoformat(props["last_traversed"])
            if props.get("last_traversed")
            else None,
            traversal_count=props.get("traversal_count", 0),
            user_specific=props.get("user_specific", False),
            user_uid=props.get("user_uid"),
            source=props.get("source", "manual"),
            evidence=props.get("evidence", []),
            notes=props.get("notes"),
        )

    # =========================================================================
    # BUSINESS LOGIC METHODS
    # =========================================================================

    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence relationship (>= 0.7)."""
        return self.confidence >= 0.7

    def is_strong_connection(self) -> bool:
        """Check if this is a strong connection (>= 0.7)."""
        return self.strength >= 0.7

    def is_critical_prerequisite(self) -> bool:
        """Check if this is a critical prerequisite (high confidence + strength)."""
        return self.is_high_confidence() and self.is_strong_connection()

    def is_frequently_traversed(self) -> bool:
        """Check if this relationship is frequently used (>= 10 traversals)."""
        return self.traversal_count >= 10

    def increment_traversal(self) -> "EdgeMetadata":
        """
        Increment traversal count and update last_traversed timestamp.

        Returns new EdgeMetadata instance (frozen dataclass pattern).
        """
        return EdgeMetadata(
            confidence=self.confidence,
            strength=self.strength,
            semantic_distance=self.semantic_distance,
            difficulty_gap=self.difficulty_gap,
            typical_learning_order=self.typical_learning_order,
            co_occurrence_count=self.co_occurrence_count,
            created_at=self.created_at,
            last_traversed=datetime.now(),
            traversal_count=self.traversal_count + 1,
            user_specific=self.user_specific,
            user_uid=self.user_uid,
            source=self.source,
            evidence=self.evidence,
            notes=self.notes,
        )

    def increment_co_occurrence(self) -> "EdgeMetadata":
        """
        Increment co-occurrence count.

        Returns new EdgeMetadata instance (frozen dataclass pattern).
        """
        return EdgeMetadata(
            confidence=self.confidence,
            strength=self.strength,
            semantic_distance=self.semantic_distance,
            difficulty_gap=self.difficulty_gap,
            typical_learning_order=self.typical_learning_order,
            co_occurrence_count=self.co_occurrence_count + 1,
            created_at=self.created_at,
            last_traversed=self.last_traversed,
            traversal_count=self.traversal_count,
            user_specific=self.user_specific,
            user_uid=self.user_uid,
            source=self.source,
            evidence=self.evidence,
            notes=self.notes,
        )

    # =========================================================================
    # EVIDENCE METHODS (Phase 4 - November 23, 2025)
    # =========================================================================

    def has_evidence(self) -> bool:
        """Check if this relationship has supporting evidence."""
        return len(self.evidence) > 0

    def is_well_supported(self) -> bool:
        """Check if this relationship has strong evidence (3+ sources)."""
        return len(self.evidence) >= 3

    def add_evidence(self, evidence_item: str) -> "EdgeMetadata":
        """
        Add evidence to relationship.

        Returns new EdgeMetadata instance (frozen dataclass pattern).

        Example:
            metadata = metadata.add_evidence(
                "Verified by Django core team (2024-01-15)"
            )
        """
        return EdgeMetadata(
            confidence=self.confidence,
            strength=self.strength,
            semantic_distance=self.semantic_distance,
            difficulty_gap=self.difficulty_gap,
            typical_learning_order=self.typical_learning_order,
            co_occurrence_count=self.co_occurrence_count,
            created_at=self.created_at,
            last_traversed=self.last_traversed,
            traversal_count=self.traversal_count,
            user_specific=self.user_specific,
            user_uid=self.user_uid,
            source=self.source,
            evidence=[*self.evidence, evidence_item],
            notes=self.notes,
        )

    def get_citation_text(self) -> str:
        """
        Format evidence as citation text for Askesis responses.

        Returns:
            Formatted string with source and evidence
        """
        lines = [f"Source: {self._format_source()}"]

        if self.evidence:
            lines.append("\nEvidence:")
            for i, item in enumerate(self.evidence, 1):
                lines.append(f"  {i}. {item}")

        if self.notes:
            lines.append(f"\nNote: {self.notes}")

        return "\n".join(lines)

    def _format_source(self) -> str:
        """Format source as human-readable text."""
        source_labels = {
            "manual": "Manually created",
            "expert_verified": "Expert-verified",
            "curriculum": "SKUEL curriculum",
            "ai_generated": "AI-suggested",
            "inferred": "Automatically inferred",
            "research_verified": "Research-backed",
            "user_created": "User observation",
            "semantic": "Semantic similarity",
        }
        return source_labels.get(self.source, self.source)

    def __str__(self) -> str:
        """String representation for debugging."""
        return (
            f"EdgeMetadata(confidence={self.confidence:.2f}, "
            f"strength={self.strength:.2f}, "
            f"source={self.source}, "
            f"traversals={self.traversal_count})"
        )

    def __repr__(self) -> str:
        """Developer representation."""
        return (
            f"EdgeMetadata(confidence={self.confidence}, strength={self.strength}, "
            f"semantic_distance={self.semantic_distance}, "
            f"difficulty_gap={self.difficulty_gap}, "
            f"source='{self.source}', traversal_count={self.traversal_count})"
        )


# =========================================================================
# HELPER FUNCTIONS
# =========================================================================


def create_prerequisite_metadata(
    confidence: float = 1.0, difficulty_gap: float | None = None, notes: str | None = None
) -> EdgeMetadata:
    """
    Create metadata for a PREREQUISITE relationship.

    Defaults:
    - High strength (0.9) - prerequisites are important
    - Manual source
    """
    return EdgeMetadata(
        confidence=confidence,
        strength=0.9,  # Prerequisites are typically strong connections
        difficulty_gap=difficulty_gap,
        source="manual",
        notes=notes,
    )


def create_enables_metadata(
    confidence: float = 1.0, strength: float = 0.8, notes: str | None = None
) -> EdgeMetadata:
    """
    Create metadata for an ENABLES relationship.

    Defaults:
    - Medium-high strength (0.8)
    - Manual source
    """
    return EdgeMetadata(confidence=confidence, strength=strength, source="manual", notes=notes)


def create_related_metadata(
    confidence: float = 0.7, semantic_distance: float | None = None, notes: str | None = None
) -> EdgeMetadata:
    """
    Create metadata for a RELATED_TO relationship.

    Defaults:
    - Medium confidence (0.7) - related concepts may be inferred
    - Medium strength (0.6) - related but not critical
    - Inferred source
    """
    return EdgeMetadata(
        confidence=confidence,
        strength=0.6,  # Related concepts are helpful but not critical
        semantic_distance=semantic_distance,
        source="inferred",
        notes=notes,
    )


def create_ai_inferred_metadata(
    confidence: float = 0.5, strength: float = 0.5, semantic_distance: float | None = None
) -> EdgeMetadata:
    """
    Create metadata for AI-inferred relationships.

    Defaults:
    - Medium confidence (0.5) - needs validation
    - Medium strength (0.5) - exploratory
    - AI-generated source
    """
    return EdgeMetadata(
        confidence=confidence,
        strength=strength,
        semantic_distance=semantic_distance,
        source="ai_generated",
    )


# =========================================================================
# EVIDENCE-AWARE HELPER FUNCTIONS (Phase 4 - November 23, 2025)
# =========================================================================


def create_cited_metadata(
    source: str,
    evidence: list[str],
    confidence: float = 0.9,
    strength: float = 0.8,
    notes: str | None = None,
) -> EdgeMetadata:
    """
    Create well-documented relationship metadata with citations.

    Use for expert-verified or research-backed relationships.

    Args:
        source: Provenance classification (e.g., "expert_verified", "curriculum")
        evidence: List of supporting references/citations
        confidence: Relationship confidence (default 0.9 - high quality)
        strength: Relationship strength (default 0.8 - important)
        notes: Optional context notes

    Returns:
        EdgeMetadata with complete provenance and evidence

    Example:
        metadata = create_cited_metadata(
            source="expert_verified",
            evidence=[
                "Django Documentation Ch. 3",
                "92% prerequisite correlation (n=2,145)",
                "Verified by Django core team (2024-01-15)"
            ],
            notes="Critical for MVC understanding"
        )
    """
    return EdgeMetadata(
        confidence=confidence,
        strength=strength,
        source=source,
        evidence=evidence,
        notes=notes,
    )


def create_research_backed_metadata(
    paper_citation: str,
    confidence: float = 0.85,
    strength: float = 0.8,
    additional_evidence: list[str] | None = None,
) -> EdgeMetadata:
    """
    Create relationship backed by research paper.

    Args:
        paper_citation: Full research paper citation
        confidence: Relationship confidence (default 0.85 - research-backed)
        strength: Relationship strength (default 0.8 - important)
        additional_evidence: Optional additional evidence items

    Returns:
        EdgeMetadata with research citation as primary evidence

    Example:
        metadata = create_research_backed_metadata(
            paper_citation="Smith et al. (2023) - Learning Sequence Analysis. CS Education Review.",
            additional_evidence=["n=1,247 learners", "p < 0.001"]
        )
    """
    evidence = [paper_citation]
    if additional_evidence:
        evidence.extend(additional_evidence)

    return EdgeMetadata(
        confidence=confidence,
        strength=strength,
        source="research_verified",
        evidence=evidence,
    )


def create_user_observation_metadata(
    observation: str,
    context: str | None = None,
    confidence: float = 0.7,
    strength: float = 0.6,
) -> EdgeMetadata:
    """
    Create relationship from user observation.

    Args:
        observation: User's observation about the relationship
        context: Optional context (project, situation, domain)
        confidence: Relationship confidence (default 0.7 - user observation)
        strength: Relationship strength (default 0.6 - helpful but not critical)

    Returns:
        EdgeMetadata with user observation as evidence

    Example:
        metadata = create_user_observation_metadata(
            observation="Required async understanding for WebSocket implementation",
            context="Project Apollo - real-time dashboard"
        )
    """
    evidence = [observation]

    return EdgeMetadata(
        confidence=confidence,
        strength=strength,
        source="user_created",
        evidence=evidence,
        notes=context,
    )
