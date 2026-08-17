"""End-to-end tests for the schema change detection capability.

These tests drive the detector through the *live* adapter seam
(`Neo4jAdapter.get_schema_change_detector()` → `check_schema_changes()`),
which is the path `adapters/persistence/neo4j_adapter.py` exposes to the rest
of the app. Before the import fix this path raised `ImportError` the moment it
was touched (the service imported `core.models.schema_change`, which has never
existed — the real models live in `core.infrastructure.database.schema_change`),
so merely importing the adapter method was enough to prove the revival.

One test also guards the async handler dispatch corrected in PR #136: a change
report reached through the adapter seam must fan out to registered handlers,
sync and async alike.

The former `AdaptiveOptimizationHandler` coverage went with the handler
(2026-08-17) — it existed only to clear the deleted `query_builders/` caches, so
the adapter seam now registers no handler of its own.
"""

from datetime import datetime
from typing import Any

import pytest

from adapters.persistence.neo4j_adapter import Neo4jAdapter
from core.infrastructure.database.schema import (
    Neo4jIndex,
    NodeLabelInfo,
    SchemaContext,
)
from core.services.schema_change_detector import SchemaChangeDetector
from core.utils.result_simplified import Result


def _make_schema(*, labels: list[str], index_names: list[str]) -> SchemaContext:
    """Build a minimal but valid SchemaContext for fingerprinting."""
    indexes = [
        Neo4jIndex(
            name=name,
            type="BTREE",
            entity_type="NODE",
            labels=["Entity"],
            properties=["uid"],
            state="ONLINE",
        )
        for name in index_names
    ]
    node_label_info = {
        label: NodeLabelInfo(
            label=label, count=1, properties={"uid"}, sample_properties={"uid": "x"}
        )
        for label in labels
    }
    return SchemaContext(
        node_labels=labels,
        relationship_types=["USES_KU"],
        indexes=indexes,
        constraints=[],
        node_label_info=node_label_info,
        relationship_type_info={},
        property_names={"uid"},
        indexed_properties={},
        unique_properties={},
        introspection_timestamp=datetime(2026, 1, 1),
        schema_hash="hash",
    )


class _FakeSchemaService:
    """Stand-in for Neo4jSchemaService — returns a settable SchemaContext.

    Mirrors the only method the detector consumes: an async
    `get_schema_context(force_refresh=...)` returning `Result[SchemaContext]`.
    """

    def __init__(self, schema: SchemaContext) -> None:
        self.current = schema
        self.call_count = 0

    async def get_schema_context(self, force_refresh: bool = False) -> Result[SchemaContext]:
        self.call_count += 1
        return Result.ok(self.current)


def _adapter_with_schema(schema_service: _FakeSchemaService) -> Neo4jAdapter:
    """Construct an unconnected adapter wired to a fake schema service."""
    adapter = Neo4jAdapter()
    adapter._schema_service = schema_service  # short-circuits get_schema_service()
    return adapter


@pytest.mark.asyncio
async def test_adapter_seam_builds_working_detector() -> None:
    """get_schema_change_detector() must construct a real detector.

    This is the regression guard for the broken import: before the fix this
    line raised ImportError (core.models.schema_change does not exist).
    """
    schema = _make_schema(labels=["Entity", "Task"], index_names=["idx_uid"])
    adapter = _adapter_with_schema(_FakeSchemaService(schema))

    detector = adapter.get_schema_change_detector()

    assert isinstance(detector, SchemaChangeDetector)
    # No handler is auto-registered: the seam builds a bare detector whose job
    # is drift detection + logging (the adaptive cache-clearing handler was
    # deleted with the query_builders/ stack it served).
    assert detector._change_handlers == []
    # Cached on the adapter — second call returns the same instance.
    assert adapter.get_schema_change_detector() is detector


@pytest.mark.asyncio
async def test_initialize_captures_baseline_fingerprint() -> None:
    schema = _make_schema(labels=["Entity"], index_names=["idx_uid"])
    detector = SchemaChangeDetector(_FakeSchemaService(schema))
    detector.enable_persistence = False  # keep history in-memory, no disk I/O

    result = await detector.initialize()

    assert result.is_ok
    assert detector._current_fingerprint is not None
    assert detector._current_fingerprint.index_count == 1


@pytest.mark.asyncio
async def test_check_for_changes_no_change_returns_empty_report() -> None:
    schema = _make_schema(labels=["Entity"], index_names=["idx_uid"])
    detector = SchemaChangeDetector(_FakeSchemaService(schema))
    detector.enable_persistence = False
    await detector.initialize()

    report = (await detector.check_for_changes()).value

    assert report.changes == []


@pytest.mark.asyncio
async def test_check_for_changes_detects_index_addition() -> None:
    fake = _FakeSchemaService(_make_schema(labels=["Entity"], index_names=["idx_uid"]))
    detector = SchemaChangeDetector(fake)
    detector.enable_persistence = False
    await detector.initialize()

    # Simulate a schema migration: a new index appears.
    fake.current = _make_schema(labels=["Entity"], index_names=["idx_uid", "idx_status"])

    report = (await detector.check_for_changes()).value

    assert report.changes, "expected the new index to be detected"
    assert detector._current_fingerprint is not None
    assert detector._current_fingerprint.index_count == 2


@pytest.mark.asyncio
async def test_end_to_end_change_reaches_registered_handler() -> None:
    """Full path: adapter seam → detector → a registered handler.

    A detected schema change must fan out through `adapter.check_schema_changes()`
    to handlers registered on the cached detector. This exercises the async
    handler dispatch (PR #136) end to end through the seam compose.py uses.
    """
    fake = _FakeSchemaService(_make_schema(labels=["Entity"], index_names=["idx_uid"]))
    adapter = _adapter_with_schema(fake)

    detector = adapter.get_schema_change_detector()
    detector.enable_persistence = False
    await detector.initialize()

    handled: list[Any] = []

    async def record(event: Any) -> None:
        handled.append(event)

    detector.add_change_handler(record)

    # Migration: enough index churn to force re-optimization (HIGH impact).
    fake.current = _make_schema(
        labels=["Entity", "Task", "Goal"],
        index_names=[f"idx_{i}" for i in range(10)],
    )

    report = (await adapter.check_schema_changes()).value

    assert report.changes
    assert report.requires_reoptimization
    assert len(handled) == 1


@pytest.mark.asyncio
async def test_handler_dispatch_supports_sync_and_async_handlers() -> None:
    """The SchemaChangeHandler contract accepts both sync and async callables."""
    fake = _FakeSchemaService(_make_schema(labels=["Entity"], index_names=["idx_uid"]))
    detector = SchemaChangeDetector(fake)
    detector.enable_persistence = False
    await detector.initialize()

    seen: list[str] = []

    def sync_handler(event: object) -> None:
        seen.append("sync")

    async def async_handler(event: object) -> None:
        seen.append("async")

    detector.add_change_handler(sync_handler)
    detector.add_change_handler(async_handler)

    fake.current = _make_schema(labels=["Entity", "Task"], index_names=["idx_uid"])
    await detector.check_for_changes()

    assert seen == ["sync", "async"]


@pytest.mark.asyncio
async def test_initialize_and_stop_schema_monitoring_lifecycle() -> None:
    """The adapter methods compose.py wires must start and stop the poll loop.

    `initialize_schema_monitoring()` (called at startup when
    NEO4J_SCHEMA_MONITORING is on) baselines the detector and launches its
    internal poll task; `stop_schema_monitoring()` (called at shutdown) cancels
    it. This guards the bootstrap wiring end to end.
    """
    fake = _FakeSchemaService(_make_schema(labels=["Entity"], index_names=["idx_uid"]))
    adapter = _adapter_with_schema(fake)

    # Disable persistence on the cached detector before the loop touches disk.
    detector = adapter.get_schema_change_detector()
    detector.enable_persistence = False

    start = await adapter.initialize_schema_monitoring(interval_seconds=900)
    assert start.is_ok
    assert detector._is_monitoring is True
    assert detector._monitor_task is not None

    stop = await adapter.stop_schema_monitoring()
    assert stop.is_ok
    assert detector._is_monitoring is False
    assert detector._monitor_task.done()


@pytest.mark.asyncio
async def test_stop_schema_monitoring_is_safe_when_never_started() -> None:
    """Shutdown must not error if monitoring was never started (flag off)."""
    adapter = _adapter_with_schema(
        _FakeSchemaService(_make_schema(labels=["Entity"], index_names=["idx_uid"]))
    )
    result = await adapter.stop_schema_monitoring()
    assert result.is_ok
