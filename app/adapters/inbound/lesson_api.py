"""
Lesson API - Migrated to CRUDRouteFactory
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
from core.models.entity_requests import AddTagsRequest, EntityUpdateRequest, RemoveTagsRequest
from core.models.enums import ContentScope
from core.models.enums.user_enums import UserRole
from core.models.lesson.lesson_request import (
    LessonContentUpdateRequest,
    LessonCreateRequest,
    LessonRelationshipCreateRequest,
)
from core.services.lesson_service import LessonService
from core.utils.result_simplified import Errors, Result
from ui.feedback import Alert, AlertT


def create_lesson_api_routes(
    app: Any, rt: Any, lesson_service: LessonService, user_service: Any = None
) -> list[Any]:
    """
    Create Lesson API routes using factory pattern.

    SECURITY: CRUD write operations (create, update, delete) require ADMIN role.
    Read operations (get, list) are public.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        lesson_service: Lesson service instance
        user_service: User service for admin role verification
    """

    def user_service_getter():
        return user_service

    # ========================================================================
    # STANDARD CRUD ROUTES (Factory-Generated, Admin-Gated Writes)
    # ========================================================================

    crud_factory = CRUDRouteFactory(
        service=lesson_service,
        domain_name="lesson",
        create_schema=LessonCreateRequest,
        update_schema=EntityUpdateRequest,
        uid_prefix="l",
        scope=ContentScope.SHARED,
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )

    # Register all standard CRUD routes:
    # - POST /api/lesson (create)
    # - GET /api/lesson/{uid} (get)
    # - PUT /api/lesson/{uid} (update)
    # - DELETE /api/lesson/{uid} (delete)
    # - GET /api/lesson (list with pagination)
    crud_factory.register_routes(app, rt)

    # ========================================================================
    # INTELLIGENCE ROUTES (Factory-Generated)
    # ========================================================================

    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=lesson_service.intelligence,
        domain_name="lesson",
        scope=ContentScope.SHARED,  # Curriculum content is shared
    )

    # Register intelligence routes:
    # - GET /api/lesson/context?uid=...&depth=2 (entity with graph context)
    # - GET /api/lesson/analytics?period_days=30 (user performance analytics)
    # - GET /api/lesson/insights?uid=... (domain-specific insights)
    intelligence_factory.register_routes(app, rt)

    # ========================================================================
    # DOMAIN-SPECIFIC ROUTES (Manual)
    # ========================================================================

    # Lesson Relationships
    # ---------------------

    @rt("/api/lesson/relationships", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def create_lesson_relationship_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Create a relationship between lessons. Requires ADMIN role."""
        body = await request.json()
        try:
            req = LessonRelationshipCreateRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await lesson_service.create_lesson_relationship(
            uid, req.target_uid, req.type, req.strength, req.description
        )

    @rt("/api/lesson/relationships", methods=["GET"])
    @boundary_handler()
    async def get_lesson_relationships_route(request: Request, uid: str) -> Result[Any]:
        """Get relationships for a lesson."""
        params = dict(request.query_params)
        relationship_type = params.get("type")
        # Note: direction param not supported by LessonService - ignoring for now

        return await lesson_service.get_lesson_relationships(uid, relationship_type)

    @rt("/api/lesson/prerequisites")
    @boundary_handler()
    async def get_lesson_prerequisites_route(request: Request, uid: str) -> Result[Any]:
        """Get prerequisites for a lesson."""
        return await lesson_service.get_lesson_prerequisites(uid)

    @rt("/api/lesson/dependencies")
    @boundary_handler()
    async def get_lesson_dependencies_route(request: Request, uid: str) -> Result[Any]:
        """Get what depends on this lesson."""
        return await lesson_service.get_lesson_dependencies(uid)

    # Curriculum Content Operations
    # ---------------------

    @rt("/api/lesson/content", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def update_lesson_content_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Update lesson content. Requires ADMIN role."""
        body = await request.json()
        try:
            req = LessonContentUpdateRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await lesson_service.update_lesson_content(uid, req.content, req.title)

    @rt("/api/lesson/tags", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def add_lesson_tags_route(request: Request, current_user: Any, uid: str) -> Result[Any]:
        """Add tags to a lesson. Requires ADMIN role."""
        body = await request.json()
        try:
            req = AddTagsRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await lesson_service.add_lesson_tags(uid, req.tags)

    @rt("/api/lesson/tags", methods=["DELETE"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def remove_lesson_tags_route(
        request: Request, current_user: Any, uid: str
    ) -> Result[Any]:
        """Remove tags from a lesson. Requires ADMIN role."""
        body = await request.json()
        try:
            req = RemoveTagsRequest(**body)
        except ValidationError as e:
            return Result.fail(Errors.validation(str(e), field="body"))

        return await lesson_service.remove_lesson_tags(uid, req.tags)

    # Lesson Search and Discovery
    # ----------------------------

    @rt("/api/lesson/search")
    @boundary_handler()
    async def search_lesson_route(request: Request) -> Result[Any]:
        """Search lessons by content, title, or tags."""
        params = dict(request.query_params)
        query = params.get("q", "")
        # Note: search_type param not supported by LessonService - searches all by default
        limit = parse_int_query_param(params, "limit", 50, minimum=1, maximum=100)

        return await lesson_service.search_lessons(query, limit)

    @rt("/api/lesson/related")
    @boundary_handler()
    async def find_related_lesson_route(request: Request, uid: str) -> Result[Any]:
        """Find lessons related to the given one."""
        params = dict(request.query_params)
        similarity_threshold = float(params.get("threshold", 0.7))
        limit = parse_int_query_param(params, "limit", 10, minimum=1, maximum=500)

        return await lesson_service.find_related_lessons(uid, similarity_threshold, limit)

    @rt("/api/lesson/recommendations")
    @boundary_handler()
    async def get_lesson_recommendations_route(request: Request, uid: str) -> Result[Any]:
        """Get personalized lesson recommendations."""
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        recommendation_type = params.get("type", "learning")

        return await lesson_service.get_lesson_recommendations(uid, user_uid, recommendation_type)

    # Lesson Organization
    # --------------------

    @rt("/api/lesson/domains")
    @boundary_handler()
    async def list_lesson_domains_route(_request: Request) -> Result[Any]:
        """List all lesson domains."""
        return await lesson_service.list_lesson_domains()

    @rt("/api/lesson/by-domain")
    @boundary_handler()
    async def get_lesson_by_domain_route(request: Request, domain: str) -> Result[Any]:
        """Get lessons in a specific domain."""
        params = dict(request.query_params)
        limit = parse_int_query_param(params, "limit", 100, minimum=1, maximum=500)

        return await lesson_service.get_lessons_by_domain(domain, limit)

    @rt("/api/lesson/categories")
    @boundary_handler()
    async def list_lesson_categories_route(_request: Request) -> Result[Any]:
        """List all lesson categories."""
        return await lesson_service.list_lesson_categories()

    @rt("/api/lesson/tags")
    @boundary_handler()
    async def list_lesson_tags_route(request: Request) -> Result[Any]:
        """List all lesson tags with usage counts."""
        params = dict(request.query_params)
        min_usage = parse_int_query_param(params, "min_usage", 1, minimum=0)

        return await lesson_service.list_lesson_tags(min_usage)

    # Lesson Analytics
    # -----------------

    @rt("/api/lesson/stats")
    @boundary_handler()
    async def get_lesson_stats_route(request: Request, uid: str) -> Result[Any]:
        """Get statistics for a lesson."""
        return await lesson_service.get_lesson_stats(uid)

    # ========================================================================
    # USER CONTEXT ROUTES - Lesson-Activity Integration (January 2026)
    # ========================================================================

    @rt("/api/lesson/my-context")
    @boundary_handler()
    async def get_lesson_user_context_route(request: Request, uid: str) -> Result[Any]:
        """
        Get personalized context for how the current user uses this lesson.

        Returns per-user substance score, activity breakdown, and recommendations
        for deepening lesson application.

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
        if not lesson_service.user_service:
            return Result.fail(
                Errors.system(
                    message="User service not available",
                    operation="get_lesson_user_context",
                )
            )

        context_result = await lesson_service.user_service.get_user_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        user_context = context_result.value
        return await lesson_service.get_user_lesson_context(uid, user_context)

    # ========================================================================
    # ADAPTIVE CURRICULUM ROUTES (absorbed from SEL)
    # ========================================================================

    @rt("/api/lesson/journey")
    @boundary_handler()
    async def get_lesson_journey(request: Request) -> Result[Any]:
        """Get user's SEL learning journey — progress across all 5 categories."""
        user_uid = require_authenticated_user(request)
        return await lesson_service.get_sel_journey(user_uid)

    @rt("/api/lesson/curriculum/{category}")
    @boundary_handler()
    async def get_personalized_curriculum(
        request: Request, category: str, limit: int = 10
    ) -> Result[Any]:
        """Get personalized lesson curriculum for an SEL category."""
        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)
        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Result.fail(Errors.validation(f"Invalid SEL category: {category}"))
        return await lesson_service.get_personalized_curriculum(
            user_uid=user_uid, sel_category=sel_category, limit=limit
        )

    @rt("/api/lesson/journey-html")
    async def get_lesson_journey_html(request: Request) -> Any:
        """HTMX: Render SEL journey as HTML fragment."""
        from fasthtml.common import P

        user_uid = require_authenticated_user(request)
        result = await lesson_service.get_sel_journey(user_uid)

        if result.is_error:
            return Alert(
                P("Unable to load your learning journey.", cls="text-center py-8"),
                variant=AlertT.error,
            )

        from ui.patterns.curriculum_adaptive import SELJourneyOverview

        return SELJourneyOverview(result.value)

    @rt("/api/lesson/curriculum-html/{category}")
    async def get_curriculum_html(request: Request, category: str, limit: int = 10) -> Any:
        """HTMX: Render personalized curriculum grid as HTML fragment."""
        from fasthtml.common import Div, P

        from core.models.enums import SELCategory

        user_uid = require_authenticated_user(request)

        try:
            sel_category = SELCategory(category)
        except ValueError:
            return Alert(P(f"Invalid category: {category}"), variant=AlertT.error)

        result = await lesson_service.get_personalized_curriculum(
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
        """Handle summary analytics for all lessons."""
        time_period = params.get("period", "month")
        return await service.get_lesson_summary_analytics(time_period)

    async def handle_graph_structure(service, params):
        """Handle lesson graph structure and metrics."""
        include_metrics = params.get("metrics", "true").lower() == "true"
        return await service.get_lesson_graph_structure(include_metrics)

    # Create analytics factory
    analytics_factory = AnalyticsRouteFactory(
        service=lesson_service,
        domain_name="lesson",
        analytics_config={
            "summary": {
                "path": "/api/lesson/analytics/summary",
                "handler": handle_summary_analytics,
                "description": "Get summary analytics for all lessons",
                "methods": ["GET"],
            },
            "graph_structure": {
                "path": "/api/lesson/graph/structure",
                "handler": handle_graph_structure,
                "description": "Get lesson graph structure and metrics",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)

    return []  # Routes registered via @rt() decorators (no objects returned)
