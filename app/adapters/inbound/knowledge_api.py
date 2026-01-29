"""
Knowledge API - Migrated to CRUDRouteFactory
=============================================

Sixth migration in Phase 1 CRUD API rollout.

Before: 327 lines of manual route definitions
After: ~270 lines

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (relationships, content, search, organization, analytics)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from core.auth import require_authenticated_user
from core.infrastructure.routes import CRUDRouteFactory, IntelligenceRouteFactory
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.models.ku.ku_request import KuCreateRequest, KuUpdateRequest
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols.facade_protocols import KuFacadeProtocol


def create_knowledge_api_routes(app: Any, rt: Any, ku_service: KuFacadeProtocol) -> list[Any]:
    """
    Create knowledge API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        ku_service: Knowledge service instance
    """

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for standard CRUD operations
    crud_factory = CRUDRouteFactory(
        service=ku_service,
        domain_name="knowledge",
        create_schema=KuCreateRequest,
        update_schema=KuUpdateRequest,
        uid_prefix="knowledge",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register all standard CRUD routes:
    # - POST   /api/knowledge           (create)
    # - GET    /api/knowledge/{uid}     (get)
    # - PUT    /api/knowledge/{uid}     (update)
    # - DELETE /api/knowledge/{uid}     (delete)
    # - GET    /api/knowledge           (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=ku_service.intelligence,
        domain_name="knowledge",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/knowledge/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/knowledge/analytics?period_days=30   (user performance analytics)
    # - GET /api/knowledge/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Knowledge Relationships
    # -----------------------

    @rt("/api/knowledge/relationships", methods=["POST"])
    @boundary_handler()
    async def create_knowledge_relationship_route(request: Request, uid: str) -> Result[Any]:
        """Create a relationship between knowledge units."""
        body = await request.json()
        target_uid = body.get("target_uid")
        relationship_type = body.get("type", "RELATED_TO")
        strength = body.get("strength", 1.0)
        description = body.get("description", "")

        return await ku_service.create_knowledge_relationship(
            uid, target_uid, relationship_type, strength, description
        )

    @rt("/api/knowledge/relationships", methods=["GET"])
    @boundary_handler()
    async def get_knowledge_relationships_route(request: Request, uid: str) -> Result[Any]:
        """Get relationships for a knowledge unit."""
        params = dict(request.query_params)
        relationship_type = params.get("type")
        # Note: direction param not supported by KuService - ignoring for now

        return await ku_service.get_knowledge_relationships(uid, relationship_type)

    @rt("/api/knowledge/prerequisites")
    @boundary_handler()
    async def get_knowledge_prerequisites_route(request: Request, uid: str) -> Result[Any]:
        """Get prerequisites for a knowledge unit."""
        return await ku_service.get_knowledge_prerequisites(uid)

    @rt("/api/knowledge/dependencies")
    @boundary_handler()
    async def get_knowledge_dependencies_route(request: Request, uid: str) -> Result[Any]:
        """Get what depends on this knowledge unit."""
        return await ku_service.get_knowledge_dependencies(uid)

    # Knowledge Content Operations
    # -----------------------------

    @rt("/api/knowledge/content")
    @boundary_handler()
    async def update_ku_content_route(request: Request, uid: str) -> Result[Any]:
        """Update knowledge unit content."""
        body = await request.json()
        content = body.get("content")
        title = body.get("title")  # Optional title update
        # Note: content_type and update_metadata params not supported by KuService

        return await ku_service.update_ku_content(uid, content, title)

    @rt("/api/knowledge/tags", methods=["POST"])
    @boundary_handler()
    async def add_knowledge_tags_route(request: Request, uid: str) -> Result[Any]:
        """Add tags to a knowledge unit."""
        body = await request.json()
        tags = body.get("tags", [])

        return await ku_service.add_knowledge_tags(uid, tags)

    @rt("/api/knowledge/tags", methods=["DELETE"])
    @boundary_handler()
    async def remove_knowledge_tags_route(request: Request, uid: str) -> Result[Any]:
        """Remove tags from a knowledge unit."""
        body = await request.json()
        tags = body.get("tags", [])

        return await ku_service.remove_knowledge_tags(uid, tags)

    # Knowledge Search and Discovery
    # -------------------------------

    @rt("/api/knowledge/search")
    @boundary_handler()
    async def search_knowledge_units_route(request: Request) -> Result[Any]:
        """Search knowledge units by content, title, or tags."""
        params = dict(request.query_params)
        query = params.get("q", "")
        # Note: search_type param not supported by KuService - searches all by default
        limit = int(params.get("limit", 50))

        return await ku_service.search_knowledge_units(query, limit)

    @rt("/api/knowledge/related")
    @boundary_handler()
    async def find_related_knowledge_route(request: Request, uid: str) -> Result[Any]:
        """Find knowledge units related to the given unit."""
        params = dict(request.query_params)
        similarity_threshold = float(params.get("threshold", 0.7))
        limit = int(params.get("limit", 10))

        return await ku_service.find_related_knowledge(uid, similarity_threshold, limit)

    @rt("/api/knowledge/recommendations")
    @boundary_handler()
    async def get_knowledge_recommendations_route(request: Request, uid: str) -> Result[Any]:
        """Get personalized knowledge recommendations."""
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        recommendation_type = params.get("type", "learning")

        return await ku_service.get_knowledge_recommendations(uid, user_uid, recommendation_type)

    # Knowledge Organization
    # ----------------------

    @rt("/api/knowledge/domains")
    @boundary_handler()
    async def list_knowledge_domains_route(_request: Request) -> Result[Any]:
        """List all knowledge domains."""
        return await ku_service.list_knowledge_domains()

    @rt("/api/knowledge/by-domain")
    @boundary_handler()
    async def get_knowledge_by_domain_route(request: Request, domain: str) -> Result[Any]:
        """Get knowledge units in a specific domain."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 100))

        return await ku_service.get_knowledge_by_domain(domain, limit)

    @rt("/api/knowledge/categories")
    @boundary_handler()
    async def list_knowledge_categories_route(_request: Request) -> Result[Any]:
        """List all knowledge categories."""
        return await ku_service.list_knowledge_categories()

    @rt("/api/knowledge/tags")
    @boundary_handler()
    async def list_knowledge_tags_route(request: Request) -> Result[Any]:
        """List all knowledge tags with usage counts."""
        params = dict(request.query_params)
        min_usage = int(params.get("min_usage", 1))

        return await ku_service.list_knowledge_tags(min_usage)

    # Knowledge Analytics
    # -------------------

    @rt("/api/knowledge/stats")
    @boundary_handler()
    async def get_knowledge_stats_route(request: Request, uid: str) -> Result[Any]:
        """Get statistics for a knowledge unit."""
        return await ku_service.get_knowledge_stats(uid)

    # ========================================================================
    # USER CONTEXT ROUTES - KU-Activity Integration (January 2026)
    # ========================================================================

    @rt("/api/knowledge/my-context")
    @boundary_handler()
    async def get_knowledge_user_context_route(request: Request, uid: str) -> Result[Any]:
        """
        Get personalized context for how the current user uses this knowledge.

        Returns per-user substance score, activity breakdown, and recommendations
        for deepening knowledge application.

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
        if not ku_service.user_service:
            return Result.fail(
                Errors.system(
                    message="User service not available",
                    operation="get_knowledge_user_context",
                )
            )

        context_result = await ku_service.user_service.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value
        return await ku_service.get_user_knowledge_context(uid, user_context)

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    # Analytics handler functions
    async def handle_summary_analytics(service, params):
        """Handle summary analytics for all knowledge."""
        time_period = params.get("period", "month")
        return await service.get_knowledge_summary_analytics(time_period)

    async def handle_graph_structure(service, params):
        """Handle knowledge graph structure and metrics."""
        include_metrics = params.get("metrics", "true").lower() == "true"
        return await service.get_knowledge_graph_structure(include_metrics)

    # Create analytics factory
    analytics_factory = AnalyticsRouteFactory(
        service=ku_service,
        domain_name="knowledge",
        analytics_config={
            "summary": {
                "path": "/api/knowledge/analytics/summary",
                "handler": handle_summary_analytics,
                "description": "Get summary analytics for all knowledge",
                "methods": ["GET"],
            },
            "graph_structure": {
                "path": "/api/knowledge/graph/structure",
                "handler": handle_graph_structure,
                "description": "Get knowledge graph structure and metrics",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    return []  # Routes registered via @rt() decorators (no objects returned)


# Migration Statistics:
# =====================
# Phase 1 - CRUD Factory Migration:
# Before (knowledge_api.py):     327 lines
# After (CRUD factory):          ~270 lines
# CRUD Reduction:                57 lines (17% reduction via CRUDRouteFactory)
#
# Phase 2 - Analytics Factory Migration:
# Analytics endpoints migrated:  2 (summary, graph structure)
# Analytics before:              ~26 lines (13 lines × 2 endpoints)
# Analytics after:               ~20 lines (handlers + factory config)
# Analytics Reduction:           ~6 lines (23% reduction via AnalyticsRouteFactory)
#
# Total Reduction:               ~63 lines (19% overall reduction)
#
# Factory usage:
# - CRUDRouteFactory:     5 standard CRUD routes
# - AnalyticsRouteFactory: 2 analytics endpoints
# - Manual routes:        17 domain-specific routes
