"""Tests for search-event logging — search.executed → SearchEventRecorder → :SearchEvent.

Covers the discovery-analytics write path:
- SearchExecuted event shape and registry entry
- SearchEventRecorder happy path, normalization, and fail-soft guarantees
- SearchRouter publishes exactly ONE event per external entry point
  (faceted / intelligent / advanced), suppresses internal fan-out, and
  skips empty/filter-only queries entirely
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from core.events import EVENT_REGISTRY, SearchExecuted
from core.models.enums.entity_enums import EntityType
from core.models.search_request import SearchRequest, SearchResponse
from core.orchestrator.search_router import SearchRouter
from core.services.search_event_recorder import SearchEventRecorder
from core.utils.result_simplified import Errors, Result

# ============================================================================
# Event shape
# ============================================================================


def test_search_executed_event_shape() -> None:
    """Event type registers as search.executed with auto occurred_at."""
    event = SearchExecuted(
        query_text="meditation",
        user_uid="user_mike",
        entry_point="faceted",
        result_count=3,
        zero_results=False,
    )
    assert event.event_type == "search.executed"
    assert event.occurred_at is not None
    assert event.domains == ()
    assert event.filters_json == "{}"
    assert EVENT_REGISTRY["search.executed"] is SearchExecuted


# ============================================================================
# SearchEventRecorder
# ============================================================================


def _recorder(backend: MagicMock | None = None) -> tuple[SearchEventRecorder, MagicMock]:
    backend = backend or MagicMock()
    backend.record_search_event = AsyncMock(return_value=Result.ok(None))
    return SearchEventRecorder(backend=backend), backend


@pytest.mark.anyio
async def test_recorder_persists_normalized_props() -> None:
    """Recorder builds the :SearchEvent props: normalization + isoformat timestamp."""
    recorder, backend = _recorder()
    event = SearchExecuted(
        query_text="  Meditation Basics ",
        user_uid="user_mike",
        entry_point="faceted",
        result_count=0,
        zero_results=True,
        semantic_boost=True,
        domains=("ku",),
        filters_json='{"nous": "body"}',
    )

    await recorder.handle_search_executed(event)

    backend.record_search_event.assert_awaited_once()
    props = backend.record_search_event.await_args.args[0]
    assert props["query_text"] == "  Meditation Basics "
    assert props["query_normalized"] == "meditation basics"
    assert props["user_uid"] == "user_mike"
    assert props["entry_point"] == "faceted"
    assert props["domains"] == ["ku"]
    assert props["result_count"] == 0
    assert props["zero_results"] is True
    assert props["semantic_boost"] is True
    assert props["created_at"] == event.occurred_at.isoformat()
    assert props["uid"]


@pytest.mark.anyio
async def test_recorder_fail_soft_on_error_result() -> None:
    """A failed backend Result is logged, never raised."""
    backend = MagicMock()
    backend.record_search_event = AsyncMock(
        return_value=Result.fail(Errors.database(operation="record", message="down"))
    )
    recorder = SearchEventRecorder(backend=backend)
    event = SearchExecuted(
        query_text="x", user_uid=None, entry_point="advanced", result_count=1, zero_results=False
    )

    await recorder.handle_search_executed(event)  # must not raise


@pytest.mark.anyio
async def test_recorder_fail_soft_on_database_exception() -> None:
    """A raised Neo4j exception is swallowed — logging can never break search."""
    backend = MagicMock()
    backend.record_search_event = AsyncMock(side_effect=ServiceUnavailable("neo4j down"))
    recorder = SearchEventRecorder(backend=backend)
    event = SearchExecuted(
        query_text="x", user_uid=None, entry_point="faceted", result_count=0, zero_results=True
    )

    await recorder.handle_search_executed(event)  # must not raise


# ============================================================================
# SearchRouter publish behavior
# ============================================================================


def _router_with_bus() -> tuple[SearchRouter, AsyncMock]:
    publish = AsyncMock()
    bus = MagicMock()
    bus.publish_async = publish
    return SearchRouter(event_bus=bus), publish


def _published_events(publish: AsyncMock) -> list[SearchExecuted]:
    return [
        call.args[0] for call in publish.await_args_list if isinstance(call.args[0], SearchExecuted)
    ]


def _empty_response(query_text: str | None) -> SearchResponse:
    return SearchResponse(
        results=[],
        total=0,
        limit=50,
        offset=0,
        query_text=query_text,
        domain=None,
        facet_counts={},
        applied_filters={},
        search_time_ms=1.0,
    )


@pytest.mark.anyio
async def test_faceted_search_publishes_one_event() -> None:
    """The cross-domain faceted path publishes exactly one search.executed."""
    router, publish = _router_with_bus()
    router._cross_domain_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await router.faceted_search(SearchRequest(query_text="zxqv-probe"), "user_mike")

    assert result.is_ok
    events = _published_events(publish)
    assert len(events) == 1
    event = events[0]
    assert event.entry_point == "faceted"
    assert event.query_text == "zxqv-probe"
    assert event.user_uid == "user_mike"
    assert event.result_count == 0
    assert event.zero_results is True
    assert event.domains == ()
    assert json.loads(event.filters_json) == {}


@pytest.mark.anyio
async def test_faceted_search_empty_query_publishes_nothing() -> None:
    """Filter-only searches (no query text) carry no gap signal — never logged."""
    router, publish = _router_with_bus()
    router._cross_domain_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await router.faceted_search(SearchRequest(query_text=None), "user_mike")

    assert result.is_ok
    assert _published_events(publish) == []


@pytest.mark.anyio
async def test_faceted_search_log_event_false_suppresses() -> None:
    """log_event=False (internal fan-out) publishes nothing."""
    router, publish = _router_with_bus()
    router._cross_domain_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    await router.faceted_search(SearchRequest(query_text="probe"), "user_mike", log_event=False)

    assert _published_events(publish) == []


@pytest.mark.anyio
async def test_publish_failure_does_not_break_search() -> None:
    """A broken event bus must not turn a successful search into a failure."""
    router, publish = _router_with_bus()
    publish.side_effect = RuntimeError("bus exploded")
    router._cross_domain_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    result = await router.faceted_search(SearchRequest(query_text="probe"), "user_mike")

    assert result.is_ok


@pytest.mark.anyio
async def test_intelligent_search_publishes_exactly_one_event() -> None:
    """intelligent_search suppresses its internal faceted calls and publishes once."""
    router, publish = _router_with_bus()

    inner_calls: list[dict] = []

    async def _fake_faceted(request, user_uid=None, **kwargs):
        inner_calls.append(kwargs)
        return Result.ok(_empty_response(request.query_text))

    router.faceted_search = _fake_faceted  # type: ignore[method-assign]
    router.search = AsyncMock(return_value=Result.ok([]))  # type: ignore[method-assign]

    result = await router.intelligent_search("urgent health tasks", user_uid="user_mike")

    assert result.is_ok
    # Every internal faceted call must carry the double-log guard
    assert inner_calls, "intelligent_search should fan out through faceted_search"
    assert all(call.get("log_event") is False for call in inner_calls)
    events = _published_events(publish)
    assert len(events) == 1
    assert events[0].entry_point == "intelligent"
    assert events[0].query_text == "urgent health tasks"
    assert events[0].domains  # target domains recorded


@pytest.mark.anyio
async def test_advanced_search_publishes_one_event_with_domain_filter() -> None:
    """advanced_search publishes once, recording the explicit entity-type filter."""
    router, publish = _router_with_bus()
    router._execute_advanced_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    request = SearchRequest(query_text="python", entity_types=[EntityType.KU])
    result = await router.advanced_search(request)

    assert result.is_ok
    events = _published_events(publish)
    assert len(events) == 1
    event = events[0]
    assert event.entry_point == "advanced"
    assert event.domains == ("ku",)
    assert event.zero_results is True
    assert event.semantic_boost is False


@pytest.mark.anyio
async def test_advanced_search_records_semantic_boost_flag() -> None:
    """The semantic/learning strategy's flag round-trips into the event (Codex P2 #596)."""
    router, publish = _router_with_bus()
    router._execute_advanced_search = AsyncMock(return_value=[])  # type: ignore[method-assign]

    request = SearchRequest(
        query_text="python",
        entity_types=[EntityType.KU],
        enable_semantic_boost=True,
    )
    result = await router.advanced_search(request)

    assert result.is_ok
    events = _published_events(publish)
    assert len(events) == 1
    assert events[0].semantic_boost is True
