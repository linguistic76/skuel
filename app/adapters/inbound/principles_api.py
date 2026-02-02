"""
Principles API - Migrated to CRUDRouteFactory
==============================================

Fifth migration in Phase 1 CRUD API rollout.

Before: 268 lines of manual route definitions
After: ~215 lines

This file uses:
- CRUDRouteFactory for standard CRUD routes (create, get, update, delete, list)
- Manual routes for domain-specific operations (expressions, alignment, links, search)
"""

from typing import Any

from fasthtml.common import Request

from core.auth import require_authenticated_user, require_ownership_query
from core.infrastructure.routes import CRUDRouteFactory, IntelligenceRouteFactory
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory
from core.models.enums import ContentScope
from core.models.principle.principle_request import (
    AlignmentAssessmentRequest,
    PrincipleCreateRequest,
    PrincipleExpressionRequest,
    PrincipleLinkRequest,
    PrincipleUpdateRequest,
)
from core.services.conversion_service import ConversionService
from core.services.protocols.facade_protocols import PrinciplesFacadeProtocol
from core.utils.error_boundary import boundary_handler
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

conversion_service = ConversionService()


def create_principles_api_routes(
    app: Any,
    rt: Any,
    principles_service: PrinciplesFacadeProtocol,
    user_service: Any = None,
    goals_service: Any = None,
    habits_service: Any = None,
) -> list[Any]:
    """
    Create principles API routes using factory pattern.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        principles_service: PrinciplesService instance
        user_service: UserService for admin role verification
        goals_service: GoalsService for goal ownership verification
        habits_service: HabitsService for habit ownership verification
    """

    # Service getter for ownership decorator (SKUEL012: named function, not lambda)
    def get_principles_service():
        return principles_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for standard CRUD operations
    crud_factory = CRUDRouteFactory(
        service=principles_service,
        domain_name="principles",
        create_schema=PrincipleCreateRequest,
        update_schema=PrincipleUpdateRequest,
        uid_prefix="principle",
        scope=ContentScope.USER_OWNED,
    )

    # Register all standard CRUD routes:
    # - POST   /api/principles           (create)
    # - GET    /api/principles/{uid}     (get)
    # - PUT    /api/principles/{uid}     (update)
    # - DELETE /api/principles/{uid}     (delete)
    # - GET    /api/principles           (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # COMMON QUERY ROUTES (Factory-Generated)
    # ========================================================================

    # Create factory for common query patterns
    query_factory = CommonQueryRouteFactory(
        service=principles_service,
        domain_name="principles",
        user_service=user_service,  # For admin /user route
        goals_service=goals_service,  # For goal ownership verification
        habits_service=habits_service,  # For habit ownership verification
        supports_goal_filter=True,  # Graph query: (goal)-[:GUIDED_BY_PRINCIPLE]->(principle)
        supports_habit_filter=True,  # Graph query: (habit)-[:ALIGNED_WITH_PRINCIPLE]->(principle)
        scope=ContentScope.USER_OWNED,
    )

    # Register common query routes:
    # - GET /api/principles/mine               (get authenticated user's principles)
    # - GET /api/principles/user?user_uid=...  (admin only - get any user's principles)
    # - GET /api/principles/goal?goal_uid=...  (get principles for goal, ownership verified)
    # - GET /api/principles/habit?habit_uid=...  (get principles for habit, ownership verified)
    # - GET /api/principles/by-status?status=...  (filter by status, auth required)
    query_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=principles_service.intelligence,
        domain_name="principles",
        ownership_service=principles_service,
        scope=ContentScope.USER_OWNED,
    )

    # Register intelligence routes:
    # - GET /api/principles/context?uid=...&depth=2     (entity with graph context)
    # - GET /api/principles/analytics?period_days=30   (user performance analytics)
    # - GET /api/principles/insights?uid=...           (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================
    # SECURITY: All UID-based routes verify user owns the principle before operating

    # NOTE: GET /api/principles/user/{user_uid} now generated by CommonQueryRouteFactory

    # Principle Expressions and Alignment
    # ------------------------------------

    @rt("/api/principles/expressions", methods=["POST"])
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler(success_status=201)
    async def create_principle_expression_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Create a principle expression (requires ownership)."""
        body = await request.json()
        data = PrincipleExpressionRequest.model_validate(body)

        expression_uid = UIDGenerator.generate_uid("expression", data.context[:50])
        dto = conversion_service.principle_expression_to_dto(expression_uid, entity.uid, data)

        return await principles_service.create_principle_expression(dto)

    @rt("/api/principles/expressions")
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler()
    async def get_principle_expressions_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get all expressions for a principle (requires ownership)."""
        return await principles_service.get_principle_expressions(entity.uid)

    @rt("/api/principles/alignment", methods=["POST"])
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler()
    async def assess_principle_alignment_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """
        Assess alignment with a principle (requires ownership).

        Implements SKUEL's dual-track philosophy:
        - Stores user's self-assessment (what they believe)
        - Calculates system alignment (what they do)
        - Returns gap analysis (perception vs reality)

        Returns PrincipleAlignmentAssessmentResult containing both tracks.
        """
        body = await request.json()
        data = AlignmentAssessmentRequest.model_validate(body)

        # Extract min_confidence from request if provided, otherwise use default
        min_confidence = getattr(data, "min_confidence", 0.7)

        # Use hybrid dual-track assessment: store user input AND calculate system alignment
        result: Result[Any] = await principles_service.alignment.assess_with_user_input(
            principle_uid=entity.uid,
            user_uid=user_uid,
            user_alignment_level=data.alignment_level,
            user_evidence=data.evidence,
            user_reflection=data.reflection,
            min_confidence=min_confidence,
        )
        return result

    @rt("/api/principles/alignment-history")
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler()
    async def get_principle_alignment_history_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get alignment history for a principle (requires ownership)."""
        params = dict(request.query_params)
        limit = int(params.get("limit", 20))
        days = int(params.get("days", 30))

        return await principles_service.get_principle_alignment_history(entity.uid, limit, days)

    # Principle Relationships and Linking
    # ------------------------------------
    # SECURITY: All routes verify user owns the principle before operating

    @rt("/api/principles/links", methods=["POST"])
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler(success_status=201)
    async def create_principle_link_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Create a link between principles (requires ownership)."""
        body = await request.json()
        data = PrincipleLinkRequest.model_validate(body)

        link_uid = UIDGenerator.generate_uid("link", f"{entity.uid}-{data.uid}")
        dto = conversion_service.principle_link_to_dto(link_uid, entity.uid, data)

        return await principles_service.create_principle_link(dto)

    @rt("/api/principles/links")
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler()
    async def get_principle_links_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get all links for a principle (requires ownership)."""
        params = dict(request.query_params)
        link_type = params.get("type")

        return await principles_service.get_principle_links(entity.uid, link_type)

    @rt("/api/principles/related")
    @require_ownership_query(get_principles_service, uid_param="principle_uid")
    @boundary_handler()
    async def get_related_principles_route(
        request: Request, user_uid: str, entity: Any
    ) -> Result[Any]:
        """Get related principles based on connections (requires ownership)."""
        params = dict(request.query_params)
        depth = int(params.get("depth", 2))
        limit = int(params.get("limit", 10))

        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = principles_service
        return await typed_service.get_related_principles(entity.uid, depth, limit)

    # Principle Search and Discovery
    # -------------------------------

    @rt("/api/principles/search")
    @boundary_handler()
    async def search_principles_route(request: Request) -> Result[Any]:
        """Search principles by content and metadata."""
        body = await request.json()
        query = body.get("query", "")
        filters = body.get("filters", {})
        limit = body.get("limit", 20)

        return await principles_service.search_principles(query, filters, limit)

    @rt("/api/principles/categories")
    @boundary_handler()
    async def get_principle_categories_route(request: Request) -> Result[Any]:
        """Get principle categories for the authenticated user."""
        user_uid = require_authenticated_user(request)
        # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
        typed_service = principles_service
        return await typed_service.get_principle_categories(user_uid)

    @rt("/api/principles/sources")
    @boundary_handler()
    async def get_principle_sources_route(_request: Request) -> Result[Any]:
        """Get all principle sources with counts."""
        return await principles_service.get_principle_sources()

    # ========================================================================
    # ANALYTICS ROUTES (Factory-Generated)
    # ========================================================================

    # Analytics handler functions
    async def handle_principles_stats(service, params):
        """Handle principles statistics and summary."""
        user_uid = params.get("user_uid", "current_user")
        return await service.get_principles_stats(user_uid)

    # Create analytics factory
    analytics_factory = AnalyticsRouteFactory(
        service=principles_service,
        domain_name="principles",
        analytics_config={
            "stats": {
                "path": "/api/principles/stats",
                "handler": handle_principles_stats,
                "description": "Get principles statistics and summary",
                "methods": ["GET"],
            }
        },
    )
    analytics_factory.register_routes(app, rt)

    return []  # Routes registered via @rt() decorators (no objects returned)


# Migration Statistics:
# =====================
# Phase 1 - CRUD Factory Migration:
# Before (principles_api.py):    268 lines
# After (CRUD factory):          ~215 lines
# CRUD Reduction:                53 lines (20% reduction via CRUDRouteFactory)
#
# Phase 2 - Analytics Factory Migration:
# Analytics endpoints migrated:  1 (stats)
# Analytics before:              ~9 lines (9 lines × 1 endpoint)
# Analytics after:               ~8 lines (handler + factory config)
# Analytics Reduction:           ~1 line (11% reduction via AnalyticsRouteFactory)
#
# Total Reduction:               ~54 lines (20% overall reduction)
#
# Factory usage:
# - CRUDRouteFactory:     5 standard CRUD routes
# - AnalyticsRouteFactory: 1 analytics endpoint
# - Manual routes:        11 domain-specific routes
