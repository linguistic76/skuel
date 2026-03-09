"""
Cypher Template Models
=====================

Data models for schema-aware Cypher query templates and their optimization strategies.
"""

__version__ = "1.0"


from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueryOptimizationStrategy(Enum):
    """Optimization strategies based on available schema elements"""

    BASIC = "basic"  # No optimization
    INDEXED = "indexed"  # Use available indexes
    FULLTEXT = "fulltext"  # Use fulltext search
    UNIQUE_CONSTRAINT = "unique_constraint"  # Use unique lookups
    RELATIONSHIP_TRAVERSAL = "relationship_traversal"  # Optimize traversals


@dataclass
class CypherQuery:
    """
    Represents a Cypher query with parameters and metadata.

    Enhanced version that includes optimization information and schema context.
    """

    cypher: str
    parameters: dict[str, Any] = (field(default_factory=dict),)
    optimization_strategy: QueryOptimizationStrategy = QueryOptimizationStrategy.BASIC
    expected_labels: set[str] = (field(default_factory=set),)
    expected_relationships: set[str] = (field(default_factory=set),)
    uses_indexes: list[str] = field(default_factory=list)  # Index names used,
    estimated_cost: int | None = None  # Relative cost estimate,
    description: str | None = None


@dataclass
class TemplateSpec:
    """
    Specification for a query template including optimization rules.
    """

    name: str
    description: str
    base_template: str
    required_parameters: set[str]
    optional_parameters: set[str] = (field(default_factory=set),)
    optimization_rules: dict[str, str] = field(
        default_factory=dict
    )  # condition -> optimized template,
    applicable_labels: set[str] = field(default_factory=set)  # Labels this template works with,
    applicable_relationships: set[str] = field(
        default_factory=set
    )  # Relationships this template works with,
    requires_indexes: set[str] = field(default_factory=set)  # Required index types,
    estimated_base_cost: int = 1  # Base cost without optimizations
    category: str = "general"  # Template category for filtering (e.g., "traversal", "search")


@dataclass
class TemplateRecommendation:
    """
    Recommendation for which template to use based on schema analysis.
    """

    template_spec: TemplateSpec
    confidence_score: float  # 0.0 - 1.0
    optimization_strategy: QueryOptimizationStrategy
    reasoning: str
    available_optimizations: list[str]
    missing_optimizations: list[str]
    estimated_performance: str  # "excellent", "good", "fair", "poor"

    @property
    def is_highly_recommended(self) -> bool:
        """Check if this template is highly recommended"""
        return self.confidence_score >= 0.8

    @property
    def is_optimally_supported(self) -> bool:
        """Check if all required optimizations are available"""
        return len(self.missing_optimizations) == 0


@dataclass
class SearchCriteria:
    """
    Criteria for searching nodes, used to select optimal templates.
    """

    labels: set[str] = (field(default_factory=set),)
    properties: dict[str, Any] = (field(default_factory=dict),)
    relationship_types: set[str] = (field(default_factory=set),)
    search_type: str = "exact"  # "exact", "fuzzy", "fulltext", "pattern",
    limit: int | None = (None,)

    order_by: str | None = (None,)
    filters: dict[str, Any] = field(default_factory=dict)
