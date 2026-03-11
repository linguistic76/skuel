"""
Graph Context Models
====================

Models for graph intelligence responses that combine nodes, relationships,
and cross-domain intelligence into unified context objects.

These models enable the GraphIntelligenceService to return rich, structured
context from Neo4j queries that span multiple domains.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from core.models.enums import Domain

if TYPE_CHECKING:
    from adapters.persistence.neo4j.query.cypher_template import QueryOptimizationStrategy
    from core.infrastructure.database.schema import SchemaContext


class RelationshipStrength(StrEnum):
    """Strength of relationships in graph context."""

    WEAK = "weak"  # Minimal connection
    MODERATE = "moderate"  # Some connection
    STRONG = "strong"  # Significant connection
    CRITICAL = "critical"  # Essential connection


class ContextRelevance(StrEnum):
    """Relevance of context to original query."""

    LOW = "low"  # Tangentially related
    MEDIUM = "medium"  # Moderately related
    HIGH = "high"  # Highly related
    ESSENTIAL = "essential"  # Core to understanding


@dataclass(frozen=True)
class GraphNode:
    """
    Represents a node in the graph context.

    Simplified graph node that can represent any domain entity
    with its core properties and relationships.

    Enhanced with APOC query support for batch operations.
    """

    uid: str
    labels: list[str]
    domain: Domain
    properties: dict[str, Any]

    # Context metadata
    distance_from_origin: int  # How many hops from query node
    relevance: ContextRelevance
    relationship_to_origin: str | None = None  # Type of relationship

    # Query optimization metadata (optional, for APOC batch operations)
    optimization_strategy: "QueryOptimizationStrategy | None" = None

    def to_cypher_params(self) -> dict[str, Any]:
        """
        Convert node to Cypher parameters for batch operations.

        Returns dict format suitable for MERGE operations.
        """
        return {
            "labels": self.labels,
            "id": self.uid,  # Unique lookup key
            "properties": self.properties,
        }

    def validate_against_schema(self, schema: "SchemaContext") -> tuple[bool, list[str]]:
        """
        Validate this node against a schema context.

        Args:
            schema: SchemaContext with label and property definitions

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check if labels exist in schema
        errors.extend(
            [
                f"Label '{label}' not found in schema"
                for label in self.labels
                if not schema.validate_node_label(label)
            ]
        )

        # Check if properties are valid for the labels
        errors.extend(
            [
                f"Property '{prop_name}' not defined for label '{label}'"
                for label in self.labels
                if schema.validate_node_label(label)
                for prop_name in self.properties
                if not schema.validate_property_on_label(label, prop_name)
            ]
        )

        return (len(errors) == 0, errors)


@dataclass(frozen=True)
class GraphRelationship:
    """
    Represents a relationship in the graph context.

    Captures the connection between two nodes with metadata
    about the relationship strength and properties.
    """

    type: str
    start_node_uid: str
    end_node_uid: str
    properties: dict[str, Any]
    strength: RelationshipStrength
    bidirectional: bool = False


@dataclass(frozen=True)
class DomainContext:
    """
    Context from a specific domain.

    Aggregates all nodes and relationships from a particular domain
    that are relevant to the query.
    """

    domain: Domain
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
    node_count: int
    relationship_count: int

    # Domain-specific intelligence
    intelligence_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphContext:
    """
    Complete graph context response.

    THE unified response from GraphIntelligenceService that combines
    nodes, relationships, and cross-domain intelligence.
    """

    origin_uid: str
    origin_domain: Domain
    query_intent: str  # QueryIntent value

    # Core graph data
    all_nodes: list[GraphNode]
    all_relationships: list[GraphRelationship]

    # Domain-specific contexts
    domain_contexts: dict[Domain, DomainContext]

    # Cross-domain intelligence
    cross_domain_insights: list[dict[str, Any]]
    relationship_patterns: dict[str, int]  # relationship_type -> count

    # Metadata
    total_nodes: int
    total_relationships: int
    domains_involved: list[Domain]
    max_depth_reached: int
    query_timestamp: datetime

    # Performance metrics
    neo4j_query_time_ms: float | None = (None,)

    processing_time_ms: float | None = None

    def get_nodes_by_domain(self, domain: Domain) -> list[GraphNode]:
        """Get all nodes from a specific domain."""
        return [node for node in self.all_nodes if node.domain == domain]

    def get_relationships_by_type(self, rel_type: str) -> list[GraphRelationship]:
        """Get all relationships of a specific type."""
        return [rel for rel in self.all_relationships if rel.type == rel_type]

    def get_strongest_relationships(self, limit: int = 10) -> list[GraphRelationship]:
        """Get the strongest relationships in context."""

        def get_strength_value(rel) -> Any:
            strength_values = {
                RelationshipStrength.WEAK: 1,
                RelationshipStrength.MODERATE: 2,
                RelationshipStrength.STRONG: 3,
                RelationshipStrength.CRITICAL: 4,
            }
            return strength_values.get(rel.strength, 0)

        sorted_rels = sorted(self.all_relationships, key=get_strength_value, reverse=True)
        return sorted_rels[:limit]

    def get_connected_domains(self) -> list[Domain]:
        """Get all domains connected to origin via relationships."""
        connected = set()
        for rel in self.all_relationships:
            # Find nodes connected to origin
            for node in self.all_nodes:
                if node.uid in [rel.start_node_uid, rel.end_node_uid]:
                    connected.add(node.domain)
        return list(connected)

    def has_cross_domain_connections(self) -> bool:
        """Check if context spans multiple domains."""
        return len(self.domains_involved) > 1

    def get_summary(self) -> dict[str, Any]:
        """Get concise summary of graph context."""
        return {
            "origin": f"{self.origin_domain.value}:{self.origin_uid}",
            "intent": self.query_intent,
            "total_nodes": self.total_nodes,
            "total_relationships": self.total_relationships,
            "domains": [d.value for d in self.domains_involved],
            "cross_domain": self.has_cross_domain_connections(),
            "depth": self.max_depth_reached,
            "insights_count": len(self.cross_domain_insights),
        }


@dataclass(frozen=True)
class IntelligenceInsight:
    """
    Cross-domain intelligence insight.

    Represents a discovered insight from analyzing graph relationships
    and domain intelligence together.
    """

    insight_type: str  # "pattern", "recommendation", "warning", "opportunity"
    title: str
    description: str

    # Evidence
    supporting_nodes: list[str]  # Node UIDs
    supporting_relationships: list[str]  # Relationship types
    confidence_score: float  # 0.0 - 1.0

    # Actionability
    is_actionable: bool
    suggested_actions: list[str]
    priority: str  # "low", "medium", "high", "critical"

    # Metadata
    domains_involved: list[Domain]
    discovered_at: datetime

    def is_high_confidence(self) -> bool:
        """Check if this is a high-confidence insight."""
        return self.confidence_score >= 0.8

    def is_urgent(self) -> bool:
        """Check if this insight requires urgent attention."""
        return self.priority in ["high", "critical"] and self.is_actionable


# Factory functions


def create_graph_context(
    origin_uid: str,
    origin_domain: Domain,
    query_intent: str,
    nodes: list[GraphNode],
    relationships: list[GraphRelationship],
) -> GraphContext:
    """Create a GraphContext from query results."""

    # Group nodes by domain
    domain_contexts = {}
    for domain in Domain:
        domain_nodes = [n for n in nodes if n.domain == domain]
        if domain_nodes:
            domain_rels = [
                r
                for r in relationships
                if any(n.uid in [r.start_node_uid, r.end_node_uid] for n in domain_nodes)
            ]

            domain_contexts[domain] = DomainContext(
                domain=domain,
                nodes=domain_nodes,
                relationships=domain_rels,
                node_count=len(domain_nodes),
                relationship_count=len(domain_rels),
            )

    # Count relationship patterns
    relationship_patterns: dict[str, int] = {}
    for rel in relationships:
        relationship_patterns[rel.type] = relationship_patterns.get(rel.type, 0) + 1

    # Determine max depth
    max_depth = max([n.distance_from_origin for n in nodes]) if nodes else 0

    return GraphContext(
        origin_uid=origin_uid,
        origin_domain=origin_domain,
        query_intent=query_intent,
        all_nodes=nodes,
        all_relationships=relationships,
        domain_contexts=domain_contexts,
        cross_domain_insights=[],
        relationship_patterns=relationship_patterns,
        total_nodes=len(nodes),
        total_relationships=len(relationships),
        domains_involved=list(domain_contexts.keys()),
        max_depth_reached=max_depth,
        query_timestamp=datetime.now(),
    )


def create_intelligence_insight(
    insight_type: str,
    title: str,
    description: str,
    confidence: float,
    nodes: list[str],
    domains: list[Domain],
) -> IntelligenceInsight:
    """Create an IntelligenceInsight."""
    return IntelligenceInsight(
        insight_type=insight_type,
        title=title,
        description=description,
        supporting_nodes=nodes,
        supporting_relationships=[],
        confidence_score=confidence,
        is_actionable=True,
        suggested_actions=[],
        priority="medium",
        domains_involved=domains,
        discovered_at=datetime.now(),
    )
