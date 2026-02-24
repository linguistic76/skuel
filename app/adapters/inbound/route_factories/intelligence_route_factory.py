"""
Intelligence Route Factory - Generic Intelligence API Generation
=================================================================

Consolidates overlapping patterns across 10 intelligence API files (15,000+ lines).

Core Principle: "One factory for intelligence routes, zero duplication"

Common Intelligence Patterns (Based on Analysis of 7 Intelligence Services):
- get_with_context(uid, depth=2) - 5/7 services implement this
- get_performance_analytics(user_uid, period_days=30) - 5/7 services implement this
- get_domain_insights(uid, min_confidence=0.7) - Maps to progress dashboards

Protocol Design (January 2026 - Option A):
- 3 methods that match actual service implementations
- High adoption potential: 5/7 services can implement with minimal changes
- Clear separation: entity context vs user analytics vs entity insights

Security (January 2026):
- verify_ownership flag for Activity Domains (user-owned entities)
- Shared content (KU, LP, MOC) can disable ownership verification
- Returns 404 (not 403) to prevent UID enumeration attacks

Usage:
    # Activity Domain (user-owned) - verify ownership by default
    factory = IntelligenceRouteFactory(
        intelligence_service=goals_intelligence_service,
        domain_name="goals",
        ownership_service=goals_service,  # Service with verify_ownership method
    )
    factory.register_routes(app, rt)

    # Curriculum Domain (shared content) - disable ownership verification
    factory = IntelligenceRouteFactory(
        intelligence_service=ku_intelligence_service,
        domain_name="knowledge",
        verify_ownership=False,  # Shared content, no ownership
    )
    factory.register_routes(app, rt)

Benefits:
    - Eliminates ~900 lines per intelligence API x 10 files = 9,000 lines
    - Consistent intelligence behavior across all domains
    - Single source of truth for intelligence patterns
    - Protocol matches actual service implementations
    - Secure by default for user-owned entities
"""

from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.type_converters import to_dict

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext

logger = get_logger(__name__)

T = TypeVar("T")


# ============================================================================
# PROTOCOLS
# ============================================================================


class OwnershipVerifier(Protocol):
    """
    Protocol for services that can verify entity ownership.

    Used by IntelligenceRouteFactory to verify that the authenticated user
    owns the entity before returning context or insights.

    Security: Returns NotFound (404) instead of Forbidden (403) to prevent
    UID enumeration attacks.
    """

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[Any]:
        """
        Verify that user owns the entity.

        Args:
            uid: Entity UID
            user_uid: User UID to verify ownership against

        Returns:
            Result containing entity if owned, NotFound error otherwise
        """
        ...


class IntelligenceOperations(Protocol[T]):
    """
    Protocol for services implementing intelligence operations.

    Based on analysis of 7 intelligence services (January 2026):
    - get_with_context: 5/7 services (Goals, Habits, Events, Choices, Principles)
    - get_performance_analytics: 5/7 services (Tasks, Goals, Habits, Events, KU)
    - get_domain_insights: Maps to progress dashboards in most services

    Services can implement additional domain-specific methods; this protocol
    defines the common interface for generic route generation.
    """

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, "GraphContext"]]:
        """
        Get entity with full graph context.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (entity, GraphContext) tuple
        """
        ...

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get performance analytics for user.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict
        """
        ...

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for entity.

        Args:
            uid: Entity UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        ...


# ============================================================================
# INTELLIGENCE ROUTE FACTORY
# ============================================================================


class IntelligenceRouteFactory:
    """
    Generic intelligence API factory for analytics, context, and insights.

    Based on analysis of 7 intelligence services (January 2026):
    - get_with_context: 5/7 services (Goals, Habits, Events, Choices, Principles)
    - get_performance_analytics: 5/7 services (Tasks, Goals, Habits, Events, KU)
    - get_domain_insights: Maps to progress dashboards in most services

    Security (January 2026):
    - verify_ownership: When True (default), verifies user owns the entity
    - ownership_service: Service with verify_ownership(uid, user_uid) method
    - Activity Domains should enable ownership verification
    - Curriculum Domains (shared content) can disable it

    Example:
        # Activity Domain with ownership verification
        factory = IntelligenceRouteFactory(
            intelligence_service=goals_intelligence_service,
            domain_name="goals",
            ownership_service=goals_service,
        )
        factory.register_routes(app, rt)

        # Curriculum Domain without ownership verification
        factory = IntelligenceRouteFactory(
            intelligence_service=ku_intelligence_service,
            domain_name="knowledge",
            verify_ownership=False,
        )
        factory.register_routes(app, rt)

    Generates routes:
        - GET  /api/{domain}/analytics    -> get_performance_analytics(user_uid)
        - GET  /api/{domain}/context      -> get_with_context(uid) [+ ownership check]
        - GET  /api/{domain}/insights     -> get_domain_insights(uid) [+ ownership check]
    """

    def __init__(
        self,
        intelligence_service: IntelligenceOperations,
        domain_name: str,
        base_path: str | None = None,
        enable_analytics: bool = True,
        enable_context: bool = True,
        enable_insights: bool = True,
        scope: ContentScope = ContentScope.USER_OWNED,
        ownership_service: OwnershipVerifier | None = None,
    ) -> None:
        """
        Initialize intelligence route factory.

        Args:
            intelligence_service: Service implementing IntelligenceOperations
            domain_name: Domain name (e.g., "habits", "tasks", "goals")
            base_path: Custom base path (default: /api/{domain})
            enable_analytics: Enable analytics route (default: True)
            enable_context: Enable context route (default: True)
            enable_insights: Enable insights route (default: True)
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (no ownership checks)
            ownership_service: Service with verify_ownership method (required if scope=USER_OWNED)
        """
        self.service = intelligence_service
        self.domain = domain_name
        self.base_path = base_path or f"/api/{domain_name}"

        # Feature flags
        self.enable_analytics = enable_analytics
        self.enable_context = enable_context
        self.enable_insights = enable_insights

        # Ownership verification (January 2026 security fix)
        # Convert ContentScope enum to boolean for internal use
        self.verify_ownership = scope == ContentScope.USER_OWNED
        self.ownership_service = ownership_service

        # Warn if ownership verification is enabled but no service provided
        if self.verify_ownership and self.ownership_service is None:
            logger.warning(
                f"IntelligenceRouteFactory for {domain_name}: scope=USER_OWNED but "
                f"no ownership_service provided. Context/insights routes will skip ownership checks."
            )

        logger.info(f"IntelligenceRouteFactory initialized for {domain_name} (scope={scope.value})")

    def register_routes(self, _app, rt):
        """
        Register all intelligence routes.

        Args:
            app: FastHTML application instance
            rt: Route decorator

        Registers (based on feature flags):
            - Analytics route: GET /analytics -> get_performance_analytics(user_uid)
            - Context route: GET /context?uid=... -> get_with_context(uid)
            - Insights route: GET /insights?uid=... -> get_domain_insights(uid)
        """
        if self.enable_analytics:
            self._register_analytics_route(rt)

        if self.enable_context:
            self._register_context_route(rt)

        if self.enable_insights:
            self._register_insights_route(rt)

        logger.info(f"Intelligence routes registered for {self.domain} at {self.base_path}")

    def _register_analytics_route(self, rt) -> Any:
        """
        Register analytics route: GET /api/{domain}/analytics

        Maps to: IntelligenceOperations.get_performance_analytics(user_uid, period_days)

        Authentication: Session-based (raises 401 if not logged in)
        Query params: period_days (optional, default: 30)
        """
        service = self.service
        domain = self.domain

        @rt(f"{self.base_path}/analytics", methods=["GET"])
        @boundary_handler()
        async def analytics_route(request, period_days: int = 30) -> Result[Any]:
            """Get performance analytics for authenticated user"""
            user_uid = require_authenticated_user(request)

            result = await service.get_performance_analytics(user_uid, period_days)

            logger.debug(f"Analytics retrieved for {domain}: user={user_uid}, period={period_days}")
            return result

        return analytics_route

    def _register_context_route(self, rt) -> Any:
        """
        Register context route: GET /api/{domain}/context?uid=...

        Maps to: IntelligenceOperations.get_with_context(uid, depth)

        Authentication: Session-based (raises 401 if not logged in)
        Ownership: Verified if verify_ownership=True and ownership_service provided
        Query params: uid (required), depth (optional, default: 2)
        """
        service = self.service
        domain = self.domain
        factory = self  # Capture for closure

        @rt(f"{self.base_path}/context", methods=["GET"])
        @boundary_handler()
        async def context_route(request, uid: str, depth: int = 2) -> Result[Any]:
            """Get entity with full graph context"""
            user_uid = require_authenticated_user(request)

            # Verify ownership (returns 404 to prevent UID enumeration)
            if factory.verify_ownership and factory.ownership_service:
                ownership_error = await verify_entity_ownership(
                    factory.ownership_service, uid, user_uid, factory.domain
                )
                if ownership_error:
                    return ownership_error

            result = await service.get_with_context(uid, depth)

            # Transform tuple result to dict for JSON serialization
            if result.is_ok and result.value:
                entity, graph_context = result.value

                # Serialize entity using protocol-based to_dict()
                entity_data = to_dict(entity)

                logger.debug(
                    f"Context retrieved for {domain}: uid={uid}, user={user_uid}, depth={depth}"
                )
                return Result.ok(
                    {
                        "entity": entity_data,
                        "context": graph_context.get_summary() if graph_context else None,
                    }
                )

            return result

        return context_route

    def _register_insights_route(self, rt) -> Any:
        """
        Register insights route: GET /api/{domain}/insights?uid=...

        Maps to: IntelligenceOperations.get_domain_insights(uid, min_confidence)

        Authentication: Session-based (raises 401 if not logged in)
        Ownership: Verified if verify_ownership=True and ownership_service provided
        Query params: uid (required), min_confidence (optional, default: 0.7)
        """
        service = self.service
        domain = self.domain
        factory = self  # Capture for closure

        @rt(f"{self.base_path}/insights", methods=["GET"])
        @boundary_handler()
        async def insights_route(request, uid: str, min_confidence: float = 0.7) -> Result[Any]:
            """Get domain-specific insights for entity"""
            user_uid = require_authenticated_user(request)

            # Verify ownership (returns 404 to prevent UID enumeration)
            if factory.verify_ownership and factory.ownership_service:
                ownership_error = await verify_entity_ownership(
                    factory.ownership_service, uid, user_uid, factory.domain
                )
                if ownership_error:
                    return ownership_error

            result = await service.get_domain_insights(uid, min_confidence)

            logger.debug(
                f"Insights retrieved for {domain}: uid={uid}, user={user_uid}, min_confidence={min_confidence}"
            )
            return result

        return insights_route


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "IntelligenceOperations",
    "IntelligenceRouteFactory",
    "OwnershipVerifier",
]
