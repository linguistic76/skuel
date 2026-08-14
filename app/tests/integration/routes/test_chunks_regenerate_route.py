"""Integration test: POST /api/chunks/regenerate against real Neo4j.

Exercises the route closure end-to-end:
- Captured via fake `rt` decorator (same pattern as tests/unit/test_chunks_regenerate_route.py)
- Wrapped in require_admin + csrf_protected + boundary_handler (the real decorators)
- Backed by a real BatchChunkingService against the Neo4j testcontainer

This complements the service-layer cycle test in
tests/integration/test_batch_chunk_regeneration.py — that file proves the
service replaces chunks against Neo4j; this file proves the HTTP route does
the same thing through the full decorator chain and returns the contract
shape (RegenerationStats dict + 200 status).
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.inbound.ingestion_api import create_ingestion_api_routes
from adapters.persistence.neo4j.batch_chunking_backend import BatchChunkingBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from core.models.enums import UserRole
from core.models.ps_content.content_chunks import CHUNKING_ALGORITHM_VERSION
from core.services.chunks.batch_chunking_service import BatchChunkingService
from core.services.entity_chunking_service import EntityChunkingService
from core.utils.result_simplified import Result
from tests.fixtures.csrf import attach_csrf


@pytest.fixture(autouse=True)
def _enforce_csrf(monkeypatch) -> None:
    """Pin enforcement ON — request stubs carry a real minted token pair."""
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")


class _RouteRegistry:
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


class _DriverConnection:
    """Adapter so Neo4jContentAdapter can use the integration neo4j_driver fixture."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


def _admin_user_service() -> MagicMock:
    user = SimpleNamespace(role=UserRole.ADMIN)
    user.has_permission = lambda _required: True
    svc = MagicMock()
    svc.get_user = AsyncMock(return_value=Result.ok(user))
    return svc


def _admin_request(json_body: dict | None = None):
    request = SimpleNamespace()
    request.session = {"user_uid": "user_admin"}
    request.method = "POST"
    request.url = SimpleNamespace(path="/api/chunks/regenerate")
    request.json = AsyncMock(return_value=json_body or {})
    return attach_csrf(request)


_FIXTURE_BODY = """---
type: Lesson
title: Route Regeneration Test
domain: tech
---

# Heading One

This is the first body paragraph used by the route regeneration test.

## Definitions

A chunk is a semantic unit of content used by retrieval.

## Examples

Here is an example chunk.

```python
def example():
    return 1
```
"""


@pytest.mark.asyncio
async def test_regenerate_route_replaces_stale_chunks(neo4j_driver):
    """POST /api/chunks/regenerate returns 200 + stats and replaces stale chunks."""
    with NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(_FIXTURE_BODY)
        temp_path = Path(f.name)

    try:
        chunking_service = EntityChunkingService()
        content_adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
        ingestion_service = make_unified_ingestion_service(
            driver=neo4j_driver,
            chunking_service=chunking_service,
            content_adapter=content_adapter,
        )

        ingest_result = await ingestion_service.ingest_file(temp_path)
        assert ingest_result.is_ok
        parent_uid = ingest_result.value["uid"]

        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN count(chunk) AS n
                """,
                {"uid": parent_uid},
            )
            initial_chunk_count = (await res.single())["n"]
        assert initial_chunk_count > 0

        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                SET chunk.chunking_version = 'v0_stale'
                """,
                {"uid": parent_uid},
            )

        batch_service = BatchChunkingService(
            backend=BatchChunkingBackend(neo4j_driver),
            chunking_service=chunking_service,
            content_adapter=content_adapter,
            event_bus=None,
        )

        registry = _RouteRegistry()
        create_ingestion_api_routes(
            app=None,
            rt=registry,
            unified_ingestion=MagicMock(),
            user_service=_admin_user_service(),
            batch_chunking_service=batch_service,
        )

        handler = registry.get("/api/chunks/regenerate", "POST")
        response = await handler(
            _admin_request(json_body={"parent_uids": [parent_uid], "force": False})
        )

        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["total_candidates"] == 1
        assert body["processed"] == 1
        assert body["succeeded"] == 1
        assert body["failed"] == 0
        assert "duration_seconds" in body

        async with neo4j_driver.session() as session:
            res = await session.run(
                """
                MATCH (c:Content {uid: $uid})-[:HAS_CHUNK]->(chunk:ContentChunk)
                RETURN count(chunk) AS n,
                       collect(DISTINCT chunk.chunking_version) AS versions
                """,
                {"uid": parent_uid},
            )
            record = await res.single()

        assert record["n"] == initial_chunk_count, (
            f"Expected {initial_chunk_count} chunks (no duplication), got {record['n']}"
        )
        assert record["versions"] == [CHUNKING_ALGORITHM_VERSION], (
            f"All chunks should be at current version, found {record['versions']}"
        )
    finally:
        temp_path.unlink()
