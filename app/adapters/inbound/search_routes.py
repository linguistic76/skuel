"""
Search Routes — Configuration-Driven Registration
===================================================

FastHTML routes for the search page with calm sidebar design.

Security:
- All search routes require authentication (January 2026 hardening)
- No fallback to default user - search is user-scoped

Architecture:
    - UI Components: /components/search_components.py
    - CSS: /static/css/search.css
    - JavaScript: /static/js/search_sidebar.js

Philosophy: "Users can handle complexity, but they need visual calm to process it."
"""

from typing import TYPE_CHECKING, Any, Literal, cast

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.route_factories import (
    DomainRouteConfig,
    register_domain_routes,
    split_csv,
)
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.relationship_names import RelationshipName
from core.models.search_request import SearchRequest
from ui.search.components import (
    render_empty_search_prompt,
    render_search_error,
    render_search_page_with_navbar,
    render_search_results,
)

if TYPE_CHECKING:
    from services_bootstrap import Services

from core.utils.logging import get_logger

logger = get_logger("skuel.routes.search")


# ============================================================================
# API FACTORY
# ============================================================================


def create_search_api_routes(
    app: FastHTMLApp, rt: RouteDecorator, search_router: Any, **_kwargs: Any
) -> list[Any]:
    """Create search routes with SearchRouter dependency."""

    @rt("/search")
    async def search_page(request: Request) -> Any:
        """Main search page with unified BasePage layout."""
        require_authenticated_user(request)

        return await render_search_page_with_navbar(request)

    @rt("/search/results")
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
        # Semantic search filters
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

        logger.info(
            f"Search params: query={query}, entity_type={entity_type!r}, "
            f"status={status!r}, priority={priority!r}"
        )

        # Build SearchRequest — all normalization (empty→None, checkbox→bool,
        # enum parsing, extended_facets assembly) lives on the model
        try:
            search_request = SearchRequest.from_form_params(
                query=query,
                user_uid=user_uid,
                entity_type=entity_type,
                _sort_order=sort_order,
                status=status,
                priority=priority,
                frequency=frequency,
                event_type=event_type,
                urgency=urgency,
                strength=strength,
                sel_category=sel_category,
                learning_level=learning_level,
                content_type=content_type,
                educational_level=educational_level,
                ready_to_learn=ready_to_learn,
                builds_on_mastered=builds_on_mastered,
                in_active_path=in_active_path,
                supports_goals=supports_goals,
                builds_on_habits=builds_on_habits,
                applied_in_tasks=applied_in_tasks,
                aligned_with_principles=aligned_with_principles,
                next_logical_step=next_logical_step,
                nous_section=nous_section,
                not_yet_viewed=not_yet_viewed,
                viewed_not_mastered=viewed_not_mastered,
                ready_to_review=ready_to_review,
                enable_semantic_boost=enable_semantic_boost,
                enable_learning_aware=enable_learning_aware,
                prefer_unmastered=prefer_unmastered,
                limit=limit,
                offset=offset,
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

    @rt("/api/search/unified", methods=["POST"])
    @csrf_protected
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

        This endpoint combines all -3 search capabilities:
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
                "top_results": [...] # Merged top results across domains
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

        # Validate graph-traversal direction at the boundary — SearchRequest narrows
        # connected_direction to a Literal, so an invalid value would otherwise raise an
        # unhandled Pydantic ValidationError during model construction.
        if direction not in ("outgoing", "incoming", "both"):
            return {
                "error": f"Invalid direction '{direction}'. Use 'outgoing', 'incoming', or 'both'.",
                "total_count": 0,
                "results_by_domain": {},
            }

        # Parse entity types
        parsed_entity_types: list[EntityType | NonKuDomain] = []
        if entity_types.strip():
            for et_str in split_csv(entity_types):
                parsed = EntityType.from_string(et_str) or NonKuDomain.from_string(et_str)
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
            parsed_tags = split_csv(tags) or None

        # Build request (SearchRequest is THE canonical model)
        search_request = SearchRequest(
            query_text=query,
            entity_types=parsed_entity_types,
            connected_to_uid=connected_to,
            connected_relationship=parsed_relationship,
            connected_direction=cast("Literal['outgoing', 'incoming', 'both']", direction),
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
        for et, items in unified_result.results_by_domain.items():
            response["results_by_domain"][et.value] = [item.to_dict() for item in items]

        # Add top results (sorted by combined score) - property returns top 10
        response["top_results"] = unified_result.top_results

        return response

    return [search_page, search_results, unified_search_api]


SEARCH_CONFIG = DomainRouteConfig(
    domain_name="search",
    primary_service_attr="search_router",
    api_factory=create_search_api_routes,
)


def create_search_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services", _sync_service: Any = None
) -> None:
    """Wire search routes via DomainRouteConfig."""
    register_domain_routes(app, rt, services, SEARCH_CONFIG)


__all__ = ["create_search_routes"]
