"""
Consolidated Query Models
=========================

Single source of truth for all query-related data models.
Adapter-layer infrastructure for Cypher query construction.

These models live in ``adapters/persistence/neo4j/query/`` — firmly in the
persistence adapter layer. Methods like ``QueryConstraint.to_cypher()`` and
``QuerySort.to_cypher()`` generate Cypher clause fragments, which is the
*purpose* of this adapter layer. This is not domain models leaking persistence
concerns; it is persistence models doing persistence work.

Infrastructure-level query models accessible to ALL domains.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from core.models.query_types import IndexStrategy, QueryIntent

# ============================================================================
# QUERY BUILDING MODELS
# ============================================================================


@dataclass
class QueryConstraint:
    """
    Adapter-layer model: a single WHERE clause condition for Cypher queries.

    Lives in ``adapters/persistence/neo4j/query/`` — this IS the persistence layer.
    ``to_cypher()`` is its primary job, not a domain model leaking serialization.
    """

    property_name: str
    operator: str  # "=", "<", ">", "<=", ">=", "CONTAINS", "STARTS WITH", "IN", etc.
    value: Any
    label: str | None = None  # Optional label context

    def to_cypher(self) -> str:
        """Generate a Cypher WHERE clause fragment (e.g., ``n.priority = $priority``)."""
        label_prefix = f"{self.label}." if self.label else "n."

        # Handle different operators
        if self.operator == "IN":
            return f"{label_prefix}{self.property_name} IN ${self.property_name}"
        elif self.operator in ["CONTAINS", "STARTS WITH", "ENDS WITH"]:
            return f"{label_prefix}{self.property_name} {self.operator} ${self.property_name}"
        else:
            return f"{label_prefix}{self.property_name} {self.operator} ${self.property_name}"


@dataclass
class QuerySort:
    """Represents sorting in a query (ORDER BY clause)"""

    property_name: str
    direction: str = "ASC"  # "ASC" or "DESC",
    label: str | None = None

    def to_cypher(self) -> str:
        """Convert to Cypher ORDER BY clause fragment"""
        label_prefix = f"{self.label}." if self.label else "n."
        return f"{label_prefix}{self.property_name} {self.direction}"


@dataclass
class QueryBuildRequest:
    """Request object for building optimized queries"""

    # Core query components
    labels: set[str] = field(default_factory=set)
    constraints: list[QueryConstraint] = field(default_factory=list)
    sort_by: list[QuerySort] = field(default_factory=list)
    return_properties: list[str] = field(default_factory=list)

    # Search-specific
    search_text: str | None = None
    search_vector: list[float] | None = None

    # Pagination
    skip: int | None = None
    limit: int | None = None

    # Relationship traversal
    relationships: list[dict[str, Any]] = field(default_factory=list)

    # Performance hints
    prefer_strategy: IndexStrategy | None = None
    max_cost: int | None = None

    # Intent analysis
    query_intent: QueryIntent | None = None

    def __post_init__(self) -> None:
        """Ensure all sets are properly initialized"""
        if not isinstance(self.labels, set):
            self.labels = set(self.labels or [])


@dataclass
class QueryPlan:
    """Represents an optimized query execution plan"""

    cypher: str
    parameters: dict[str, Any]
    strategy: IndexStrategy
    used_indexes: list[str]
    estimated_cost: int
    explanation: str
    expected_selectivity: float = 1.0  # 0.0-1.0, lower is more selective

    @property
    def is_optimal(self) -> bool:
        """Check if this plan uses optimal indexes"""
        return self.strategy in [
            IndexStrategy.UNIQUE_LOOKUP,
            IndexStrategy.FULLTEXT_SEARCH,
            IndexStrategy.VECTOR_SEARCH,
            IndexStrategy.COMPOSITE_INDEX,
        ]

    @property
    def performance_tier(self) -> str:
        """Get performance tier for this plan"""
        if self.strategy == IndexStrategy.UNIQUE_LOOKUP:
            return "optimal"
        elif self.strategy in [IndexStrategy.FULLTEXT_SEARCH, IndexStrategy.VECTOR_SEARCH]:
            return "excellent"
        elif self.strategy in [IndexStrategy.COMPOSITE_INDEX, IndexStrategy.RANGE_FILTER]:
            return "good"
        elif self.strategy == IndexStrategy.TEXT_SEARCH:
            return "acceptable"
        else:
            return "poor"


@dataclass
class IndexRecommendation:
    """Recommendation for creating new indexes"""

    index_type: str
    labels: list[str]
    properties: list[str]
    reasoning: str
    estimated_benefit: str  # "high", "medium", "low"

    def to_cypher_create(self) -> str:
        """Generate Cypher to create this index"""
        label = self.labels[0] if self.labels else "Node"
        prop = self.properties[0] if self.properties else "property"

        if self.index_type == "RANGE":
            return f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
        elif self.index_type == "FULLTEXT":
            props_str = ", ".join([f"n.{p}" for p in self.properties])
            return f"CREATE FULLTEXT INDEX IF NOT EXISTS FOR (n:{label}) ON EACH [{props_str}]"
        elif self.index_type == "UNIQUE":
            return f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
        else:
            return f"// {self.index_type} index on {label}.{prop}"


@dataclass
class QueryOptimizationResult:
    """Result of query optimization with multiple plan options"""

    primary_plan: QueryPlan
    alternative_plans: list[QueryPlan] = (field(default_factory=list),)
    index_recommendations: list[IndexRecommendation] = (field(default_factory=list),)
    warnings: list[str] = field(default_factory=list)

    @property
    def best_plan(self) -> QueryPlan:
        """Get the best available plan"""
        return self.primary_plan

    @property
    def all_plans(self) -> list[QueryPlan]:
        """Get all available plans sorted by estimated cost"""
        all_plans = [self.primary_plan, *self.alternative_plans]

        def get_plan_cost(plan: QueryPlan) -> float:
            return plan.estimated_cost

        return sorted(all_plans, key=get_plan_cost)


# ============================================================================
# QUERY ANALYSIS MODELS
# ============================================================================


@dataclass
class PropertyReference:
    """Reference to a property in a query"""

    label: str | None
    property: str
    usage: str  # "filter", "lookup", "return", "sort", "aggregate"


@dataclass
class QueryElements:
    """
    Extracted elements from a Cypher query for validation and analysis.
    Unified to serve both validation and intent understanding.
    """

    node_labels: set[str]
    relationship_types: set[str]
    node_properties: dict[str, set[str]]  # label -> properties
    relationship_properties: dict[str, set[str]]  # type -> properties
    property_references: list[PropertyReference]
    variables: set[str]
    functions: set[str]

    # Intent analysis fields
    intent: QueryIntent | None = (None,)

    keywords: list[str] = (field(default_factory=list),)
    needs_hierarchy: bool = False

    needs_prerequisites: bool = False
    depth_required: int = 2

    def __post_init__(self) -> None:
        """Ensure all fields are sets/dicts to avoid mutation issues"""
        self.node_labels = set(self.node_labels) if self.node_labels else set()
        self.relationship_types = set(self.relationship_types) if self.relationship_types else set()
        self.node_properties = dict(self.node_properties) if self.node_properties else {}
        self.relationship_properties = (
            dict(self.relationship_properties) if self.relationship_properties else {}
        )
        self.variables = set(self.variables) if self.variables else set()
        self.functions = set(self.functions) if self.functions else set()
        self.property_references = (
            list(self.property_references) if self.property_references else []
        )

    @property
    def all_properties(self) -> set[str]:
        """Get all unique property names from both nodes and relationships"""
        all_props = set()
        for props in self.node_properties.values():
            all_props.update(props)
        for props in self.relationship_properties.values():
            all_props.update(props)
        return all_props

    def has_schema_elements(self) -> bool:
        """Check if query contains any schema elements that need validation"""
        return (
            bool(self.node_labels)
            or bool(self.relationship_types)
            or bool(self.node_properties)
            or bool(self.relationship_properties)
        )

    def analyze_intent(self, query_text: str) -> None:
        """Analyze query text to determine intent and requirements"""
        query_lower = query_text.lower()

        # Detect intent based on keywords and patterns
        if any(word in query_lower for word in ["example", "exercise", "practice", "problem"]):
            self.intent = QueryIntent.PRACTICE
        elif any(word in query_lower for word in ["prerequisite", "before", "need to know"]):
            self.intent = QueryIntent.PREREQUISITE
        elif any(word in query_lower for word in ["children", "subtopic", "break down"]):
            self.intent = QueryIntent.HIERARCHICAL
        elif any(word in query_lower for word in ["count", "sum", "avg", "max", "min"]):
            self.intent = QueryIntent.AGGREGATION
        elif any(word in query_lower for word in ["related", "connected", "linked"]):
            self.intent = QueryIntent.RELATIONSHIP
        elif len(query_text.split()) <= 3:
            self.intent = QueryIntent.SPECIFIC
        else:
            self.intent = QueryIntent.EXPLORATORY

        # Extract keywords
        self.keywords = [w for w in query_text.split() if len(w) > 3]

        # Determine requirements based on intent
        self.needs_hierarchy = self.intent in [QueryIntent.HIERARCHICAL, QueryIntent.EXPLORATORY]
        self.needs_prerequisites = self.intent in [QueryIntent.PREREQUISITE, QueryIntent.PRACTICE]
        self.depth_required = 3 if self.needs_hierarchy else 2


@dataclass
class ValidationIssue:
    """
    Represents a specific validation issue found in a query.
    Provides detailed information about what's wrong and how to fix it.
    """

    severity: str  # 'error', 'warning', 'info'
    category: str  # 'missing_label', 'missing_property', 'missing_relationship', 'optimization'
    message: str
    element: str  # The problematic element (label, property, etc.)
    context: str | None = None  # Additional context,
    suggestion: str | None = None  # How to fix it

    @property
    def is_error(self) -> bool:
        """Check if this is an error-level issue"""
        return self.severity == "error"

    @property
    def is_warning(self) -> bool:
        """Check if this is a warning-level issue"""
        return self.severity == "warning"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "element": self.element,
            "context": self.context,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationResult:
    """
    Result of query validation with detailed feedback.
    Provides clear information about what passed, what failed, and how to fix issues.
    """

    is_valid: bool
    issues: list[ValidationIssue]
    query_elements: QueryElements
    schema_hash: str  # Hash of schema used for validation

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues"""
        return [issue for issue in self.issues if issue.is_error]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues"""
        return [issue for issue in self.issues if issue.is_warning]

    @property
    def error_count(self) -> int:
        """Count of error-level issues"""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Count of warning-level issues"""
        return len(self.warnings)

    def get_error_summary(self) -> str:
        """Get a concise summary of all errors"""
        if not self.errors:
            return "No validation errors"

        error_messages = [issue.message for issue in self.errors]
        return "; ".join(error_messages)

    def get_suggestions(self) -> list[str]:
        """Get all suggestions for fixing issues"""
        return [issue.suggestion for issue in self.issues if issue.suggestion]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _extract_property_references(query_text: str) -> list[PropertyReference]:
    """
    Extract property references from a Cypher query and classify their usage.

    Classifies properties based on context:
    - "lookup": MATCH clause with equality (indexed lookup)
    - "filter": WHERE clause (filtering)
    - "return": RETURN clause (output)
    - "sort": ORDER BY clause (sorting)
    - "aggregate": Used in aggregation functions (COUNT, SUM, AVG, etc.)

    Args:
        query_text: Cypher query to analyze

    Returns:
        List of PropertyReference objects with label, property, and usage
    """
    property_refs = []

    # Pattern: variable.property (e.g., "n.due_date", "task.priority")
    # Captures: variable name and property name
    prop_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b")

    # Pattern: node labels in MATCH clause (e.g., "(n:Task)", "(user:User)")
    # Captures: variable name and label
    label_pattern = re.compile(r"\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)")

    # Pattern: shorthand property matching in MATCH (e.g., "(n:Task {uid: $uid})")
    # Captures: variable, label, and properties within {}
    shorthand_pattern = re.compile(
        r"\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\{([^}]+)\}\s*\)"
    )

    # Build variable -> label mapping from MATCH clauses
    var_to_label: dict[str, str] = {}
    for match in label_pattern.finditer(query_text):
        var_name = match.group(1)
        label_name = match.group(2)
        var_to_label[var_name] = label_name

    # Extract properties from shorthand MATCH syntax
    for match in shorthand_pattern.finditer(query_text):
        var_name = match.group(1)
        label_name = match.group(2)
        properties_str = match.group(3)

        # Update label mapping
        var_to_label[var_name] = label_name

        # Parse property:value pairs (e.g., "uid: $uid, status: 'active'")
        prop_assignments = re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:", properties_str)

        # Use extend instead of loop append for better performance (PERF401)
        property_refs.extend(
            PropertyReference(
                label=label_name,
                property=prop_name,
                usage="lookup",  # Shorthand in MATCH is always a lookup
            )
            for prop_name in prop_assignments
        )

    # Split query into clauses for context-aware classification
    query_upper = query_text.upper()

    # Helper to find clause boundaries
    def get_clause_ranges() -> dict[str, tuple[int, int]]:
        """Get start/end positions for each query clause"""
        clauses = {}

        # Find MATCH clause
        match_start = query_upper.find("MATCH")
        where_start = query_upper.find("WHERE")
        return_start = query_upper.find("RETURN")
        order_start = query_upper.find("ORDER BY")

        if match_start >= 0:
            match_end = (
                where_start
                if where_start >= 0
                else (return_start if return_start >= 0 else len(query_text))
            )
            clauses["match"] = (match_start, match_end)

        if where_start >= 0:
            where_end = (
                return_start
                if return_start >= 0
                else (order_start if order_start >= 0 else len(query_text))
            )
            clauses["where"] = (where_start, where_end)

        if return_start >= 0:
            return_end = order_start if order_start >= 0 else len(query_text)
            clauses["return"] = (return_start, return_end)

        if order_start >= 0:
            clauses["order"] = (order_start, len(query_text))

        return clauses

    clause_ranges = get_clause_ranges()

    # Aggregation function pattern
    agg_pattern = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|COLLECT)\s*\(")

    # Process each property reference
    for match in prop_pattern.finditer(query_text):
        var_name = match.group(1)
        prop_name = match.group(2)
        prop_position = match.start()

        # Get label for this variable (if known)
        label = var_to_label.get(var_name)

        # Determine usage based on context
        usage = "filter"  # Default

        # Check if in aggregation function
        # Look backwards from property for aggregation keyword
        context_start = max(0, prop_position - 50)
        context_before = query_text[context_start:prop_position]
        if agg_pattern.search(context_before):
            usage = "aggregate"
        # Check which clause contains this property
        elif "match" in clause_ranges:
            match_start, match_end = clause_ranges["match"]
            if match_start <= prop_position < match_end:
                # In MATCH clause - check if it's an equality lookup
                # Look ahead for = operator (not ==, !=, <=, >=)
                context_after = query_text[prop_position : min(len(query_text), prop_position + 30)]
                usage = "lookup" if re.search(r"\s*=\s*[^=]", context_after) else "filter"

        if "where" in clause_ranges:
            where_start, where_end = clause_ranges["where"]
            if where_start <= prop_position < where_end:
                usage = "filter"

        if "return" in clause_ranges:
            return_start, return_end = clause_ranges["return"]
            if return_start <= prop_position < return_end and usage != "aggregate":
                usage = "return"

        if "order" in clause_ranges:
            order_start, order_end = clause_ranges["order"]
            if order_start <= prop_position < order_end:
                usage = "sort"

        property_refs.append(PropertyReference(label=label, property=prop_name, usage=usage))

    return property_refs


def analyze_query_intent(query_text: str) -> QueryElements:
    """
    Analyze a query to extract elements and determine intent.
    This is the unified analysis function.

    Extracts:
    - Property references with usage classification
    - Query intent (PRACTICE, PREREQUISITE, etc.)
    - Keywords and requirements
    """
    # Extract property references from query
    property_refs = _extract_property_references(query_text)

    elements = QueryElements(
        node_labels=set(),
        relationship_types=set(),
        node_properties={},
        relationship_properties={},
        property_references=property_refs,
        variables=set(),
        functions=set(),
    )

    # Analyze intent
    elements.analyze_intent(query_text)

    return elements


def create_search_request(
    labels: list[str] | None = None,
    search_text: str | None = None,
    intent: QueryIntent | None = None,
    limit: int = 25,
) -> QueryBuildRequest:
    """Helper to create a search request with intent"""
    return QueryBuildRequest(
        labels=set(labels or []), search_text=search_text, limit=limit, query_intent=intent
    )


def create_filter_request(label: str, **filters: Any) -> QueryBuildRequest:
    """Helper to create a filter request"""
    constraints = []
    for prop, value in filters.items():
        constraints.append(
            QueryConstraint(property_name=prop, operator="=", value=value, label=label)
        )

    return QueryBuildRequest(labels={label}, constraints=constraints)


def create_range_request(
    label: str, property_name: str, min_value=None, max_value=None, limit: int | None = None
) -> QueryBuildRequest:
    """Helper to create a range query request"""
    constraints = []

    if min_value is not None:
        constraints.append(
            QueryConstraint(
                property_name=property_name, operator=">=", value=min_value, label=label
            )
        )

    if max_value is not None:
        constraints.append(
            QueryConstraint(
                property_name=property_name, operator="<=", value=max_value, label=label
            )
        )

    return QueryBuildRequest(labels={label}, constraints=constraints, limit=limit)
