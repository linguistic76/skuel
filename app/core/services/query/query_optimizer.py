"""
Query Optimizer
===============

Index-aware query optimization for maximum performance.

Part of QueryBuilder decomposition.
Generates multiple query plans and selects the optimal strategy
based on available indexes.
"""

from functools import partial

from core.infrastructure.database.schema import SchemaContext
from adapters.persistence.neo4j.query import (
    IndexRecommendation,
    QueryBuildRequest,
    QueryOptimizationResult,
    QueryPlan,
)
from core.models.query_types import IndexStrategy
from core.ports import HasStrategy
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_query_plan_priority


class QueryOptimizer:
    """
    Index-aware query optimizer.

    Analyzes QueryBuildRequests and generates multiple optimized
    query plans ranked by expected performance.
    """

    def __init__(self, schema_service) -> None:
        """Initialize optimizer with schema service."""
        self.schema_service = schema_service
        self.logger = get_logger("QueryOptimizer")

    async def build_optimized_query(
        self, request: QueryBuildRequest
    ) -> Result[QueryOptimizationResult]:
        """
        Build an optimized query using the best available indexes.

        This is the main entry point - analyzes the request and generates
        multiple optimized query plans ranked by performance.
        """
        try:
            # Get current schema
            schema_result = await self.schema_service.get_schema_context()
            if schema_result.is_error:
                return Result.fail(schema_result.expect_error())

            schema = schema_result.value

            # Validate the request
            validation_result = self._validate_request(request, schema)
            if validation_result.is_error:
                return Result.fail(validation_result.expect_error())

            # Generate multiple query plans
            plans = await self._generate_query_plans(request, schema)

            if not plans:
                return Result.fail(
                    Errors.validation(
                        field="query_optimization",
                        message="No viable query plans could be generated",
                    )
                )

            # Select the best plan
            primary_plan = self._select_best_plan(plans)
            alternative_plans = [p for p in plans if p != primary_plan]

            # Generate index recommendations
            recommendations = self._generate_index_recommendations(request, schema)

            # Generate warnings for suboptimal queries
            warnings = self._generate_warnings(primary_plan, request)

            self.logger.debug(
                f"Generated {len(plans)} query plans, selected {primary_plan.strategy.value} strategy"
            )

            result = QueryOptimizationResult(
                primary_plan=primary_plan,
                alternative_plans=alternative_plans[:3],  # Limit alternatives
                index_recommendations=recommendations,
                warnings=warnings,
            )

            return Result.ok(result)

        except Exception as e:
            self.logger.error(f"Query optimization failed: {e}", exc_info=True)
            return Result.fail(
                Errors.validation(
                    field="query_builder", message=f"Query optimization failed: {e!s}"
                )
            )

    def _validate_request(self, request: QueryBuildRequest, schema: SchemaContext) -> Result[bool]:
        """Validate the query build request"""

        # Check that requested labels exist
        for label in request.labels:
            if label not in schema.node_labels:
                return Result.fail(
                    Errors.validation(
                        field="labels", message=f"Label '{label}' not found in schema"
                    )
                )

        # Check that constraint properties exist for their labels
        for constraint in request.constraints:
            if constraint.label and constraint.label not in schema.node_labels:
                return Result.fail(
                    Errors.validation(
                        field="constraint_label",
                        message=f"Label '{constraint.label}' not found in schema",
                    )
                )

        return Result.ok(True)

    async def _generate_query_plans(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> list[QueryPlan]:
        """Generate multiple optimized query plans for the request"""
        plans = []

        # Plan 1: Unique constraint lookup (if applicable)
        unique_plan = self._try_unique_lookup_plan(request, schema)
        if unique_plan:
            plans.append(unique_plan)

        # Plan 2: Fulltext search (if text search requested)
        if request.search_text:
            fulltext_plan = self._try_fulltext_search_plan(request, schema)
            if fulltext_plan:
                plans.append(fulltext_plan)

        # Plan 3: Vector search (if vector search requested)
        if request.search_vector:
            vector_plan = self._try_vector_search_plan(request, schema)
            if vector_plan:
                plans.append(vector_plan)

        # Plan 4: Range index optimization
        range_plan = self._try_range_index_plan(request, schema)
        if range_plan:
            plans.append(range_plan)

        # Plan 5: Text index optimization
        if request.search_text:
            text_plan = self._try_text_index_plan(request, schema)
            if text_plan:
                plans.append(text_plan)

        # Plan 6: Composite index optimization
        composite_plan = self._try_composite_index_plan(request, schema)
        if composite_plan:
            plans.append(composite_plan)

        # Plan 7: Fallback - basic query without special indexes
        fallback_plan = self._generate_fallback_plan(request, schema)
        plans.append(fallback_plan)

        return plans

    def _try_unique_lookup_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to create a plan using unique constraints for O(1) lookup"""

        # Look for equality constraints on unique properties
        for constraint in request.constraints:
            if constraint.operator == "=":
                # Check if this property has a unique constraint
                for unique_constraint in schema.constraints:
                    if (
                        unique_constraint.type == "UNIQUENESS"
                        and constraint.property_name in unique_constraint.properties
                    ):
                        # Found a unique constraint match
                        label = constraint.label or (
                            next(iter(request.labels)) if request.labels else None
                        )
                        if not label:
                            continue

                        cypher = f"MATCH (n:{label} {{{constraint.property_name}: ${constraint.property_name}}}) RETURN n"

                        # Add additional constraints if any
                        additional_constraints = [c for c in request.constraints if c != constraint]
                        if additional_constraints:
                            where_clauses = [
                                f"n.{c.property_name} {c.operator} ${c.property_name}"
                                for c in additional_constraints
                            ]
                            cypher += " WHERE " + " AND ".join(where_clauses)

                        # Add ordering if requested
                        if request.sort_by:
                            order_clauses = [
                                f"n.{sort.property_name} {sort.direction}"
                                for sort in request.sort_by
                            ]
                            cypher += f" ORDER BY {', '.join(order_clauses)}"

                        # Add pagination
                        if request.skip is not None:
                            cypher += f" SKIP ${request.skip}"
                        if request.limit is not None:
                            cypher += f" LIMIT ${request.limit}"

                        parameters = {constraint.property_name: constraint.value}
                        for c in additional_constraints:
                            parameters[c.property_name] = c.value

                        return QueryPlan(
                            cypher=cypher,
                            parameters=parameters,
                            strategy=IndexStrategy.UNIQUE_LOOKUP,
                            used_indexes=[unique_constraint.name],
                            estimated_cost=1,  # O(1) lookup
                            explanation=f"Using unique constraint on {label}.{constraint.property_name}",
                            expected_selectivity=0.01,  # Unique constraint means very selective
                        )

        return None

    def _try_fulltext_search_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to create a plan using fulltext indexes"""

        if not request.search_text:
            return None

        # Find suitable fulltext indexes
        suitable_indexes = [
            index
            for index in schema.indexes
            if index.type == "FULLTEXT"
            and (not request.labels or request.labels.intersection(set(index.labels)))
        ]

        if not suitable_indexes:
            return None

        # Use the first suitable index (could be enhanced with ranking)
        index = suitable_indexes[0]

        cypher = f"""
            CALL db.index.fulltext.queryNodes('{index.name}', $search_text)
            YIELD node, score
            """

        # Add label filtering if specific labels requested
        if request.labels:
            label_conditions = " OR ".join(
                [f"'{label}' IN labels(node)" for label in request.labels]
            )
            cypher += f" WHERE {label_conditions}"

        # Add additional constraints
        if request.constraints:
            constraint_conditions = [
                f"node.{constraint.property_name} {constraint.operator} ${constraint.property_name}"
                for constraint in request.constraints
            ]

            if constraint_conditions:
                where_part = " AND ".join(constraint_conditions)
                if request.labels:
                    cypher += f" AND {where_part}"
                else:
                    cypher += f" WHERE {where_part}"

        cypher += " RETURN node as n, score ORDER BY score DESC"

        # Add pagination
        if request.limit is not None:
            cypher += f" LIMIT ${request.limit}"

        parameters = {"search_text": request.search_text}
        for constraint in request.constraints:
            parameters[constraint.property_name] = constraint.value

        return QueryPlan(
            cypher=cypher,
            parameters=parameters,
            strategy=IndexStrategy.FULLTEXT_SEARCH,
            used_indexes=[index.name],
            estimated_cost=2,  # Very efficient for text search
            explanation=f"Using fulltext index {index.name} for text search",
            expected_selectivity=0.1,  # Text search typically quite selective
        )

    def _try_vector_search_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to create a plan using vector indexes"""

        if not request.search_vector:
            return None

        # Find suitable vector indexes
        suitable_indexes = [
            index
            for index in schema.indexes
            if index.type == "VECTOR"
            and (not request.labels or request.labels.intersection(set(index.labels)))
        ]

        if not suitable_indexes:
            return None

        index = suitable_indexes[0]

        # Vector search with cosine similarity (adjust based on your vector setup)
        cypher = f"""
            CALL db.index.vector.queryNodes('{index.name}', $k, $search_vector)
            YIELD node, score
            """

        if request.labels:
            label_conditions = " OR ".join(
                [f"'{label}' IN labels(node)" for label in request.labels]
            )
            cypher += f" WHERE {label_conditions}"

        cypher += " RETURN node as n, score ORDER BY score DESC"

        if request.limit is not None:
            cypher += f" LIMIT ${request.limit}"

        parameters = {"search_vector": request.search_vector, "k": request.limit or 10}

        return QueryPlan(
            cypher=cypher,
            parameters=parameters,
            strategy=IndexStrategy.VECTOR_SEARCH,
            used_indexes=[index.name],
            estimated_cost=3,  # Efficient for semantic search
            explanation=f"Using vector index {index.name} for semantic search",
            expected_selectivity=0.05,  # Vector search very selective
        )

    def _try_range_index_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to create a plan using range indexes for filtering/sorting"""

        # Find constraints that can benefit from range indexes
        indexed_constraints = []
        sort_indexed = []

        for constraint in request.constraints:
            # Check if there's a range index on this property
            for index in schema.indexes:
                if index.type == "RANGE" and constraint.property_name in index.properties:
                    indexed_constraints.append((constraint, index))
                    break

        for sort in request.sort_by:
            for index in schema.indexes:
                if index.type == "RANGE" and sort.property_name in index.properties:
                    sort_indexed.append((sort, index))
                    break

        if not indexed_constraints and not sort_indexed:
            return None

        # Build the query
        if request.labels:
            label = next(iter(request.labels))  # Use first label
            cypher = f"MATCH (n:{label})"
        else:
            cypher = "MATCH (n)"

        # Add WHERE clause for indexed constraints
        if indexed_constraints:
            where_clauses = []
            for constraint, _ in indexed_constraints:
                where_clauses.append(
                    f"n.{constraint.property_name} {constraint.operator} ${constraint.property_name}"
                )
            cypher += f" WHERE {' AND '.join(where_clauses)}"

        cypher += " RETURN n"

        # Add ORDER BY for indexed sorts
        if sort_indexed:
            order_clauses = []
            for sort, _ in sort_indexed:
                order_clauses.append(f"n.{sort.property_name} {sort.direction}")
            cypher += f" ORDER BY {', '.join(order_clauses)}"

        # Add pagination
        if request.skip is not None:
            cypher += f" SKIP ${request.skip}"
        if request.limit is not None:
            cypher += f" LIMIT ${request.limit}"

        parameters = {}
        for constraint, _ in indexed_constraints:
            parameters[constraint.property_name] = constraint.value

        used_indexes = list(
            set(index.name for constraint, index in indexed_constraints + sort_indexed)
        )

        return QueryPlan(
            cypher=cypher,
            parameters=parameters,
            strategy=IndexStrategy.RANGE_FILTER,
            used_indexes=used_indexes,
            estimated_cost=4 + len(request.constraints),  # Good for filtering
            explanation=f"Using range indexes: {', '.join(used_indexes)}",
            expected_selectivity=0.3,  # Depends on constraint selectivity
        )

    def _try_text_index_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to create a plan using text indexes"""

        if not request.search_text:
            return None

        # Find text indexes
        text_indexes = [idx for idx in schema.indexes if idx.type == "TEXT"]
        if not text_indexes:
            return None

        # Use first available text index
        index = text_indexes[0]

        if request.labels:
            label = next(iter(request.labels))
            cypher = (
                f"MATCH (n:{label}) WHERE n.{index.properties[0]} CONTAINS $search_text RETURN n"
            )
        else:
            cypher = f"MATCH (n) WHERE n.{index.properties[0]} CONTAINS $search_text RETURN n"

        if request.limit:
            cypher += f" LIMIT ${request.limit}"

        return QueryPlan(
            cypher=cypher,
            parameters={"search_text": request.search_text},
            strategy=IndexStrategy.TEXT_SEARCH,
            used_indexes=[index.name],
            estimated_cost=6,  # Less efficient than fulltext
            explanation=f"Using text index {index.name}",
            expected_selectivity=0.2,
        )

    def _try_composite_index_plan(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> QueryPlan | None:
        """Try to use composite (multi-property) indexes"""

        if len(request.constraints) < 2:
            return None

        # Find indexes that cover multiple constraint properties
        for index in schema.indexes:
            if len(index.properties) > 1:
                constraint_props = {c.property_name for c in request.constraints}
                index_props = set(index.properties)

                # Check if this index covers multiple of our constraints
                if len(constraint_props.intersection(index_props)) >= 2:
                    # Build query using this composite index
                    if request.labels:
                        label = next(iter(request.labels))
                        cypher = f"MATCH (n:{label})"
                    else:
                        cypher = "MATCH (n)"

                    where_clauses = []
                    parameters = {}

                    for constraint in request.constraints:
                        if constraint.property_name in index.properties:
                            where_clauses.append(
                                f"n.{constraint.property_name} {constraint.operator} ${constraint.property_name}"
                            )
                            parameters[constraint.property_name] = constraint.value

                    if where_clauses:
                        cypher += f" WHERE {' AND '.join(where_clauses)} RETURN n"

                        if request.limit:
                            cypher += f" LIMIT ${request.limit}"

                        return QueryPlan(
                            cypher=cypher,
                            parameters=parameters,
                            strategy=IndexStrategy.COMPOSITE_INDEX,
                            used_indexes=[index.name],
                            estimated_cost=3,  # Very efficient for multi-property lookups
                            explanation=f"Using composite index {index.name}",
                            expected_selectivity=0.05,  # Multi-property very selective
                        )

        return None

    def _generate_fallback_plan(
        self, request: QueryBuildRequest, _schema: SchemaContext
    ) -> QueryPlan:
        """Generate a basic fallback plan without special index optimizations"""

        if request.labels:
            label = next(iter(request.labels))
            cypher = f"MATCH (n:{label})"
        else:
            cypher = "MATCH (n)"

        parameters = {}

        # Add WHERE clause
        if request.constraints:
            where_clauses = []
            for constraint in request.constraints:
                where_clauses.append(
                    f"n.{constraint.property_name} {constraint.operator} ${constraint.property_name}"
                )
                parameters[constraint.property_name] = constraint.value
            cypher += f" WHERE {' AND '.join(where_clauses)}"

        # Add text search as CONTAINS if no fulltext available
        if request.search_text:
            text_clause = "n.title CONTAINS $search_text OR n.description CONTAINS $search_text"
            parameters["search_text"] = request.search_text

            if request.constraints:
                cypher += f" AND ({text_clause})"
            else:
                cypher += f" WHERE {text_clause}"

        cypher += " RETURN n"

        # Add sorting
        if request.sort_by:
            order_clauses = [f"n.{sort.property_name} {sort.direction}" for sort in request.sort_by]
            cypher += f" ORDER BY {', '.join(order_clauses)}"

        # Add pagination
        if request.skip is not None:
            cypher += f" SKIP ${request.skip}"
        if request.limit is not None:
            cypher += f" LIMIT ${request.limit}"

        return QueryPlan(
            cypher=cypher,
            parameters=parameters,
            strategy=IndexStrategy.NO_INDEX,
            used_indexes=[],
            estimated_cost=10,  # High cost - full scan
            explanation="Fallback plan - no suitable indexes found",
            expected_selectivity=0.8,  # Not very selective
        )

    def _select_best_plan(self, plans: list[QueryPlan]) -> QueryPlan:
        """Select the best plan based on cost and strategy"""

        # Sort by strategy preference, then by cost
        strategy_priority = {
            IndexStrategy.UNIQUE_LOOKUP: 1,
            IndexStrategy.FULLTEXT_SEARCH: 2,
            IndexStrategy.VECTOR_SEARCH: 3,
            IndexStrategy.COMPOSITE_INDEX: 4,
            IndexStrategy.RANGE_FILTER: 5,
            IndexStrategy.TEXT_SEARCH: 6,
            IndexStrategy.NO_INDEX: 7,
        }

        # Use centralized sort function with partial to bind strategy_priority
        priority_key = partial(get_query_plan_priority, strategy_priority=strategy_priority)
        return min(plans, key=priority_key)

    def _generate_index_recommendations(
        self, request: QueryBuildRequest, schema: SchemaContext
    ) -> list[IndexRecommendation]:
        """Generate recommendations for creating new indexes"""
        recommendations = []

        # Recommend fulltext index if text search requested but no suitable index
        if (
            request.search_text
            and not any(idx.type == "FULLTEXT" for idx in schema.indexes)
            and request.labels
        ):
            recommendations.extend(
                [
                    IndexRecommendation(
                        index_type="FULLTEXT",
                        labels=[label],
                        properties=["title", "description", "content"],
                        reasoning=f"Text search requested on {label} but no fulltext index available",
                        estimated_benefit="high",
                    )
                    for label in request.labels
                ]
            )

        # Recommend range indexes for frequently filtered properties
        for constraint in request.constraints:
            if constraint.operator in ["<", ">", "<=", ">="]:
                # Check if there's already a range index
                has_range_index = any(
                    idx.type == "RANGE" and constraint.property_name in idx.properties
                    for idx in schema.indexes
                )

                if not has_range_index and constraint.label:
                    recommendations.append(
                        IndexRecommendation(
                            index_type="RANGE",
                            labels=[constraint.label],
                            properties=[constraint.property_name],
                            reasoning=f"Range query on {constraint.property_name} without suitable index",
                            estimated_benefit="medium",
                        )
                    )

        return recommendations

    def _generate_warnings(self, plan: QueryPlan, request: QueryBuildRequest) -> list[str]:
        """Generate warnings for potentially problematic queries"""
        warnings = []

        if isinstance(plan, HasStrategy) and plan.strategy == IndexStrategy.NO_INDEX:
            warnings.append(
                "Query will perform full table scan - consider adding appropriate indexes"
            )

        if plan.estimated_cost > 8:
            warnings.append(f"High estimated cost ({plan.estimated_cost}) - query may be slow")

        if request.limit is None and not request.constraints:
            warnings.append("Unlimited query without constraints may return large result set")

        return warnings

    # ========================================================================
    # TEMPLATE FUNCTIONALITY
    # ========================================================================

    def get_query_explanation(self, plan: QueryPlan) -> str:
        """
        Get a human-readable explanation of what a query plan does.

        Args:
            plan: The query plan to explain

        Returns:
            Human-readable explanation
        """
        explanation_parts = [
            f"Strategy: {plan.strategy.value}",
            f"Estimated Cost: {plan.estimated_cost}",
            f"Explanation: {plan.explanation}",
        ]

        if plan.used_indexes:
            explanation_parts.append(f"Indexes Used: {', '.join(plan.used_indexes)}")
        else:
            explanation_parts.append("No indexes used (may be slow)")

        if plan.expected_selectivity:
            selectivity_pct = plan.expected_selectivity * 100
            explanation_parts.append(f"Expected to return ~{selectivity_pct:.1f}% of data")

        return "\n".join(explanation_parts)

    # ========================================================================
    # FACETED SEARCH SUPPORT
    # ========================================================================
