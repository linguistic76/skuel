"""
Search Routes - Calm Design with Sidebar Layout
================================================

FastHTML routes for the search page with calm sidebar design.

Security:
- All search routes require authentication (January 2026 hardening)
- No fallback to default user - search is user-scoped

Architecture:
    - UI Components: /components/search_components.py
    - CSS: /static/css/search.css
    - JavaScript: /static/js/search_sidebar.js

Philosophy: "Users can handle complexity, but they need visual calm to process it."

Version: 3.1-security-hardened
"""

from typing import TYPE_CHECKING, Any

from starlette.requests import Request

from components.search_components import (
    render_empty_search_prompt,
    render_search_error,
    render_search_page_with_navbar,
    render_search_results,
)
from core.auth import require_authenticated_user
from core.models.enums import (
    ContentType,
    EducationalLevel,
    KuStatus,
    LearningLevel,
    Priority,
    SELCategory,
)
from core.models.enums.entity_enums import NonKuDomain
from core.models.enums.ku_enums import KuType
from core.models.relationship_names import RelationshipName
from core.models.search import SearchRouter
from core.models.search_request import SearchRequest

if TYPE_CHECKING:
    from core.utils.services_bootstrap import Services
from adapters.inbound.boundary import boundary_handler
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.search")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _none_if_empty(value: str | None) -> str | None:
    """Convert empty strings to None."""
    return None if not value or value.strip() == "" else value


def _checkbox_to_bool(value: str | None) -> bool:
    """Convert checkbox values to boolean."""
    return value == "true" if value else False


# ============================================================================
# ROUTES
# ============================================================================


def create_search_routes(
    app: Any,
    rt: Any,
    services: "Services",
    search_router: SearchRouter,
) -> None:
    """Wire search routes with explicit SearchRouter dependency."""

    @app.get("/search")
    async def search_page(request: Request) -> Any:
        """Main search page with unified BasePage layout."""
        require_authenticated_user(request)  # Enforce authentication

        return await render_search_page_with_navbar(request)

    @app.get("/search/results")
    @boundary_handler()
    async def search_results(
        request: Request,
        query: str = "",
        # Scope filters
        entity_type: str | None = None,
        sort_order: str = "relevance",
        # Common filters (NEW)
        status: str | None = None,
        priority: str | None = None,
        # Domain-specific filters (NEW)
        frequency: str | None = None,
        event_type: str | None = None,
        urgency: str | None = None,
        strength: str | None = None,
        # Knowledge filters
        sel_category: str | None = None,
        learning_level: str | None = None,
        content_type: str | None = None,
        educational_level: str | None = None,
        # Graph relationship filters
        ready_to_learn: str | None = None,
        builds_on_mastered: str | None = None,
        in_active_path: str | None = None,
        supports_goals: str | None = None,
        builds_on_habits: str | None = None,
        applied_in_tasks: str | None = None,
        aligned_with_principles: str | None = None,
        next_logical_step: str | None = None,
        # Nous-specific filters
        nous_section: str | None = None,
        # Pedagogical filters
        not_yet_viewed: str | None = None,
        viewed_not_mastered: str | None = None,
        ready_to_review: str | None = None,
        # Semantic search filters (Phase 1 Enhancement - January 2026)
        enable_semantic_boost: str | None = None,
        enable_learning_aware: str | None = None,
        prefer_unmastered: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        """Execute search and return HTML results. Requires authentication."""
        user_uid = require_authenticated_user(request)

        if not query.strip():
            return render_empty_search_prompt()

        # Debug logging
        logger.info(
            f"Search params: query={query}, entity_type={entity_type!r}, sort_order={sort_order!r}"
        )
        logger.info(f"Common filters: status={status!r}, priority={priority!r}")
        logger.info(
            f"Relationship filters: ready_to_learn={ready_to_learn!r}, "
            f"builds_on_mastered={builds_on_mastered!r}, in_active_path={in_active_path!r}, "
            f"supports_goals={supports_goals!r}, builds_on_habits={builds_on_habits!r}, "
            f"applied_in_tasks={applied_in_tasks!r}, aligned_with_principles={aligned_with_principles!r}, "
            f"next_logical_step={next_logical_step!r}"
        )

        # Clean up filter values
        entity_type = _none_if_empty(entity_type)
        status = _none_if_empty(status)
        priority = _none_if_empty(priority)
        frequency = _none_if_empty(frequency)
        event_type = _none_if_empty(event_type)
        urgency = _none_if_empty(urgency)
        strength = _none_if_empty(strength)
        sel_category = _none_if_empty(sel_category)
        learning_level = _none_if_empty(learning_level)
        content_type = _none_if_empty(content_type)
        educational_level = _none_if_empty(educational_level)
        nous_section = _none_if_empty(nous_section)

        # Convert relationship filters to boolean
        ready_to_learn_bool = _checkbox_to_bool(ready_to_learn)
        builds_on_mastered_bool = _checkbox_to_bool(builds_on_mastered)
        in_active_path_bool = _checkbox_to_bool(in_active_path)
        supports_goals_bool = _checkbox_to_bool(supports_goals)
        builds_on_habits_bool = _checkbox_to_bool(builds_on_habits)
        applied_in_tasks_bool = _checkbox_to_bool(applied_in_tasks)
        aligned_with_principles_bool = _checkbox_to_bool(aligned_with_principles)
        next_logical_step_bool = _checkbox_to_bool(next_logical_step)

        # Convert pedagogical filters to boolean
        not_yet_viewed_bool = _checkbox_to_bool(not_yet_viewed)
        viewed_not_mastered_bool = _checkbox_to_bool(viewed_not_mastered)
        ready_to_review_bool = _checkbox_to_bool(ready_to_review)

        # Convert semantic search filters to boolean (Phase 1 Enhancement)
        enable_semantic_boost_bool = _checkbox_to_bool(enable_semantic_boost)
        enable_learning_aware_bool = _checkbox_to_bool(enable_learning_aware)
        prefer_unmastered_bool = _checkbox_to_bool(prefer_unmastered)

        # Parse entity type to KuType/NonKuDomain enum
        parsed_entity_types: list[KuType | NonKuDomain] = []
        if entity_type:
            et = KuType.from_string(entity_type) or NonKuDomain.from_string(entity_type)
            if et:
                parsed_entity_types = [et]

        # Build extended_facets for domain-specific filters
        extended_facets: dict[str, Any] = {}
        if frequency:
            extended_facets["frequency"] = frequency
        if event_type:
            extended_facets["event_type"] = event_type
        if urgency:
            extended_facets["urgency"] = urgency
        if strength:
            extended_facets["strength"] = strength

        # Build SearchRequest with safe enum conversion
        try:
            search_request = SearchRequest(
                query_text=query,
                # Scope
                entity_types=parsed_entity_types,
                # Common filters (convert to enums)
                status=KuStatus(status) if status else None,
                priority=Priority(priority) if priority else None,
                # Domain-specific filters
                extended_facets=extended_facets if extended_facets else None,
                # Knowledge filters
                sel_category=SELCategory(sel_category) if sel_category else None,
                learning_level=LearningLevel(learning_level) if learning_level else None,
                content_type=ContentType(content_type) if content_type else None,
                educational_level=EducationalLevel(educational_level)
                if educational_level
                else None,
                # Graph relationship filters
                ready_to_learn=ready_to_learn_bool,
                builds_on_mastered=builds_on_mastered_bool,
                in_active_path=in_active_path_bool,
                supports_goals=supports_goals_bool,
                builds_on_habits=builds_on_habits_bool,
                applied_in_tasks=applied_in_tasks_bool,
                aligned_with_principles=aligned_with_principles_bool,
                next_logical_step=next_logical_step_bool,
                # Nous-specific filters
                nous_section=nous_section,
                # Pedagogical filters
                not_yet_viewed=not_yet_viewed_bool,
                viewed_not_mastered=viewed_not_mastered_bool,
                ready_to_review=ready_to_review_bool,
                # Semantic search filters (Phase 1 Enhancement)
                enable_semantic_boost=enable_semantic_boost_bool,
                enable_learning_aware=enable_learning_aware_bool,
                prefer_unmastered=prefer_unmastered_bool,
                user_uid=user_uid,
                limit=limit,
                offset=offset,
                include_facet_counts=True,
            )
        except ValueError as e:
            logger.error(f"Invalid filter value: {e}")
            return render_search_error("Invalid filter selection. Please try again.", "warning")

        # Execute search via SearchRouter (One Path Forward)
        # SearchRouter.faceted_search handles strategy selection internally
        result = await search_router.faceted_search(search_request, user_uid)

        if result.is_error:
            logger.error(f"Search failed: {result.error}")
            return render_search_error(f"Search error: {result.error}")

        # Render results
        return render_search_results(result.value)

    # ========================================================================
    # UNIFIED SEARCH API ENDPOINT
    # ========================================================================

    @app.post("/api/search/unified")
    @boundary_handler()
    async def unified_search_api(
        request: Request,
        query: str = "",
        entity_types: str = "",  # Comma-separated: "ku,task,goal"
        connected_to: str | None = None,
        relationship: str | None = None,
        direction: str = "outgoing",
        tags: str = "",  # Comma-separated: "python,ml"
        tags_match_all: bool = False,
        limit: int = 50,
        limit_per_domain: int = 20,
    ) -> dict[str, Any]:
        """
        Unified search API combining text, graph, and array search.

        This endpoint combines all Phase 1-3 search capabilities:
        - Text search on configured fields
        - Graph-aware filtering (relationship traversal)
        - Tag/array filtering (AND/OR semantics)

        Args:
            query: Text search query
            entity_types: Comma-separated entity types (ku,task,goal,habit,event,choice,principle)
            connected_to: UID of entity to traverse from (graph filter)
            relationship: Relationship type name (e.g., ENABLES, REQUIRES_KNOWLEDGE)
            direction: outgoing, incoming, or both
            tags: Comma-separated tags to filter by
            tags_match_all: True = AND semantics, False = OR semantics
            limit: Total result limit
            limit_per_domain: Results per entity type

        Returns:
            {
                "query": str,
                "total_count": int,
                "results_by_domain": {
                    "ku": [{"uid": str, "title": str, ...}, ...],
                    "task": [...],
                },
                "top_results": [...]  # Merged top results across domains
            }

        Example:
            POST /api/search/unified
            {
                "query": "machine learning",
                "entity_types": "ku,task",
                "connected_to": "ku.python-basics",
                "relationship": "ENABLES",
                "tags": "python,beginner"
            }
        """
        require_authenticated_user(request)

        if not query.strip():
            return {"error": "Query is required", "total_count": 0, "results_by_domain": {}}

        # Parse entity types
        parsed_entity_types: list[KuType | NonKuDomain] = []
        if entity_types.strip():
            for et_str in entity_types.split(","):
                et_str = et_str.strip()
                parsed = KuType.from_string(et_str) or NonKuDomain.from_string(et_str)
                if parsed:
                    parsed_entity_types.append(parsed)
                else:
                    logger.warning(f"Unknown entity type: {et_str}")

        # Parse relationship
        parsed_relationship = None
        if relationship:
            try:
                parsed_relationship = RelationshipName(relationship)
            except ValueError:
                logger.warning(f"Unknown relationship: {relationship}")

        # Parse tags
        parsed_tags = None
        if tags.strip():
            parsed_tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Build request (SearchRequest is THE canonical model)
        search_request = SearchRequest(
            query_text=query,
            entity_types=parsed_entity_types,
            connected_to_uid=connected_to,
            connected_relationship=parsed_relationship,
            connected_direction=direction,
            tags_contain=parsed_tags,
            tags_match_all=tags_match_all,
            limit=limit,
        )

        # Execute search
        result = await search_router.advanced_search(search_request)

        if result.is_error:
            logger.error(f"Unified search failed: {result.error}")
            return {"error": str(result.error), "total_count": 0, "results_by_domain": {}}

        # Format response
        unified_result = result.value
        response: dict[str, Any] = {
            "query": unified_result.query,
            "total_count": unified_result.total_count,
            "results_by_domain": {},
            "top_results": [],
        }

        # Convert results by domain
        for entity_type, items in unified_result.results_by_domain.items():
            response["results_by_domain"][entity_type.value] = [
                {
                    "uid": item.uid,
                    "title": item.title,
                    "entity_type": item.entity_type.value,
                    "relevance_score": item.relevance_score,
                    "priority_score": item.priority_score,
                    "combined_score": item.combined_score,
                    "match_reason": item.match_reason,
                }
                for item in items
            ]

        # Add top results (sorted by combined score) - property returns top 10
        response["top_results"] = unified_result.top_results

        return response


__all__ = ["create_search_routes"]
