"""
Intelligence Route Factory
==========================

One factory registers the intelligence routes of a domain from its analytics
service:

- ``GET {base}/context?uid=``  -> ``get_with_context(uid, depth)``
- ``GET {base}/insights?uid=`` -> ``get_domain_insights(uid, min_confidence)``
- ``GET {base}/analytics``     -> ``get_performance_analytics(user_uid, period_days)``

Context and insights are per-entity reads and exist at either scope. Analytics
is the signed-in user's own aggregate, so it exists for ``ContentScope.USER_OWNED``
alone: shared curriculum has no per-user set to aggregate, and a SHARED factory
registers no ``/analytics`` route.

Ownership: at USER_OWNED the context and insights routes verify that the caller
owns the entity and answer 404 (never 403) for one they do not. SHARED content
is readable by every signed-in user.

Usage:
    # Activity domain (user-owned): three routes, ownership verified
    IntelligenceRouteFactory(
        intelligence_service=goals_service.intelligence,
        domain_name="goals",
        ownership_service=goals_service,
    ).register_routes(app, rt)

    # Curriculum domain (shared): context + insights
    IntelligenceRouteFactory(
        intelligence_service=ps_service.intelligence,
        domain_name="path-steps",
        scope=ContentScope.SHARED,
    ).register_routes(app, rt)

See: /docs/patterns/ROUTE_FACTORIES.md
"""

from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import ContentScope
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext

logger = get_logger(__name__)

T = TypeVar("T")

# What an analytics or insights route answers with. One factory serves each routed
# domain, so the payload's shape varies per domain (a Task's analytics, a PathStep's
# insights): the route-factory erased-T boundary (CLAUDE.md Any policy). A service
# may declare a TypedDict for its own payload; the factory reads none of its keys.
IntelligencePayload = dict[str, Any]  # boundary: route-factory erased-T


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

    async def verify_ownership(
        self, uid: str, user_uid: UserUID
    ) -> Result[Any]:  # boundary: route-factory erased-T — the owned entity, any domain's model
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
    The per-entity reads behind the context and insights routes.

    Every routed analytics service implements both, at either scope. The routes
    pass their arguments positionally.
    """

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[T, GraphContext]]:
        """
        Get entity with full graph context.

        Args:
            uid: Entity UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (entity, GraphContext) tuple
        """
        ...

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[IntelligencePayload]:
        """
        Get domain-specific insights for entity.

        Args:
            uid: Entity UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        ...


class PerformanceAnalyticsOperations(Protocol):
    """
    The per-user aggregate behind the analytics route.

    Implemented by the analytics services of user-owned domains. A service over
    shared content does not implement it, and its factory registers no
    analytics route.
    """

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[IntelligencePayload]:
        """
        Get performance analytics for user.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict
        """
        ...


# ============================================================================
# INTELLIGENCE ROUTE FACTORY
# ============================================================================


class IntelligenceRouteFactory:
    """
    Registers a domain's intelligence routes from its analytics service.

    Generates:
        - GET /api/{domain}/context?uid=   -> get_with_context(uid, depth)
        - GET /api/{domain}/insights?uid=  -> get_domain_insights(uid, min_confidence)
        - GET /api/{domain}/analytics      -> get_performance_analytics(user_uid, period_days)
          (USER_OWNED scope only)

    At USER_OWNED the context and insights routes verify ownership through
    ``ownership_service``; at SHARED they do not, and there is no analytics route.
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
            intelligence_service: Service implementing IntelligenceOperations; at
                USER_OWNED scope with analytics enabled it also implements
                PerformanceAnalyticsOperations
            domain_name: Domain name (e.g., "habits", "tasks", "goals")
            base_path: Custom base path (default: /api/{domain})
            enable_analytics: Register the analytics route (default: True). Read at
                USER_OWNED scope; a SHARED factory has no analytics route to enable
            enable_context: Enable context route (default: True)
            enable_insights: Enable insights route (default: True)
            scope: Content ownership model (default: ContentScope.USER_OWNED).
                  - ContentScope.USER_OWNED: User-specific content with ownership verification
                  - ContentScope.SHARED: Public/shared content (no ownership checks)
            ownership_service: Service with verify_ownership method (required if scope=USER_OWNED)

        Raises:
            ValueError: USER_OWNED without an ownership_service, or USER_OWNED with
                analytics enabled over a service that has no get_performance_analytics.
        """
        self.service = intelligence_service
        self.domain = domain_name
        self.base_path = base_path or f"/api/{domain_name}"

        self.verify_ownership = scope == ContentScope.USER_OWNED
        self.ownership_service = ownership_service

        # Feature flags. Analytics is the caller's own aggregate, so it is a
        # USER_OWNED route whatever the flag says.
        self.enable_analytics = enable_analytics and self.verify_ownership
        self.enable_context = enable_context
        self.enable_insights = enable_insights

        # A USER_OWNED factory with no ownership service cannot verify ownership
        # on its context/insights routes, so it refuses to construct (ADR-085).
        if self.verify_ownership and self.ownership_service is None:
            raise ValueError(
                f"IntelligenceRouteFactory for {domain_name}: scope=USER_OWNED requires "
                f"an ownership_service — without it the context/insights routes cannot "
                f"verify ownership. Pass ownership_service, or declare "
                f"scope=ContentScope.SHARED for shared content."
            )

        # Presence is read by attribute, so a stand-in service is judged by what
        # it answers to: scripts/health/route_catalog.py wires this tree over mocks.
        self.analytics_service: PerformanceAnalyticsOperations | None = None
        if self.enable_analytics:
            if getattr(intelligence_service, "get_performance_analytics", None) is None:
                raise ValueError(
                    f"IntelligenceRouteFactory for {domain_name}: the analytics route needs "
                    f"get_performance_analytics, which "
                    f"{type(intelligence_service).__name__} does not implement. Implement "
                    f"it, pass enable_analytics=False, or declare "
                    f"scope=ContentScope.SHARED for shared content."
                )
            self.analytics_service = cast("PerformanceAnalyticsOperations", intelligence_service)

        logger.info(f"IntelligenceRouteFactory initialized for {domain_name} (scope={scope.value})")

    def register_routes(self, _app, rt) -> None:
        """
        Register the intelligence routes.

        Args:
            app: FastHTML application instance
            rt: Route decorator

        Registers (based on scope and feature flags):
            - Analytics route: GET /analytics -> get_performance_analytics(user_uid)
              (USER_OWNED scope only)
            - Context route: GET /context?uid=... -> get_with_context(uid)
            - Insights route: GET /insights?uid=... -> get_domain_insights(uid)
        """
        if self.analytics_service is not None:
            self._register_analytics_route(rt, self.analytics_service)

        if self.enable_context:
            self._register_context_route(rt)

        if self.enable_insights:
            self._register_insights_route(rt)

        logger.info(f"Intelligence routes registered for {self.domain} at {self.base_path}")

    def _register_analytics_route(self, rt, service: PerformanceAnalyticsOperations) -> None:
        """
        Register analytics route: GET /api/{domain}/analytics

        Maps to: PerformanceAnalyticsOperations.get_performance_analytics(user_uid, period_days)

        Authentication: Session-based (raises 401 if not logged in)
        Query params: period_days (optional, default: 30)
        """
        domain = self.domain

        @rt(f"{self.base_path}/analytics", methods=["GET"])
        @boundary_handler()
        async def analytics_route(
            request: Request, period_days: int = 30
        ) -> Result[IntelligencePayload]:
            """Get performance analytics for authenticated user"""
            user_uid = require_authenticated_user(request)

            result = await service.get_performance_analytics(user_uid, period_days)

            logger.debug(f"Analytics retrieved for {domain}: user={user_uid}, period={period_days}")
            return result

    def _register_context_route(self, rt) -> None:
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
        async def context_route(
            request: Request, uid: str, depth: int = 2
        ) -> Result[IntelligencePayload]:
            """Get entity with full graph context"""
            user_uid = require_authenticated_user(request)

            # Verify ownership (returns 404 to prevent UID enumeration).
            # verify_ownership=True implies ownership_service is present — the
            # constructor refuses otherwise; the second conjunct narrows the
            # Optional for typing.
            if factory.verify_ownership and factory.ownership_service:
                ownership_error = await verify_entity_ownership(
                    factory.ownership_service, uid, user_uid, factory.domain
                )
                if ownership_error:
                    return ownership_error

            result = await service.get_with_context(uid, depth)
            if result.is_error:
                return Result.fail(result)
            if not result.value:
                return Result.fail(Errors.not_found(resource=domain, identifier=uid))

            # The boundary serializes the entity, as it does a CRUD read's.
            entity, graph_context = result.value

            logger.debug(
                f"Context retrieved for {domain}: uid={uid}, user={user_uid}, depth={depth}"
            )
            return Result.ok(
                {
                    "entity": entity,
                    "context": graph_context.get_summary() if graph_context else None,
                }
            )

    def _register_insights_route(self, rt) -> None:
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
        async def insights_route(
            request: Request, uid: str, min_confidence: float = 0.7
        ) -> Result[IntelligencePayload]:
            """Get domain-specific insights for entity"""
            user_uid = require_authenticated_user(request)

            # Verify ownership (returns 404 to prevent UID enumeration).
            # verify_ownership=True implies ownership_service is present — the
            # constructor refuses otherwise; the second conjunct narrows the
            # Optional for typing.
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


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    "IntelligenceOperations",
    "IntelligenceRouteFactory",
    "OwnershipVerifier",
    "PerformanceAnalyticsOperations",
]
