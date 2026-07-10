"""Tests for the admin search-gaps read surface (discovery analytics, read side).

Covers:
- AdminStatsService.get_search_gaps / get_search_event_total happy paths
- None-backend degrade (Result.ok([]) / Result.ok(0), never an error)
- Error propagation from the backend
- AdminOrchestrator.get_analytics_data passthrough + empty-on-error degrade
- render_search_gaps empty state and populated table shape
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.orchestrator.admin_orchestrator import AdminOrchestrator
from core.ports.query_types import SearchGapRow
from core.services.admin_stats_service import AdminStatsService
from core.utils.result_simplified import Errors, Result
from ui.admin.views import AdminAnalyticsComponents

GAP_ROW = SearchGapRow(
    query="meditation basics",
    searches=4,
    zero_count=3,
    avg_results=0.5,
    last_seen="2026-07-10T09:00:00Z",
    entry_points=["faceted", "advanced"],
)


def _search_event_backend(
    gaps: Result[list[SearchGapRow]] | None = None,
    total: Result[int] | None = None,
) -> MagicMock:
    backend = MagicMock()
    backend.get_search_gaps = AsyncMock(return_value=gaps or Result.ok([GAP_ROW]))
    backend.count_search_events = AsyncMock(return_value=total or Result.ok(42))
    return backend


# ============================================================================
# AdminStatsService
# ============================================================================


@pytest.mark.anyio
async def test_get_search_gaps_happy_path() -> None:
    """Gap rows pass through, with the threshold kwargs forwarded to the backend."""
    backend = _search_event_backend()
    service = AdminStatsService(backend=MagicMock(), search_event_backend=backend)

    result = await service.get_search_gaps(max_result_count=1, days=30, limit=10)

    assert not result.is_error
    assert result.value == [GAP_ROW]
    backend.get_search_gaps.assert_awaited_once_with(max_result_count=1, days=30, limit=10)


@pytest.mark.anyio
async def test_get_search_event_total_happy_path() -> None:
    """The running :SearchEvent total passes through from the backend."""
    service = AdminStatsService(backend=MagicMock(), search_event_backend=_search_event_backend())

    result = await service.get_search_event_total()

    assert not result.is_error
    assert result.value == 42


@pytest.mark.anyio
async def test_none_backend_degrades_to_empty() -> None:
    """No search-event backend wired → empty queue + zero total, never an error."""
    service = AdminStatsService(backend=MagicMock())

    gaps = await service.get_search_gaps()
    total = await service.get_search_event_total()

    assert not gaps.is_error
    assert gaps.value == []
    assert not total.is_error
    assert total.value == 0


@pytest.mark.anyio
async def test_backend_errors_propagate() -> None:
    """Backend failures propagate as error Results (the orchestrator degrades them)."""
    err: Result[list[SearchGapRow]] = Result.fail(
        Errors.database(operation="get_search_gaps", message="down")
    )
    total_err: Result[int] = Result.fail(
        Errors.database(operation="count_search_events", message="down")
    )
    backend = _search_event_backend(gaps=err, total=total_err)
    service = AdminStatsService(backend=MagicMock(), search_event_backend=backend)

    assert (await service.get_search_gaps()).is_error
    assert (await service.get_search_event_total()).is_error


# ============================================================================
# AdminOrchestrator
# ============================================================================


def _orchestrator(admin_stats: MagicMock) -> AdminOrchestrator:
    admin_stats.get_user_role_counts = AsyncMock(
        return_value=Result.ok(
            {"total": 1, "admins": 1, "teachers": 0, "members": 0, "registered": 0}
        )
    )
    admin_stats.get_activity_entity_counts = AsyncMock(
        return_value=Result.ok({"tasks_created": 2, "habits_active": 1, "goals_active": 1})
    )
    return AdminOrchestrator(user_service=MagicMock(), admin_stats=admin_stats)


@pytest.mark.anyio
async def test_analytics_data_includes_search_gaps() -> None:
    """get_analytics_data carries the gap rows (as dicts) and the event total."""
    admin_stats = MagicMock()
    admin_stats.get_search_gaps = AsyncMock(return_value=Result.ok([GAP_ROW]))
    admin_stats.get_search_event_total = AsyncMock(return_value=Result.ok(42))

    data = await _orchestrator(admin_stats).get_analytics_data()

    assert data["search_gaps"] == [dict(GAP_ROW)]
    assert data["search_event_total"] == 42


@pytest.mark.anyio
async def test_analytics_data_degrades_on_gap_errors() -> None:
    """Failed gap sub-queries fall back to []/0 — the page never sees an error."""
    admin_stats = MagicMock()
    admin_stats.get_search_gaps = AsyncMock(
        return_value=Result.fail(Errors.database(operation="get_search_gaps", message="down"))
    )
    admin_stats.get_search_event_total = AsyncMock(
        return_value=Result.fail(Errors.database(operation="count_search_events", message="down"))
    )

    data = await _orchestrator(admin_stats).get_analytics_data()

    assert data["search_gaps"] == []
    assert data["search_event_total"] == 0
    # The pre-existing sections still render their (mocked) values
    assert data["user_stats"]["total"] == 1
    assert data["activity_stats"]["tasks_created"] == 2


# ============================================================================
# UI rendering (shape only — runtime verification is the authed probe)
# ============================================================================


def test_render_search_gaps_empty_state() -> None:
    """No gaps → empty-state line + running total vs the Phase-2 trigger."""
    html = to_xml(AdminAnalyticsComponents.render_search_gaps([], 0))

    assert "No zero/low-result searches recorded yet" in html
    assert "0 search event(s) logged" in html
    assert "1,000+" in html


def test_render_search_gaps_table_row() -> None:
    """A gap row renders query, counts, formatted avg, date, and entry points."""
    html = to_xml(AdminAnalyticsComponents.render_search_gaps([dict(GAP_ROW)], 42))

    assert "meditation basics" in html
    assert "0.5" in html  # avg_results formatted to one decimal
    assert "2026-07-10" in html  # date part of last_seen
    assert "faceted, advanced" in html
    assert "42 search event(s) logged" in html


def test_render_analytics_dashboard_includes_gap_section() -> None:
    """The dashboard renders the Search Gaps card alongside the existing sections."""
    html = to_xml(
        AdminAnalyticsComponents.render_analytics_dashboard(
            {
                "user_stats": {},
                "activity_stats": {},
                "search_gaps": [dict(GAP_ROW)],
                "search_event_total": 42,
            }
        )
    )

    assert "Search Gaps (content authoring queue)" in html
    assert "meditation basics" in html
