"""
Tests for Intelligence Route Factory
====================================

Comprehensive test coverage for generic intelligence route generation.

Updated January 2026 for new 3-method protocol:
- get_with_context(uid, depth) -> Result[tuple[T, GraphContext]]
- get_performance_analytics(user_uid, period_days) -> Result[dict]
- get_domain_insights(uid, min_confidence) -> Result[dict]
"""

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
from starlette.responses import JSONResponse

from core.infrastructure.routes.intelligence_route_factory import (
    IntelligenceRouteFactory,
)
from core.models.enums import ContentScope, Domain
from core.utils.result_simplified import Result

# ============================================================================
# AUTH MOCK - Auto-applied to all tests
# ============================================================================


@pytest.fixture(autouse=True)
def mock_auth():
    """Automatically mock authentication for all tests."""
    with patch(
        "core.infrastructure.routes.intelligence_route_factory.require_authenticated_user"
    ) as mock:
        mock.return_value = "user.test"
        yield mock


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def extract_response(response: JSONResponse) -> tuple[dict, int]:
    """Helper to extract body and status from JSONResponse for testing."""
    body = json.loads(response.body)
    return body, response.status_code


# ============================================================================
# MOCK GRAPH CONTEXT (Simplified for Testing)
# ============================================================================


@dataclass
class MockGraphContext:
    """Mock GraphContext for testing."""

    origin_uid: str
    total_nodes: int = 5
    total_relationships: int = 3
    domains_involved: list = None

    def __post_init__(self):
        if self.domains_involved is None:
            self.domains_involved = [Domain.GOALS]

    def get_summary(self) -> dict[str, Any]:
        """Get concise summary for JSON serialization."""
        return {
            "origin": f"goals:{self.origin_uid}",
            "total_nodes": self.total_nodes,
            "total_relationships": self.total_relationships,
            "domains": [d.value for d in self.domains_involved],
        }


@dataclass
class MockGoal:
    """Mock Goal entity for testing."""

    uid: str
    title: str
    progress: float = 0.0

    def model_dump(self) -> dict[str, Any]:
        """Return dict for JSON serialization."""
        return {
            "uid": self.uid,
            "title": self.title,
            "progress": self.progress,
        }


# ============================================================================
# TEST FIXTURES - Mock Intelligence Service
# ============================================================================


class MockIntelligenceService:
    """Mock service implementing IntelligenceOperations protocol (3-method design)."""

    def __init__(self):
        self.context_calls = []
        self.analytics_calls = []
        self.insights_calls = []

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[MockGoal, MockGraphContext]]:
        """Get entity with full graph context."""
        self.context_calls.append((uid, depth))
        goal = MockGoal(uid=uid, title=f"Goal {uid}", progress=50.0)
        context = MockGraphContext(origin_uid=uid, total_nodes=depth * 3)
        return Result.ok((goal, context))

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """Get performance analytics for user."""
        self.analytics_calls.append((user_uid, period_days))
        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "analytics": {
                    "total_goals": 10,
                    "completed_goals": 7,
                    "success_rate": 0.70,
                    "avg_progress": 65.5,
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """Get domain-specific insights for entity."""
        self.insights_calls.append((uid, min_confidence))
        return Result.ok(
            {
                "uid": uid,
                "min_confidence": min_confidence,
                "insights": {
                    "progress_status": "on_track",
                    "risk_level": "low",
                    "recommendations": [
                        "Continue current pace",
                        "Consider adding supporting habits",
                    ],
                },
                "metrics": {
                    "support_coverage": 0.75,
                    "task_support_count": 5,
                    "habit_support_count": 2,
                },
            }
        )


# ============================================================================
# TEST FIXTURES - Mock Request & Router
# ============================================================================


class MockRequest:
    """Mock Starlette request."""

    def __init__(self, path_params=None, query_params=None, json_data=None):
        self.path_params = path_params or {}
        self.query_params = query_params or {}
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data


class MockRouter:
    """Mock route decorator."""

    def __init__(self):
        self.routes = {}

    def __call__(self, path: str, methods: list[str]):
        def decorator(func):
            self.routes[f"{methods[0]}:{path}"] = func
            return func

        return decorator

    def get_route(self, method: str, path: str):
        """Get registered route handler."""
        return self.routes.get(f"{method}:{path}")


@pytest.fixture
def mock_service() -> MockIntelligenceService:
    """Fixture providing mock intelligence service."""
    return MockIntelligenceService()


@pytest.fixture
def mock_router() -> MockRouter:
    """Fixture providing mock router."""
    return MockRouter()


@pytest.fixture
def intelligence_factory(mock_service) -> IntelligenceRouteFactory:
    """Fixture providing intelligence route factory."""
    return IntelligenceRouteFactory(intelligence_service=mock_service, domain_name="goals")


# ============================================================================
# TESTS - Factory Initialization
# ============================================================================


def test_factory_initialization(intelligence_factory):
    """Test factory initializes with correct parameters."""
    assert intelligence_factory.domain == "goals"
    assert intelligence_factory.base_path == "/api/goals"
    assert intelligence_factory.enable_analytics is True
    assert intelligence_factory.enable_context is True
    assert intelligence_factory.enable_insights is True


def test_factory_custom_base_path(mock_service):
    """Test factory accepts custom base path."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="tasks",
        base_path="/api/v2/tasks/intelligence",
    )
    assert factory.base_path == "/api/v2/tasks/intelligence"


def test_factory_feature_flags(mock_service):
    """Test factory accepts feature flags."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="habits",
        enable_analytics=True,
        enable_context=False,
        enable_insights=True,
    )
    assert factory.enable_analytics is True
    assert factory.enable_context is False
    assert factory.enable_insights is True


# ============================================================================
# TESTS - Route Registration
# ============================================================================


def test_register_routes_all_enabled(intelligence_factory, mock_router):
    """Test all routes registered when all features enabled."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    # Verify all routes registered
    assert "GET:/api/goals/analytics" in mock_router.routes
    assert "GET:/api/goals/context" in mock_router.routes
    assert "GET:/api/goals/insights" in mock_router.routes


def test_register_routes_selective_features(mock_service, mock_router):
    """Test only enabled routes are registered."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="tasks",
        enable_analytics=True,
        enable_context=False,
        enable_insights=True,
    )

    factory.register_routes(_app=None, rt=mock_router)

    # Verify only enabled routes registered
    assert "GET:/api/tasks/analytics" in mock_router.routes
    assert "GET:/api/tasks/context" not in mock_router.routes
    assert "GET:/api/tasks/insights" in mock_router.routes


# ============================================================================
# TESTS - Analytics Route (get_performance_analytics)
# ============================================================================


@pytest.mark.asyncio
async def test_analytics_route_success(intelligence_factory, mock_router, mock_service):
    """Test analytics route with valid parameters."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    analytics_handler = mock_router.get_route("GET", "/api/goals/analytics")
    assert analytics_handler is not None

    # Mock request
    request = MockRequest()

    # Call route handler with period_days as function arg (FastHTML pattern)
    json_response = await analytics_handler(request, period_days=60)
    response, status_code = extract_response(json_response)

    # Verify response
    assert status_code == 200
    assert response["user_uid"] == "user.test"  # From require_authenticated_user mock
    assert response["period_days"] == 60
    assert response["analytics"]["total_goals"] == 10
    assert response["analytics"]["success_rate"] == 0.70

    # Verify service called with correct params
    assert len(mock_service.analytics_calls) == 1
    assert mock_service.analytics_calls[0] == ("user.test", 60)


@pytest.mark.asyncio
async def test_analytics_route_default_period(intelligence_factory, mock_router, mock_service):
    """Test analytics route uses default period_days."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    analytics_handler = mock_router.get_route("GET", "/api/goals/analytics")

    # Mock request - no period_days passed, uses default
    request = MockRequest()

    json_response = await analytics_handler(request)
    response, status_code = extract_response(json_response)

    # Verify default period_days used
    assert status_code == 200
    assert response["period_days"] == 30

    # Verify service called with default
    assert mock_service.analytics_calls[0] == ("user.test", 30)


# ============================================================================
# TESTS - Context Route (get_with_context)
# ============================================================================


@pytest.mark.asyncio
async def test_context_route_success(intelligence_factory, mock_router, mock_service):
    """Test context route retrieves entity with graph context."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    context_handler = mock_router.get_route("GET", "/api/goals/context")
    assert context_handler is not None

    # Mock request
    request = MockRequest()

    # Call route handler with params as function args (FastHTML pattern)
    json_response = await context_handler(request, uid="goal:abc123", depth=3)
    response, status_code = extract_response(json_response)

    # Verify response structure
    assert status_code == 200
    assert "entity" in response
    assert "context" in response
    assert response["context"]["origin"] == "goals:goal:abc123"
    assert response["context"]["total_nodes"] == 9  # depth * 3

    # Verify service called
    assert len(mock_service.context_calls) == 1
    assert mock_service.context_calls[0] == ("goal:abc123", 3)


@pytest.mark.asyncio
async def test_context_route_default_depth(intelligence_factory, mock_router, mock_service):
    """Test context route uses default depth."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    context_handler = mock_router.get_route("GET", "/api/goals/context")

    # Mock request - only uid, depth uses default
    request = MockRequest()

    json_response = await context_handler(request, uid="goal:xyz789")
    response, status_code = extract_response(json_response)

    # Verify default depth used
    assert status_code == 200
    assert response["context"]["total_nodes"] == 6  # default depth=2 * 3

    # Verify service called with default
    assert mock_service.context_calls[0] == ("goal:xyz789", 2)


# ============================================================================
# TESTS - Insights Route (get_domain_insights)
# ============================================================================


@pytest.mark.asyncio
async def test_insights_route_success(intelligence_factory, mock_router, mock_service):
    """Test insights route retrieves domain-specific insights."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    insights_handler = mock_router.get_route("GET", "/api/goals/insights")
    assert insights_handler is not None

    # Mock request
    request = MockRequest()

    # Call route handler with params as function args (FastHTML pattern)
    json_response = await insights_handler(request, uid="goal:def456", min_confidence=0.8)
    response, status_code = extract_response(json_response)

    # Verify response
    assert status_code == 200
    assert response["uid"] == "goal:def456"
    assert response["min_confidence"] == 0.8
    assert response["insights"]["progress_status"] == "on_track"
    assert "recommendations" in response["insights"]
    assert "metrics" in response

    # Verify service called
    assert len(mock_service.insights_calls) == 1
    assert mock_service.insights_calls[0] == ("goal:def456", 0.8)


@pytest.mark.asyncio
async def test_insights_route_default_confidence(intelligence_factory, mock_router, mock_service):
    """Test insights route uses default min_confidence."""
    intelligence_factory.register_routes(_app=None, rt=mock_router)

    insights_handler = mock_router.get_route("GET", "/api/goals/insights")

    # Mock request - only uid, min_confidence uses default
    request = MockRequest()

    json_response = await insights_handler(request, uid="goal:ghi789")
    response, status_code = extract_response(json_response)

    # Verify default min_confidence used
    assert status_code == 200
    assert response["min_confidence"] == 0.7

    # Verify service called with default
    assert mock_service.insights_calls[0] == ("goal:ghi789", 0.7)


# ============================================================================
# TESTS - Protocol Compliance
# ============================================================================


def test_service_implements_intelligence_operations_protocol():
    """Test MockIntelligenceService implements IntelligenceOperations protocol."""
    service = MockIntelligenceService()

    # Protocol check (duck typing) - 3 methods
    assert hasattr(service, "get_with_context")
    assert hasattr(service, "get_performance_analytics")
    assert hasattr(service, "get_domain_insights")


# ============================================================================
# TESTS - Ownership Verification (January 2026 Security Fix)
# ============================================================================


class MockOwnershipService:
    """Mock service implementing OwnershipVerifier protocol."""

    def __init__(self, owned_uids: set | None = None):
        self.owned_uids = owned_uids or {"goal:owned123"}
        self.verify_calls = []

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[MockGoal]:
        """Verify ownership - returns entity if owned, NotFound otherwise."""
        from core.utils.result_simplified import Errors

        self.verify_calls.append((uid, user_uid))
        if uid in self.owned_uids:
            return Result.ok(MockGoal(uid=uid, title=f"Goal {uid}"))
        return Result.fail(Errors.not_found(resource="Goal", identifier=uid))


@pytest.fixture
def mock_ownership_service() -> MockOwnershipService:
    """Fixture providing mock ownership service."""
    return MockOwnershipService()


def test_factory_with_ownership_verification(mock_service, mock_ownership_service):
    """Test factory accepts ownership verification parameters."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="goals",
        scope=ContentScope.USER_OWNED,
        ownership_service=mock_ownership_service,
    )
    assert factory.verify_ownership is True
    assert factory.ownership_service is mock_ownership_service


def test_factory_without_ownership_verification(mock_service):
    """Test factory can disable ownership verification for shared content."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="knowledge",
        scope=ContentScope.SHARED,
    )
    assert factory.verify_ownership is False
    assert factory.ownership_service is None


@pytest.mark.asyncio
async def test_context_route_with_ownership_verification(
    mock_router, mock_service, mock_ownership_service
):
    """Test context route verifies ownership when enabled."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="goals",
        scope=ContentScope.USER_OWNED,
        ownership_service=mock_ownership_service,
    )
    factory.register_routes(_app=None, rt=mock_router)

    context_handler = mock_router.get_route("GET", "/api/goals/context")
    request = MockRequest()

    # Request owned entity - should succeed
    json_response = await context_handler(request, uid="goal:owned123")
    response, status_code = extract_response(json_response)

    assert status_code == 200
    assert "entity" in response
    assert len(mock_ownership_service.verify_calls) == 1
    assert mock_ownership_service.verify_calls[0] == ("goal:owned123", "user.test")


@pytest.mark.asyncio
async def test_context_route_ownership_denied(mock_router, mock_service, mock_ownership_service):
    """Test context route returns 404 when user doesn't own entity."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="goals",
        scope=ContentScope.USER_OWNED,
        ownership_service=mock_ownership_service,
    )
    factory.register_routes(_app=None, rt=mock_router)

    context_handler = mock_router.get_route("GET", "/api/goals/context")
    request = MockRequest()

    # Request unowned entity - should fail with 404
    json_response = await context_handler(request, uid="goal:not-owned")
    response, status_code = extract_response(json_response)

    # Returns 404 (not 403) to prevent UID enumeration
    assert status_code == 404
    assert "not found" in response.get("detail", "").lower() or "not found" in str(response).lower()

    # Verify ownership was checked
    assert len(mock_ownership_service.verify_calls) == 1
    assert mock_ownership_service.verify_calls[0] == ("goal:not-owned", "user.test")

    # Verify service was NOT called (ownership failed first)
    assert len(mock_service.context_calls) == 0


@pytest.mark.asyncio
async def test_context_route_skips_ownership_for_shared_content(mock_router, mock_service):
    """Test context route skips ownership check for shared content."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="knowledge",
        scope=ContentScope.SHARED,
    )
    factory.register_routes(_app=None, rt=mock_router)

    context_handler = mock_router.get_route("GET", "/api/knowledge/context")
    request = MockRequest()

    # Request any entity - no ownership check
    json_response = await context_handler(request, uid="ku:any-knowledge")
    response, status_code = extract_response(json_response)

    assert status_code == 200
    assert "entity" in response
    # Service was called directly without ownership check
    assert len(mock_service.context_calls) == 1


@pytest.mark.asyncio
async def test_insights_route_with_ownership_verification(
    mock_router, mock_service, mock_ownership_service
):
    """Test insights route verifies ownership when enabled."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="goals",
        scope=ContentScope.USER_OWNED,
        ownership_service=mock_ownership_service,
    )
    factory.register_routes(_app=None, rt=mock_router)

    insights_handler = mock_router.get_route("GET", "/api/goals/insights")
    request = MockRequest()

    # Request owned entity - should succeed
    json_response = await insights_handler(request, uid="goal:owned123")
    response, status_code = extract_response(json_response)

    assert status_code == 200
    assert "insights" in response
    assert len(mock_ownership_service.verify_calls) == 1


@pytest.mark.asyncio
async def test_insights_route_ownership_denied(mock_router, mock_service, mock_ownership_service):
    """Test insights route returns 404 when user doesn't own entity."""
    factory = IntelligenceRouteFactory(
        intelligence_service=mock_service,
        domain_name="goals",
        scope=ContentScope.USER_OWNED,
        ownership_service=mock_ownership_service,
    )
    factory.register_routes(_app=None, rt=mock_router)

    insights_handler = mock_router.get_route("GET", "/api/goals/insights")
    request = MockRequest()

    # Request unowned entity - should fail with 404
    json_response = await insights_handler(request, uid="goal:not-owned")
    response, status_code = extract_response(json_response)

    # Returns 404 (not 403) to prevent UID enumeration
    assert status_code == 404

    # Verify service was NOT called (ownership failed first)
    assert len(mock_service.insights_calls) == 0
