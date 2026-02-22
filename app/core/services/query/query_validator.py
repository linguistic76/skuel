"""
Query Validator
===============

Query validation and syntax checking.

Part of QueryBuilder decomposition (Phase 2).
Validates query syntax and suggests optimizations.

NOTE: This service depends on QueryOptimizer and QueryTemplateManager
for full functionality. The QueryBuilder facade wires these dependencies.
"""

from typing import TYPE_CHECKING

from core.models.query import (
    QueryBuildRequest,
    QueryConstraint,
    QueryOptimizationResult,
    ValidationIssue,
    ValidationResult,
    analyze_query_intent,
)
from core.ports import HasSeverity, HasUsage
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.query.query_optimizer import QueryOptimizer
    from core.services.query.query_template_manager import QueryTemplateManager


class QueryValidator:
    """
    Validates Cypher queries and suggests improvements.

    Provides syntax checking, semantic validation, and
    optimization suggestions for query improvement.

    This service is part of the QueryBuilder facade decomposition.
    It depends on QueryOptimizer and QueryTemplateManager for
    full functionality (injected after initialization).
    """

    def __init__(
        self,
        schema_service,
        optimizer: "QueryOptimizer | None" = None,
        template_manager: "QueryTemplateManager | None" = None,
    ) -> None:
        """
        Initialize validator with schema service.

        Args:
            schema_service: Schema context provider
            optimizer: Optional QueryOptimizer for optimization delegation
            template_manager: Optional QueryTemplateManager for template access

        Note: QueryBuilder facade injects optimizer and template_manager
        after initialization to avoid circular dependencies.
        """
        self.schema_service = schema_service
        self.optimizer = optimizer
        self.template_manager = template_manager
        self.logger = get_logger("QueryValidator")

    async def validate_only(
        self, cypher: str, strict_mode: bool = True
    ) -> Result[ValidationResult]:
        """
        Validate a Cypher query without building or executing it.

        Args:
            cypher: The Cypher query to validate
            strict_mode: If True, treat warnings as errors

        Returns:
            Result[ValidationResult] with detailed validation feedback
        """
        try:
            self.logger.debug(f"Validating query: {cypher[:100]}...")

            # Get current schema
            schema_result = await self.schema_service.get_schema_context()
            if schema_result.is_error:
                return schema_result

            schema = schema_result.value

            # Parse query to extract elements and analyze intent
            query_elements = analyze_query_intent(cypher)

            # Skip validation for queries with no schema elements
            if not query_elements.has_schema_elements():
                self.logger.debug("Query has no schema elements, skipping validation")
                return Result.ok(
                    ValidationResult(
                        is_valid=True,
                        issues=[],
                        query_elements=query_elements,
                        schema_hash=schema.schema_hash,
                    )
                )

            # Perform validation checks
            issues = []

            # Validate node labels
            issues.extend(
                [
                    ValidationIssue(
                        severity="error",
                        category="missing_label",
                        message=f"Node label '{label}' does not exist in schema",
                        element=label,
                        context=f"Available labels: {', '.join(sorted(schema.node_labels)[:5])}",
                    )
                    for label in query_elements.node_labels
                    if label not in schema.node_labels
                ]
            )

            # Validate relationship types
            issues.extend(
                [
                    ValidationIssue(
                        severity="error",
                        category="missing_relationship",
                        message=f"Relationship type '{rel_type}' does not exist in schema",
                        element=rel_type,
                        context=f"Available types: {', '.join(sorted(schema.relationship_types)[:5])}",
                    )
                    for rel_type in query_elements.relationship_types
                    if rel_type not in schema.relationship_types
                ]
            )

            # Validate properties
            for prop_ref in query_elements.property_references:
                label_exists = not prop_ref.label or prop_ref.label in schema.node_labels
                if label_exists and prop_ref.label:
                    # Check if property exists for this label
                    label_info = schema.node_label_info.get(prop_ref.label, {})
                    properties = label_info.get("properties", {})
                    if prop_ref.property not in properties:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                category="missing_property",
                                message=f"Property '{prop_ref.property}' not found on label '{prop_ref.label}'",
                                element=f"{prop_ref.label}.{prop_ref.property}",
                                context="Property might exist but wasn't detected in schema scan",
                            )
                        )

            # Check for index usage opportunities
            for prop_ref in query_elements.property_references:
                if isinstance(prop_ref, HasUsage) and (
                    prop_ref.usage == "filter" or prop_ref.usage == "lookup"
                ):
                    # Check if there's an index
                    has_index = any(prop_ref.property in idx.properties for idx in schema.indexes)
                    if not has_index:
                        issues.append(
                            ValidationIssue(
                                severity="info",
                                category="optimization",
                                message=f"No index found for filtered property '{prop_ref.property}'",
                                element=prop_ref.property,
                                context="Consider creating an index for better performance",
                            )
                        )

            # Determine overall validity
            errors = [
                issue
                for issue in issues
                if isinstance(issue, HasSeverity) and issue.severity == "error"
            ]
            warnings = [
                issue
                for issue in issues
                if isinstance(issue, HasSeverity) and issue.severity == "warning"
            ]

            is_valid = len(errors) == 0 and (not strict_mode or len(warnings) == 0)

            validation_result = ValidationResult(
                is_valid=is_valid,
                issues=issues,
                query_elements=query_elements,
                schema_hash=schema.schema_hash,
            )

            self.logger.info(
                f"Validation complete: valid={is_valid}, "
                f"errors={len(errors)}, warnings={len(warnings)}"
            )

            return Result.ok(validation_result)

        except Exception as e:
            self.logger.error(f"Query validation failed: {e}", exc_info=True)
            return Result.fail(
                Errors.validation(field="query_validation", message=f"Validation failed: {e!s}")
            )

    async def validate_and_optimize(self, cypher: str) -> Result[QueryOptimizationResult]:
        """
        Validate a query and provide optimization suggestions.

        This combines validation with optimization analysis.

        Args:
            cypher: The Cypher query to validate and optimize

        Returns:
            Result with validation results and optimization suggestions
        """
        # First validate
        validation_result = await self.validate_only(cypher)
        if validation_result.is_error:
            return Result.fail(validation_result.expect_error())

        validation = validation_result.value
        if not validation.is_valid:
            return Result.fail(
                Errors.validation(
                    field="query",
                    message="Query validation failed",
                    value={"issues": [issue.__dict__ for issue in validation.issues]},
                )
            )

        # Check if optimizer is available
        if not self.optimizer:
            return Result.fail(
                Errors.system(
                    message="QueryOptimizer not available - cannot perform optimization",
                    operation="validate_and_optimize",
                )
            )

        # Parse query to create a build request
        query_elements = validation.query_elements

        # Extract labels and constraints from the parsed query
        labels = query_elements.node_labels
        constraints = []

        # Convert property references to constraints
        # Filter for properties used in filtering/lookup operations (not return/sort/aggregate)
        constraints.extend(
            [
                QueryConstraint(
                    property_name=prop_ref.property,
                    operator="=",  # Default, would need more parsing for actual operator
                    value=None,  # Would need to extract from query
                    label=prop_ref.label,
                )
                for prop_ref in query_elements.property_references
                if isinstance(prop_ref, HasUsage) and prop_ref.usage in ["filter", "lookup"]
            ]
        )

        # Create build request with intent
        request = QueryBuildRequest(
            labels=labels, constraints=constraints, query_intent=query_elements.intent
        )

        # Delegate to optimizer
        return await self.optimizer.build_optimized_query(request)

    # ========================================================================
    # ENHANCED FUNCTIONALITY
    # ========================================================================

    async def build_from_natural_language(
        self, description: str
    ) -> Result[QueryOptimizationResult]:
        """
        Build a query from a natural language description.

        This maps common patterns to templates.

        Args:
            description: Natural language query description

        Returns:
            Result with optimized query plan
        """
        # Check if template manager is available
        if not self.template_manager:
            return Result.fail(
                Errors.system(
                    message="QueryTemplateManager not available - cannot build from templates",
                    operation="build_from_natural_language",
                )
            )

        description_lower = description.lower()

        # Simple pattern matching for common queries
        if "find" in description_lower or "get" in description_lower:
            if "by id" in description_lower or "by uid" in description_lower:
                # Extract the ID from the description
                # This is simplified - in production, use NLP
                return await self.template_manager.from_template(
                    "get_by_uid", {"uid": "placeholder"}
                )

            elif "related" in description_lower:
                return await self.template_manager.from_template(
                    "find_related", {"uid": "placeholder", "rel_type": "RELATED_TO"}
                )

        elif "create" in description_lower:
            return await self.template_manager.from_template(
                "create_entity", {"label": "Entity", "properties": {}}
            )

        elif "delete" in description_lower:
            return await self.template_manager.from_template(
                "delete_entity", {"uid": "placeholder"}
            )

        elif "count" in description_lower:
            return await self.template_manager.from_template("count_by_label", {"label": "Entity"})

        # Fallback to text search
        return await self.template_manager.from_template(
            "text_search",
            {
                "label": "Entity",
                "property": "content",
                "search_term": description,
                "limit": 10,
            },
        )
