"""Unit tests for POST /api/ingest/directory ingestion_mode passthrough.

The directory endpoint forwards ingestion_mode ("full" | "incremental" |
"smart") to UnifiedIngestionService.ingest_directory — the seam the vault
watcher (scripts/vault_watch.py) depends on for cheap repeat syncs. Covers
mode validation, default behavior, and the incremental stats in the response.

Mirrors the fake-rt registry pattern from tests/unit/test_chunks_regenerate_route.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.inbound.ingestion_api import create_ingestion_api_routes
from core.models.enums import UserRole
from core.services.ingestion.types import IncrementalStats, IngestionStats
from core.utils.result_simplified import Result


@pytest.fixture(autouse=True)
def _disable_csrf(monkeypatch) -> None:
    """csrf_protected reads env at call time — force enforcement off for unit tests."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


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


def _admin_user_service() -> MagicMock:
    user = SimpleNamespace(role=UserRole.ADMIN)
    user.has_permission = lambda _required: True
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _request(json_body: dict):
    request = SimpleNamespace()
    request.session = {"user_uid": "user_admin"}
    request.method = "POST"
    request.url = SimpleNamespace(path="/api/ingest/directory")
    request.json = AsyncMock(return_value=json_body)
    return request


@pytest.fixture
def routes_and_service(monkeypatch, tmp_path):
    monkeypatch.setenv("SKUEL_INGESTION_ALLOWED_PATHS", str(tmp_path))
    registry = _RouteRegistry()
    ingestion = MagicMock()
    create_ingestion_api_routes(
        app=None,
        rt=registry,
        unified_ingestion=ingestion,
        user_service=_admin_user_service(),
    )
    return registry, ingestion, tmp_path


class TestIngestionModePassthrough:
    @pytest.mark.asyncio
    async def test_incremental_mode_forwarded_and_stats_returned(self, routes_and_service) -> None:
        registry, ingestion, vault = routes_and_service
        stats = IncrementalStats(
            total_files=10,
            files_checked=10,
            files_skipped=8,
            files_ingested=2,
            nodes_created=1,
            nodes_updated=1,
            duration_seconds=0.5,
        )
        ingestion.ingest_directory = AsyncMock(return_value=Result.ok(stats))

        handler = registry.get("/api/ingest/directory", "POST")
        response = await handler(
            _request({"directory": str(vault), "ingestion_mode": "incremental"})
        )

        assert response.status_code == 200
        kwargs = ingestion.ingest_directory.await_args.kwargs
        assert kwargs["ingestion_mode"] == "incremental"

        body = json.loads(response.body)
        assert body["files_skipped"] == 8
        assert body["files_ingested"] == 2
        assert body["skip_efficiency"] == 80.0

    @pytest.mark.asyncio
    async def test_mode_defaults_to_full(self, routes_and_service) -> None:
        registry, ingestion, vault = routes_and_service
        ingestion.ingest_directory = AsyncMock(
            return_value=Result.ok(IngestionStats(total_files=0, duration_seconds=0.0))
        )

        handler = registry.get("/api/ingest/directory", "POST")
        response = await handler(_request({"directory": str(vault)}))

        assert response.status_code == 200
        kwargs = ingestion.ingest_directory.await_args.kwargs
        assert kwargs["ingestion_mode"] == "full"

        body = json.loads(response.body)
        assert "files_skipped" not in body  # full mode → no incremental fields

    @pytest.mark.asyncio
    async def test_invalid_mode_rejected_before_service_call(self, routes_and_service) -> None:
        registry, ingestion, vault = routes_and_service
        ingestion.ingest_directory = AsyncMock()

        handler = registry.get("/api/ingest/directory", "POST")
        response = await handler(_request({"directory": str(vault), "ingestion_mode": "turbo"}))

        # boundary_handler maps Errors.validation → 400
        assert response.status_code == 400
        ingestion.ingest_directory.assert_not_called()
