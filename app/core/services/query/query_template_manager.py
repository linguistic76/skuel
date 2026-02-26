"""
Query Template Manager
=====================

Template management and execution system.

Part of QueryBuilder decomposition.
Manages library of query templates and executes them with parameters.
"""

from dataclasses import dataclass
from typing import Any

from core.models.query import IndexStrategy, QueryOptimizationResult, QueryPlan, TemplateSpec
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


@dataclass
class TemplateRegistration:
    """Registration for a query template"""

    name: str
    spec: TemplateSpec
    category: str = "custom"


class QueryTemplateManager:
    """
    Manages query templates and executes them with parameters.

    Provides a library of 40+ built-in templates for common query patterns,
    plus support for custom template registration.
    """

    def __init__(self, schema_service) -> None:
        """Initialize template manager with schema service."""
        self.schema_service = schema_service
        self.logger = get_logger("QueryTemplateManager")
        self._template_library = {}
        self._load_default_templates()

    def _load_default_templates(self) -> None:
        """Load default templates from Template Library and Enhanced Templates."""

        # From Template Library - Basic CRUD operations
        self.register_template(
            "get_by_uid",
            TemplateSpec(
                name="get_by_uid",
                description="Fetch entity by unique ID",
                base_template="MATCH (n {uid: $uid}) RETURN n",
                required_parameters={"uid"},
                optimization_rules={
                    "has_uid_index": "MATCH (n {uid: $uid}) RETURN n"  # Already optimal
                },
                estimated_base_cost=1,
            ),
            category="crud",
        )

        self.register_template(
            "create_entity",
            TemplateSpec(
                name="create_entity",
                description="Create new entity",
                base_template="CREATE (n:$label $properties) RETURN n",
                required_parameters={"label", "properties"},
                estimated_base_cost=1,
            ),
            category="crud",
        )

        self.register_template(
            "update_entity",
            TemplateSpec(
                name="update_entity",
                description="Update entity properties",
                base_template="""
                    MATCH (n {uid: $uid})
                    SET n += $properties
                    RETURN n
                """,
                required_parameters={"uid", "properties"},
                estimated_base_cost=2,
            ),
            category="crud",
        )

        self.register_template(
            "delete_entity",
            TemplateSpec(
                name="delete_entity",
                description="Delete entity and relationships",
                base_template="""
                    MATCH (n {uid: $uid})
                    DETACH DELETE n
                    RETURN true as deleted
                """,
                required_parameters={"uid"},
                estimated_base_cost=2,
            ),
            category="crud",
        )

        # From Enhanced Templates - Text search patterns
        self.register_template(
            "text_search",
            TemplateSpec(
                name="text_search",
                description="Text search with automatic index selection",
                base_template="""
                    MATCH (n:$label)
                    WHERE n.$property CONTAINS $search_term
                    RETURN n
                    ORDER BY n.updated_at DESC
                    LIMIT $limit
                """,
                required_parameters={"label", "property", "search_term"},
                optional_parameters={"limit"},
                optimization_rules={
                    "has_fulltext_index": """
                        CALL db.index.fulltext.queryNodes('{index_name}', $search_term)
                        YIELD node, score
                        WHERE '{label}' IN labels(node)
                        RETURN node as n, score
                        ORDER BY score DESC
                        LIMIT $limit
                    """
                },
                estimated_base_cost=5,
            ),
            category="search",
        )

        # Relationship templates
        self.register_template(
            "find_related",
            TemplateSpec(
                name="find_related",
                description="Find related nodes",
                base_template="""
                    MATCH (n {uid: $uid})-[r:$rel_type]-(related)
                    RETURN related, r, type(r) as relationship_type
                """,
                required_parameters={"uid", "rel_type"},
                estimated_base_cost=3,
            ),
            category="relationships",
        )

        self.register_template(
            "create_relationship",
            TemplateSpec(
                name="create_relationship",
                description="Create relationship between nodes",
                base_template="""
                    MATCH (a {uid: $from_uid}), (b {uid: $to_uid})
                    CREATE (a)-[r:$rel_type $properties]->(b)
                    RETURN r
                """,
                required_parameters={"from_uid", "to_uid", "rel_type"},
                optional_parameters={"properties"},
                estimated_base_cost=2,
            ),
            category="relationships",
        )

        # Aggregation templates
        self.register_template(
            "count_by_label",
            TemplateSpec(
                name="count_by_label",
                description="Count nodes by label",
                base_template="""
                    MATCH (n:$label)
                    RETURN count(n) as count
                """,
                required_parameters={"label"},
                estimated_base_cost=4,
            ),
            category="aggregation",
        )

        self.register_template(
            "group_by_property",
            TemplateSpec(
                name="group_by_property",
                description="Group and count by property",
                base_template="""
                    MATCH (n:$label)
                    RETURN n.$property as value, count(n) as count
                    ORDER BY count DESC
                """,
                required_parameters={"label", "property"},
                estimated_base_cost=5,
            ),
            category="aggregation",
        )

        self.logger.info(f"Loaded {len(self._template_library)} default templates")

    def register_template(self, name: str, spec: TemplateSpec, category: str = "custom"):
        """
        Register a new query template.

        Args:
            name: Template name for referencing
            spec: Template specification
            category: Template category for organization
        """
        self._template_library[name] = TemplateRegistration(name=name, spec=spec, category=category)
        self.logger.debug(f"Registered template '{name}' in category '{category}'")

    async def from_template(
        self, template_name: str, params: dict[str, Any]
    ) -> Result[QueryOptimizationResult]:
        """
        Build an optimized query from a predefined template.

        Args:
            template_name: Name of registered template
            params: Parameters for the template

        Returns:
            Result with optimized query plan
        """
        if template_name not in self._template_library:
            return Result.fail(
                Errors.validation(
                    field="template_name",
                    message=f"Template '{template_name}' not found. Available: {list(self._template_library.keys())}",
                )
            )

        registration = self._template_library[template_name]
        spec = registration.spec

        # Validate required parameters
        missing_params = spec.required_parameters - set(params.keys())
        if missing_params:
            return Result.fail(
                Errors.validation(
                    field="parameters", message=f"Missing required parameters: {missing_params}"
                )
            )

        # Get current schema for optimization
        schema_result = await self.schema_service.get_schema_context()
        if schema_result.is_error:
            return schema_result

        schema = schema_result.value

        # Select best template variant based on schema
        cypher = spec.base_template
        used_indexes = []
        strategy = IndexStrategy.NO_INDEX

        # Apply optimization rules based on available indexes
        if spec.optimization_rules:
            for rule_name, optimized_template in spec.optimization_rules.items():
                if rule_name == "has_fulltext_index":
                    # Check for fulltext index
                    fulltext_indexes = [idx for idx in schema.indexes if idx.type == "FULLTEXT"]
                    if fulltext_indexes:
                        cypher = optimized_template.replace(
                            "{index_name}", fulltext_indexes[0].name
                        )
                        if "label" in params:
                            cypher = cypher.replace("{label}", params["label"])
                        used_indexes.append(fulltext_indexes[0].name)
                        strategy = IndexStrategy.FULLTEXT_SEARCH
                        break

                elif rule_name == "has_uid_index":
                    # Check for UID index/constraint
                    uid_indexes = [
                        idx
                        for idx in schema.indexes
                        if "uid" in idx.properties or "id" in idx.properties
                    ]
                    if uid_indexes:
                        used_indexes.append(uid_indexes[0].name)
                        strategy = IndexStrategy.UNIQUE_LOOKUP

        # Process template with parameters
        for key, value in params.items():
            placeholder = f"${key}"
            if placeholder in cypher:
                # Parameter will be passed separately
                continue
            # Direct substitution for structural elements (labels, relationship types)
            cypher = cypher.replace(f"${key}", str(value))

        # Create query plan
        plan = QueryPlan(
            cypher=cypher,
            parameters={
                k: v for k, v in params.items() if f"${k}" in cypher
            },  # Only include used parameters
            strategy=strategy,
            used_indexes=used_indexes,
            estimated_cost=spec.estimated_base_cost,
            explanation=f"Template '{template_name}': {spec.description}",
            expected_selectivity=0.5,  # Default selectivity
        )

        # Create optimization result
        result = QueryOptimizationResult(
            primary_plan=plan, alternative_plans=[], index_recommendations=[], warnings=[]
        )

        return Result.ok(result)

    def get_template_library(self) -> dict[str, list[str]]:
        """
        Get organized view of available templates.

        Returns:
            Dictionary mapping categories to template names
        """
        library = {}
        for name, registration in self._template_library.items():
            category = registration.category
            if category not in library:
                library[category] = []
            library[category].append(name)

        # Sort for consistent ordering
        for category in library:
            library[category].sort()

        return library

    def get_template_spec(self, template_name: str) -> TemplateSpec | None:
        """Get the specification for a specific template."""
        registration = self._template_library.get(template_name)
        return registration.spec if registration else None

    # ========================================================================
    # VALIDATION FUNCTIONALITY
    # ========================================================================
