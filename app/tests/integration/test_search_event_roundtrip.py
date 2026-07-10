"""
Search-event logging round-trip — real Neo4j
=============================================

Proves the discovery-analytics write + read path end to end against a real
Neo4j container:

    SearchExecuted → InMemoryEventBus → SearchEventRecorder
        → SearchEventBackend.record_search_event → (:SearchEvent)
        → get_search_gaps / count_search_events

The SearchRouter→publish half is covered by unit tests
(tests/unit/test_search_event_logging.py) — this file proves the persisted
node shape and the gap aggregation Cypher are real.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.search_event_backend import SearchEventBackend
from core.events.search_events import SearchExecuted
from core.services.search_event_recorder import SearchEventRecorder


@pytest_asyncio.fixture(loop_scope="session")
async def search_event_backend(neo4j_driver):
    """Backend over the test container, with per-test :SearchEvent cleanup."""
    backend = SearchEventBackend(Neo4jQueryExecutor(neo4j_driver))

    async def _wipe() -> None:
        async with neo4j_driver.session() as session:
            await session.run("MATCH (e:SearchEvent) DETACH DELETE e")

    await _wipe()
    yield backend
    await _wipe()


def _event(
    query: str,
    result_count: int,
    entry_point: str = "faceted",
    user_uid: str = "user_test",
) -> SearchExecuted:
    return SearchExecuted(
        query_text=query,
        user_uid=user_uid,
        entry_point=entry_point,
        result_count=result_count,
        zero_results=result_count == 0,
        domains=("ku",),
        filters_json='{"nous": "body"}',
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_event_bus_roundtrip_persists_search_event(neo4j_driver, search_event_backend):
    """Publishing search.executed through the real bus lands a :SearchEvent node."""
    bus = InMemoryEventBus()
    recorder = SearchEventRecorder(backend=search_event_backend)
    bus.subscribe(SearchExecuted, recorder.handle_search_executed)

    event = _event("Zxqv Probe ", result_count=0)
    await bus.publish_async(event)

    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:SearchEvent {query_normalized: $q}) RETURN e",
            q="zxqv probe",
        )
        record = await result.single()

    assert record is not None, ":SearchEvent node was not created"
    node = record["e"]
    assert node["query_text"] == "Zxqv Probe "
    assert node["user_uid"] == "user_test"
    assert node["entry_point"] == "faceted"
    assert node["zero_results"] is True
    assert node["result_count"] == 0
    assert list(node["domains"]) == ["ku"]
    assert node["filters_json"] == '{"nous": "body"}'
    assert node["created_at"] is not None  # native Neo4j datetime
    assert node["uid"]


@pytest.mark.asyncio(loop_scope="session")
async def test_gap_aggregation_groups_and_filters(search_event_backend):
    """Gap query groups by normalized text, counts zeros, excludes rich results."""
    recorder = SearchEventRecorder(backend=search_event_backend)

    # Two zero-result searches for the same (differently-cased) query,
    # one low-result, one rich query that must NOT appear as a gap.
    await recorder.handle_search_executed(_event("Breathing Space", 0))
    await recorder.handle_search_executed(_event("breathing space", 0, entry_point="intelligent"))
    await recorder.handle_search_executed(_event("gunas", 2))
    await recorder.handle_search_executed(_event("meditation", 25))

    gaps_result = await search_event_backend.get_search_gaps(max_result_count=2, days=90)
    assert gaps_result.is_ok
    gaps = {row["query"]: row for row in gaps_result.value}

    assert "meditation" not in gaps, "rich-result queries must not surface as gaps"
    assert gaps["breathing space"]["searches"] == 2
    assert gaps["breathing space"]["zero_count"] == 2
    assert sorted(gaps["breathing space"]["entry_points"]) == ["faceted", "intelligent"]
    assert gaps["gunas"]["searches"] == 1
    assert gaps["gunas"]["zero_count"] == 0
    assert gaps["gunas"]["avg_results"] == 2.0
    assert gaps["breathing space"]["last_seen"]

    count_result = await search_event_backend.count_search_events()
    assert count_result.is_ok
    assert count_result.value == 4
