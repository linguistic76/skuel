"""
Faceted Query Builder
====================

Faceted search query generation.

Part of QueryBuilder decomposition (Phase 2).
Builds queries for faceted search with aggregations and filters.

NOTE: This service depends on QueryOptimizer for full functionality.
The QueryBuilder facade wires these dependencies.
"""

from typing import TYPE_CHECKING

from core.models.query import (
    QueryBuildRequest,
    QueryConstraint,
    QueryOptimizationResult,
    TemplateSpec,
)
from core.models.query.search_models import FacetSetRequest as FacetSetSchema
from core.services.search.core_types import FacetSet
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.query.query_optimizer import QueryOptimizer


class FacetedQueryBuilder:
    """
    Builds faceted search queries with aggregations.

    Generates queries for faceted search interfaces, including
    facet counts and filtered result sets.

    This service is part of the QueryBuilder facade decomposition.
    It depends on QueryOptimizer for query optimization (injected after initialization).
    """

    def __init__(self, schema_service, optimizer: "QueryOptimizer | None" = None) -> None:
        """
        Initialize faceted builder with schema service.

        Args:
            schema_service: Schema context provider
            optimizer: Optional QueryOptimizer for optimization delegation

        Note: QueryBuilder facade injects optimizer after initialization
        to avoid circular dependencies.
        """
        self.schema_service = schema_service
        self.optimizer = optimizer
        self.logger = get_logger("FacetedQueryBuilder")

    async def build_faceted_query(
        self, request: QueryBuildRequest, facets: FacetSet | FacetSetSchema
    ) -> Result[QueryOptimizationResult]:
        """
        Build an optimized query with facet filtering.

        This is crucial for:
        - Progressive learning (filter by level)
        - Domain-specific search
        - Topic filtering
        - User journey tracking in Askesis

        Args:
            request: Base query build request,
            facets: Facets to apply (domain, level, topics, etc.)

        Returns:
            Optimized query plan with facet constraints
        """
        try:
            # Convert FacetSetSchema to FacetSet if needed
            if isinstance(facets, FacetSetSchema):
                facet_set = FacetSet(
                    domain=facets.domain,
                    level=facets.level,
                    intents=facets.intents,
                    topics=facets.topics,
                    filters=facets.filters,
                )
            else:
                facet_set = facets

            # Apply domain facet as label constraint
            if facet_set.domain:
                # Add domain-specific label (e.g., KnowledgeUnit for knowledge domain)
                if facet_set.domain == "knowledge":
                    request.labels.add("Ku")
                elif facet_set.domain == "habits":
                    request.labels.add("Habit")
                elif facet_set.domain == "tasks":
                    request.labels.add("Task")

                # Also add as a property constraint for IN_DOMAIN relationships
                request.constraints.append(
                    QueryConstraint(property_name="domain", operator="=", value=facet_set.domain)
                )

            # Apply level facet
            if facet_set.level:
                request.constraints.append(
                    QueryConstraint(property_name="level", operator="=", value=facet_set.level)
                )

            # Apply topic facets as text search
            if facet_set.topics:
                # Combine topics for text search
                topic_query = " OR ".join(facet_set.topics)
                if request.search_text:
                    request.search_text = f"({request.search_text}) AND ({topic_query})"
                else:
                    request.search_text = topic_query

            # Apply intent facets (for learning-focused search)
            if facet_set.intents:
                # Add intent-based filtering
                for intent in facet_set.intents:
                    if intent == "learn":
                        # Prioritize introductory content
                        request.constraints.append(
                            QueryConstraint(property_name="difficulty", operator="<=", value=3)
                        )
                    elif intent == "practice":
                        # Include exercises and practical content
                        request.constraints.append(
                            QueryConstraint(
                                property_name="content_type",
                                operator="IN",
                                value=["exercise", "practice", "lab"],
                            )
                        )
                    elif intent == "review":
                        # Include completed or familiar content
                        request.constraints.append(
                            QueryConstraint(property_name="mastery_level", operator=">=", value=0.7)
                        )

            # Apply additional filters from facet
            if facet_set.filters:
                for key, value in facet_set.filters.items():
                    request.constraints.append(
                        QueryConstraint(property_name=key, operator="=", value=value)
                    )

            # Build optimized query with all facet constraints
            # Phase 2: Delegate to injected optimizer
            if not self.optimizer:
                return Result.fail(
                    Errors.system(
                        message="QueryOptimizer not available - cannot build faceted query",
                        operation="build_faceted_query",
                    )
                )

            return await self.optimizer.build_optimized_query(request)

        except Exception as e:
            self.logger.error(f"Faceted query building failed: {e}", exc_info=True)
            return Result.fail(
                Errors.validation(
                    field="faceted_query", message=f"Failed to build faceted query: {e!s}"
                )
            )

    async def generate_facet_counts_query(
        self, base_query: str, facet_fields: list[str]
    ) -> Result[dict[str, str]]:
        """
        Generate queries to get facet counts for search refinement.

        This enables the search UI to show:
        - Domain counts (Knowledge: 23, Habits: 15, etc.)
        - Level counts (Intro: 45, Advanced: 12, etc.)
        - Topic counts for drill-down

        Args:
            base_query: The base search query,
            facet_fields: Fields to generate counts for

        Returns:
            Dictionary mapping facet field to count query
        """
        facet_queries = {}

        try:
            # Parse base query to extract the MATCH clause
            # TODO [ENHANCEMENT]: Phase 2 - Use analyze_query_intent for semantic analysis
            # analyze_query_intent(base_query)
            match_clause = base_query.split("RETURN")[0] if "RETURN" in base_query else base_query

            for field in facet_fields:
                if field == "domain":
                    # Count by domain
                    facet_queries["domain"] = f"""
                        {match_clause}
                        MATCH (n)-[:IN_DOMAIN]->(d:Domain)
                        RETURN d.name as value, count(DISTINCT n) as count
                        ORDER BY count DESC
                    """

                elif field == "level":
                    # Count by level
                    facet_queries["level"] = f"""
                        {match_clause}
                        WHERE n.level IS NOT NULL
                        RETURN n.level as value, count(*) as count
                        ORDER BY value
                    """

                elif field == "content_type":
                    # Count by content type
                    facet_queries["content_type"] = f"""
                        {match_clause}
                        WHERE n.content_type IS NOT NULL
                        RETURN n.content_type as value, count(*) as count
                        ORDER BY count DESC
                    """

                elif field == "tags":
                    # Count by tags (top 10)
                    facet_queries["tags"] = f"""
                        {match_clause}
                        UNWIND n.tags as tag
                        RETURN tag as value, count(*) as count
                        ORDER BY count DESC
                        LIMIT 10
                    """

                elif field == "has_prerequisites":
                    # Count items with/without prerequisites
                    facet_queries["has_prerequisites"] = f"""
                        {match_clause}
                        OPTIONAL MATCH (n)<-[:PREREQUISITE_FOR]-()
                        RETURN
                            CASE WHEN count(*) > 0 THEN 'Has Prerequisites'
                                 ELSE 'No Prerequisites' END as value,
                            count(DISTINCT n) as count
                    """

                else:
                    # Generic facet count
                    facet_queries[field] = f"""
                        {match_clause}
                        WHERE n.{field} IS NOT NULL
                        RETURN n.{field} as value, count(*) as count
                        ORDER BY count DESC
                        LIMIT 20
                    """

            return Result.ok(facet_queries)

        except Exception as e:
            self.logger.error(f"Facet count query generation failed: {e}", exc_info=True)
            return Result.fail(
                Errors.validation(
                    field="facet_counts", message=f"Failed to generate facet count queries: {e!s}"
                )
            )

    def register_faceted_templates(self, template_manager):
        """Register templates optimized for faceted search."""

        # Faceted knowledge search
        template_manager.register_template(
            "faceted_knowledge_search",
            TemplateSpec(
                name="faceted_knowledge_search",
                description="Search knowledge with facets",
                base_template="""
                    MATCH (n:Ku)
                    WHERE ($domain IS NULL OR EXISTS((n)-[:IN_DOMAIN]->(:Domain {name: $domain})))
                    AND ($level IS NULL OR n.level = $level)
                    AND ($search_text IS NULL OR
                         n.title CONTAINS $search_text OR
                         n.content CONTAINS $search_text)
                    RETURN n
                    ORDER BY n.updated_at DESC
                    LIMIT $limit
                """,
                required_parameters=set(),
                optional_parameters={"domain", "level", "search_text", "limit"},
                optimization_rules={
                    "has_fulltext_index": """
                        CALL db.index.fulltext.queryNodes('knowledge_fulltext', $search_text)
                        YIELD node, score
                        WHERE ($domain IS NULL OR EXISTS((node)-[:IN_DOMAIN]->(:Domain {name: $domain})))
                        AND ($level IS NULL OR node.level = $level)
                        RETURN node as n, score
                        ORDER BY score DESC
                        LIMIT $limit
                    """
                },
                estimated_base_cost=5,
            ),
            category="faceted_search",
        )

        # Faceted aggregation for counts
        template_manager.register_template(
            "facet_aggregation",
            TemplateSpec(
                name="facet_aggregation",
                description="Get facet counts for refinement",
                base_template="""
                    MATCH (n:$label)
                    WHERE $base_conditions
                    WITH n
                    RETURN n.$facet_field as value, count(*) as count
                    ORDER BY count DESC
                    LIMIT 20
                """,
                required_parameters={"label", "facet_field", "base_conditions"},
                estimated_base_cost=6,
            ),
            category="faceted_search",
        )

        # Progressive learning search
        template_manager.register_template(
            "progressive_learning_search",
            TemplateSpec(
                name="progressive_learning_search",
                description="Search with progressive difficulty filtering",
                base_template="""
                    MATCH (n:Ku)
                    WHERE n.level <= $user_level
                    AND NOT EXISTS((n)<-[:COMPLETED]-(:User {uid: $user_uid}))
                    AND ($search_text IS NULL OR n.title CONTAINS $search_text)
                    OPTIONAL MATCH (n)<-[:PREREQUISITE_FOR]-(prereq)
                    WITH n, collect(prereq.uid) as prerequisites
                    WHERE ALL(p IN prerequisites WHERE EXISTS((:User {uid: $user_uid})-[:COMPLETED]->(:Ku {uid: p})))
                    RETURN n
                    ORDER BY n.level ASC, n.created_at DESC
                    LIMIT $limit
                """,
                required_parameters={"user_uid", "user_level"},
                optional_parameters={"search_text", "limit"},
                estimated_base_cost=7,
            ),
            category="faceted_search",
        )

        self.logger.info("Registered faceted search templates")
