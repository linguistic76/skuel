"""
Article API - Migrated to CRUDRouteFactory
===========================================

Sixth migration in CRUD API rollout.

Before: 327 lines of manual route definitions
After: ~270 lines

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (relationships, content, search, organization, analytics)
"""

from typing import Any

from fasthtml.common import Request
from pydantic import ValidationError

from adapters.inbound.auth import require_admin, require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import (
    CRUDRouteFactory,
    IntelligenceRouteFactory,
    parse_int_query_param,
)
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory
from core.models.article.article_request import (
    ArticleContentUpdateRequest,
    ArticleCreateRequest,
    ArticleRelationshipCreateRequest,
)
from core.models.entity_requests import AddTagsRequest, EntityUpdateRequest, RemoveTagsRequest
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.services.article_service import ArticleService
from core.utils.result_simplified import Errors, Result
from ui.feedback import Alert, AlertT


def create_article_api_routes(
    app: Any, rt: Any, article_service: ArticleService, user_service: Any = None
) -> list[Any]:
    """
    Create Article API routes using factory pattern.

    SECURITY: CRUD write operations (create, update, delete) require ADMIN role.
    Read operations (get, list) are public.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        article_service: Article service instance
        user_service: User service for admin role verification
    """

    def user_service_getter():
        return user_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated, Admin-Gated Writes)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=article_service,
        domain_name="article",
        create_schema=ArticleCreateRequest,
        update_schema=EntityUpdateRequest,
        uid_prefix="a",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )

    # Register all standard CRUD routes:
    # - POST /api/article (create)
    # - GET /api/article/{uid} (get)
    # - PUT /api/article/{uid} (update)
    # - DELETE /api/article/{uid} (delete)
    # - GET /api/article (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=article_service.intelligence,
        domain_name="article",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/article/context?uid=...&depth=2 (entity with graph context)
    # - GET /api/article/analytics?period_days=30 (user performance analytics)
    # - GET /api/article/insights?uid=... (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Article Relationships
    # ---------------------

    @rt("/api/article/relationships", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def create_article_relationship_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Create a relationship between articles. Requires ADMIN role."""
        body = await request.json()
        try:
            req = ArticleRelationshipCreateRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await article_service.create_article_relationship(
            uid, req.target_uid, req.type, req.strength, req.description
        )

    @rt("/api/article/relationships", methods=["GET"])
    @boundary_handler()
    async def get_article_relationships_route(request: Request, uid: str) -> Result[Any]:
        """Get relationships for an article."""
        params = dict(request.query_params)
        relationship_type = params.get("type")
        # Note: direction param not supported by ArticleService - ignoring for now

        return await article_service.get_article_relationships(uid, relationship_type)

    @rt("/api/article/prerequisites")
    @boundary_handler()
    async def get_article_prerequisites_route(request: Request, uid: str) -> Result[Any]:
        """Get prerequisites for an article."""
        return await article_service.get_article_prerequisites(uid)

    @rt("/api/article/dependencies")
    @boundary_handler()
    async def get_article_dependencies_route(request: Request, uid: str) -> Result[Any]:
        """Get what depends on this article."""
        return await article_service.get_article_dependencies(uid)

    # Curriculum Content Operations
    # ---------------------

    @rt("/api/article/content", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def update_article_content_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Update article content. Requires ADMIN role."""
        body = await request.json()
        try:
            req = ArticleContentUpdateRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await article_service.update_article_content(uid, req.content, req.title)

    @rt("/api/article/tags", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def add_article_tags_route(request: Request, current_user: Any, uid: str) -> Result[Any]:
        """Add tags to an article. Requires ADMIN role."""
        body = await request.json()
        try:
            req = AddTagsRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await article_service.add_article_tags(uid, req.tags)

    @rt("/api/article/tags", methods=["DELETE"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def remove_article_tags_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Remove tags from an article. Requires ADMIN role."""
        body = await request.json()
        try:
            req = RemoveTagsRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await article_service.remove_article_tags(uid, req.tags)

    # Article Search and Discovery
    # ----------------------------

    @rt("/api/article/search")
    @boundary_handler()
    async def search_article_route(request: Request) -> Result[Any]:
        """Search articles by content, title, or tags."""
        params = dict(request.query_params)
        query = params.get("q", "")
        # Note: search_type param not supported by ArticleService - searches all by default
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=100)

        return await article_service.search_articles(query, limit)

    @rt("/api/article/related")
    @boundary_handler()
    async def find_related_article_route(request: Request, uid: str) -> Result[Any]:
        """Find articles related to the given one."""
        params = dict(request.query_params)
        similarity_threshold = float(params.get("threshold", 0.7))
        limit = parse_int_query_param(params, "limit", 10, minimum=1, maximum=500)

        return await article_service.find_related_articles(uid, similarity_threshold, limit)

    @rt("/api/article/recommendations")
    @boundary_handler()
    async def get_article_recommendations_route(request: Request, uid: str) -> Result[Any]:
        """Get personalized article recommendations."""
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        recommendation_type = params.get("type", "learning")

        return await article_service.get_article_recommendations(uid, user_uid, recommendation_type)

    # Article Organization
    # --------------------

    @rt("/api/article/domains")
    @boundary_handler()
    async def list_article_domains_route(_request: Request) -> Result[Any]:
        """List all article domains."""
        return await article_service.list_article_domains()

    @rt("/api/article/by-domain")
    @boundary_handler()
    async def get_article_by_domain_route(request: Request, domain: str) -> Result[Any]:
        """Get articles in a specific domain."""
        params = dict(request.query_params)
        limit = parse_int_query_param(params, "limit", 100, minimum=1, maximum=500)

        return await article_service.get_articles_by_domain(domain, limit)

    @rt("/api/article/categories")
    @boundary_handler()
    async def list_article_categories_route(_request: Request) -> Result[Any]:
        """List all article categories."""
        return await article_service.list_article_categories()

    @rt("/api/article/tags")
    @boundary_handler()
    async def list_article_tags_route(request: Request) -> Result[Any]:
        """List all article tags with usage counts."""
        params = dict(request.query_params)
        min_usage = parse_int_query_param(params, "min_usage", 1, minimum=0)

        return await article_service.list_article_tags(min_usage)

    # Article Analytics
    # -----------------

    @rt("/api/article/stats")
    @boundary_handler()
    async def get_article_stats_route(request: Request, uid: str) -> Result[Any]:
        """Get statistics for an article."""
        return await article_service.get_article_stats(uid)

    # ========================================================================
    # USER CONTEXT ROUTES - Article-Activity Integration (January 2026)
    # ========================================================================

    @rt("/api/article/my-context")
    @boundary_handler()
    async def get_article_user_context_route(request: Request, uid: str) -> Result[Any]:
        """
        Get personalized context for how the current user uses this article.

        Returns per-user substance score, activity breakdown, and recommendations
        for deepening article application.

        Requires authentication - returns 401 if not logged in.

        Response example:
        {
            "ku_uid": "ku.python-basics",
            "user_substance_score": 0.45,
            "breakdown": {
                "tasks": {"count": 3, "uids": [...], "score": 0.15},
                "habits": {"count": 1, "uids": [...], "score": 0.10},
                ...
            },
            "recommendations": [
                {"type": "journal", "message": "Reflect on...", "impact": "+0.07"}
            ]
        }
        """
        user_uid = require_authenticated_user(request)

        # Get UserContext for this user
        if not article_service.user_service:
            return Result.fail(
                Errors.system(
                    message="User service not available",
                    operation="get_article_user_context",
                )
            )

        context_result = await article_service.user_service.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value
        return await article_service.get_user_article_context(uid, user_context)

    # ========================================================================
    # ADAPTIVE CURRICULUM ROUTES (absorbed from SEL)
    # ========================================================================

    @rt("/api/article/journey")
    @boundary_handler()
    async def get_article_journey(request: Request) -> Result[Any]:
        """Get user's SEL learning journey — progress across all 5 categories."""
        user_uid = require_authenticated_user(request)
        return await article_service.get_sel_journey(user_uid)

    @rt("/api/article/curriculum/{category}")
    @boundary_handler()
    async def get_personalized_curriculum(
        request: Request, category: str, limit: int = 10
    ) -> Result[Any]:
        """Get personalized article curriculum for an SEL category."""
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid SEL category: {category}"))
        return await article_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

    @rt("/api/article/journey-html")
    async def get_article_journey_html(request: Request) -> Any:
        """HTMX: Render SEL journey as HTML fragment."""
        from fasthtml.common import P

        user_uid = require_authenticated_user(request)
        result = await article_service.get_sel_journey(user_uid)

        if result.is_error:
            return Alert(
                P("Unable to load your learning journey.", cls="text-center py-8"),
                variant=AlertT.error,
            )

        from ui.patterns.curriculum_adaptive import SELJourneyOverview

        return SELJourneyOverview(result.value)

    @rt("/api/article/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
        """HTMX: Render personalized curriculum grid as HTML fragment."""
        from fasthtml.common import Div, P

        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)

        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Alert(P(f"Invalid category: {category}"), variant=AlertT.error)

        result = await article_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

        if result.is_error:
            return Alert(P("Unable to load curriculum."), variant=AlertT.error)

        curriculum = result.value
        if not curriculum:
            from ui.patterns.empty_state import EmptyState

            return EmptyState(
                title="No curriculum available yet",
                description="Complete prerequisite knowledge units to unlock content in this area.",
                icon="📚",
            )

        from ui.patterns.curriculum_adaptive import AdaptiveKUCard

        return Div(
            *[AdaptiveKUCard(ku) for ku in curriculum],
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        )

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    # Analytics handler functions
    async def handle_summary_analytics(service, params):
        """Handle summary analytics for all articles."""
        time_period = params.get("period", "month")
        return await service.get_article_summary_analytics(time_period)

    async def handle_graph_structure(service, params):
        """Handle article graph structure and metrics."""
        include_metrics = params.get("metrics", "true").lower() == "true"
        return await service.get_article_graph_structure(include_metrics)

    # Create analytics factory
    analytics_factory = AnalyticsRouteFactory(
        service=article_service,
        domain_name="article",
        analytics_config={
            "summary": {
                "path": "/api/article/analytics/summary",
                "handler": handle_summary_analytics,
                "description": "Get summary analytics for all articles",
                "methods": ["GET"],
            },
            "graph_structure": {
                "path": "/api/article/graph/structure",
                "handler": handle_graph_structure,
                "description": "Get article graph structure and metrics",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    return []  # Routes registered via @rt() decorators (no objects returned)


# Migration Statistics:
# =====================
# - CRUD Factory Migration:
# Before (ku_api.py): 327 lines
# After (CRUD factory): ~270 lines
# CRUD Reduction: 57 lines (17% reduction via CRUDRouteFactory)
#
# - Analytics Factory Migration:
# Analytics endpoints migrated: 2 (summary, graph structure)
# Analytics before: ~26 lines (13 lines × 2 endpoints)
# Analytics after: ~20 lines (handlers + factory config)
# Analytics Reduction: ~6 lines (23% reduction via AnalyticsRouteFactory)
#
# Total Reduction: ~63 lines (19% overall reduction)
#
# Factory usage:
# - CRUDRouteFactory: 5 standard CRUD routes
# - AnalyticsRouteFactory: 2 analytics endpoints
# - Manual routes: 17 domain-specific routes
