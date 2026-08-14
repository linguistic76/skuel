"""Unit tests for POST /api/chunks/regenerate.

Covers the route handler wired in ingestion_api.py — admin gate, JSON
validation, error mapping, and the conditional registration based on whether
batch_chunking_service is wired.

Mirrors the fake-rt registry pattern from tests/unit/adapters/test_calendar_api.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from adapters.inbound.ingestion_api import create_ingestion_api_routes
from core.models.chunks_request import RegenerateChunksRequest
from core.models.enums import UserRole
from core.services.chunks.batch_chunking_service import RegenerationStats
from core.utils.result_simplified import Errors, Result
from tests.fixtures.csrf import attach_csrf


@pytest.fixture(autouse=True)
def _enforce_csrf(monkeypatch) -> None:
    """csrf_protected reads env at call time — pin enforcement ON; the
    request stubs carry a real minted token pair (attach_csrf)."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


class _RouteRegistry:
    """Capture handlers registered via @rt(path, methods=...)."""

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "POST"):
        return self.handlers[(path, method.upper())]

    def has(self, path: str, method: str = "POST") -> bool:
        return (path, method.upper()) in self.handlers


def _admin_user_service() -> MagicMock:
    """A user_service stub that resolves every uid to an ADMIN user."""
    user = SimpleNamespace(role=UserRole.ADMIN)
    user.has_permission = lambda _required: True
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _non_admin_user_service() -> MagicMock:
    """A user_service stub that resolves every uid to a non-admin (MEMBER)."""
    user = SimpleNamespace(role=UserRole.MEMBER)
    user.has_permission = lambda required: required == UserRole.MEMBER
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _request_with_session(session: dict | None, json_body: dict | None = None):
    """Minimal Starlette-like Request stub with optional session + json body."""
    request = SimpleNamespace()
    request.session = session if session is not None else {}
    request.method = "POST"
    request.url = SimpleNamespace(path="/api/chunks/regenerate")
    if json_body is not None:
        request.json = AsyncMock(return_value=json_body)
    else:
        request.json = AsyncMock(return_value={})
    return attach_csrf(request)


# ============================================================================
# Pydantic model
# ============================================================================


class TestRegenerateChunksRequest:
    def test_defaults(self) -> None:
        model = RegenerateChunksRequest()
        assert model.parent_uids is None
        assert model.force is False

    def test_explicit_values(self) -> None:
        model = RegenerateChunksRequest(parent_uids=["ku_a", "ku_b"], force=True)
        assert model.parent_uids == ["ku_a", "ku_b"]
        assert model.force is True

    def test_rejects_non_bool_force(self) -> None:
        # Pydantic V2 coerces "true"/"false" by default; reject only obvious garbage.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RegenerateChunksRequest(force=["not", "a", "bool"])


# ============================================================================
# Factory wiring — route is conditional on service being provided
# ============================================================================


class TestFactoryWiring:
    def test_route_registered_when_service_present(self) -> None:
        registry = _RouteRegistry()
        ingestion = MagicMock()
        batch_service = MagicMock()
        create_ingestion_api_routes(
            app=None,
            rt=registry,
            unified_ingestion=ingestion,
            user_service=_admin_user_service(),
            batch_chunking_service=batch_service,
        )
        assert registry.has("/api/chunks/regenerate", "POST")

    def test_route_skipped_when_service_none(self) -> None:
        registry = _RouteRegistry()
        ingestion = MagicMock()
        create_ingestion_api_routes(
            app=None,
            rt=registry,
            unified_ingestion=ingestion,
            user_service=_admin_user_service(),
            batch_chunking_service=None,
        )
        assert not registry.has("/api/chunks/regenerate", "POST")


# ============================================================================
# Route handler — admin gate, validation, error mapping
# ============================================================================


@pytest.fixture
def admin_routes_and_service():
    registry = _RouteRegistry()
    user_service = _admin_user_service()
    batch_service = MagicMock()
    create_ingestion_api_routes(
        app=None,
        rt=registry,
        unified_ingestion=MagicMock(),
        user_service=user_service,
        batch_chunking_service=batch_service,
    )
    return registry, batch_service


class TestRegenerateRouteHappyPath:
    @pytest.mark.asyncio
    async def test_success_returns_stats_dict(self, admin_routes_and_service) -> None:
        registry, batch_service = admin_routes_and_service

        stats = RegenerationStats(
            total_candidates=2,
            processed=2,
            succeeded=2,
            failed=0,
            skipped_no_body=0,
            duration_seconds=0.42,
        )
        batch_service.regenerate_chunks = AsyncMock(return_value=Result.ok(stats))

        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(
            session={"user_uid": "user_admin"},
            json_body={"parent_uids": ["ku_a", "ku_b"], "force": False},
        )

        response = await handler(request)
        assert response.status_code == 200

        import json

        body = json.loads(response.body)
        assert body["succeeded"] == 2
        assert body["failed"] == 0
        assert body["total_candidates"] == 2
        batch_service.regenerate_chunks.assert_awaited_once_with(
            parent_uids=["ku_a", "ku_b"], force=False
        )

    @pytest.mark.asyncio
    async def test_force_true_passed_through(self, admin_routes_and_service) -> None:
        registry, batch_service = admin_routes_and_service
        batch_service.regenerate_chunks = AsyncMock(return_value=Result.ok(RegenerationStats()))

        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(
            session={"user_uid": "user_admin"},
            json_body={"force": True},
        )

        await handler(request)
        kwargs = batch_service.regenerate_chunks.await_args.kwargs
        assert kwargs["parent_uids"] is None
        assert kwargs["force"] is True


class TestRegenerateRouteValidation:
    @pytest.mark.asyncio
    async def test_invalid_body_returns_400(self, admin_routes_and_service) -> None:
        registry, batch_service = admin_routes_and_service
        batch_service.regenerate_chunks = AsyncMock()

        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(
            session={"user_uid": "user_admin"},
            json_body={"force": ["not", "a", "bool"]},
        )

        response = await handler(request)
        # boundary_handler maps Errors.validation → 400
        assert response.status_code == 400
        batch_service.regenerate_chunks.assert_not_called()


class TestRegenerateRouteServiceFailure:
    @pytest.mark.asyncio
    async def test_database_failure_maps_to_503(self, admin_routes_and_service) -> None:
        registry, batch_service = admin_routes_and_service
        batch_service.regenerate_chunks = AsyncMock(
            return_value=Result.fail(
                Errors.database(
                    operation="fetch_regeneration_candidates",
                    message="Neo4j unreachable",
                )
            )
        )

        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(
            session={"user_uid": "user_admin"},
            json_body={"parent_uids": None, "force": False},
        )

        response = await handler(request)
        # boundary_handler maps Errors.database → 503
        assert response.status_code == 503


class TestRegenerateRouteAdminGate:
    @pytest.mark.asyncio
    async def test_unauthenticated_raises_401(self) -> None:
        registry = _RouteRegistry()
        create_ingestion_api_routes(
            app=None,
            rt=registry,
            unified_ingestion=MagicMock(),
            user_service=_admin_user_service(),
            batch_chunking_service=MagicMock(),
        )
        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(session={})  # no user_uid

        with pytest.raises(HTTPException) as exc_info:
            await handler(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_user_raises_403(self) -> None:
        registry = _RouteRegistry()
        create_ingestion_api_routes(
            app=None,
            rt=registry,
            unified_ingestion=MagicMock(),
            user_service=_non_admin_user_service(),
            batch_chunking_service=MagicMock(),
        )
        handler = registry.get("/api/chunks/regenerate", "POST")
        request = _request_with_session(
            session={"user_uid": "user_member"},
            json_body={"force": False},
        )

        with pytest.raises(HTTPException) as exc_info:
            await handler(request)
        assert exc_info.value.status_code == 403
