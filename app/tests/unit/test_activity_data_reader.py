"""
Unit Tests for ActivityDataReader
===================================

Tests the shared read layer that both ProgressFeedbackGenerator and
ActivityReviewService use to query user activity data.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.feedback.activity_data_reader import ActivityData, ActivityDataReader
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute_query = AsyncMock(return_value=Result.ok([]))
    return executor


@pytest.fixture
def reader(mock_executor):
    return ActivityDataReader(executor=mock_executor)


def _window():
    end = datetime.now()
    start = end - timedelta(days=7)
    return start, end


# ============================================================================
# SINGLE ROUND-TRIP
# ============================================================================


class TestSingleRoundTrip:
    """read() issues exactly one execute_query call regardless of domains."""

    @pytest.mark.asyncio
    async def test_single_query_all_domains(self, reader, mock_executor):
        """All-domain read issues 1 query."""
        start, end = _window()
        await reader.read("user_alice", start, end)
        assert mock_executor.execute_query.call_count == 1

    @pytest.mark.asyncio
    async def test_single_query_filtered_domains(self, reader, mock_executor):
        """Domain-filtered read still issues 1 query."""
        start, end = _window()
        await reader.read("user_alice", start, end, domains=["tasks", "goals"])
        assert mock_executor.execute_query.call_count == 1


# ============================================================================
# EMPTY RESULT
# ============================================================================


class TestEmptyResult:
    """Empty or missing query rows produce an empty ActivityData."""

    @pytest.mark.asyncio
    async def test_no_rows_returns_empty_activity_data(self, reader, mock_executor):
        """Empty row list → ActivityData with empty lists."""
        mock_executor.execute_query.return_value = Result.ok([])
        start, end = _window()

        result = await reader.read("user_ghost", start, end)

        assert not result.is_error
        data = result.value
        assert data.main_records == []
        assert data.event_records == []
        assert data.choice_records == []

    @pytest.mark.asyncio
    async def test_null_records_filtered_out(self, reader, mock_executor):
        """Null entries inside record lists are filtered before returning."""
        mock_executor.execute_query.return_value = Result.ok(
            [{"main_records": [None, None], "event_records": [], "choice_records": []}]
        )
        start, end = _window()

        result = await reader.read("user_alice", start, end)

        assert result.value.main_records == []


# ============================================================================
# DOMAIN FILTERING
# ============================================================================


class TestDomainFiltering:
    """entity_types parameter passed to the query reflects the domains filter."""

    @pytest.mark.asyncio
    async def test_all_domains_passes_all_entity_types(self, reader, mock_executor):
        """domains=None → entity_types includes task, goal, habit, principle."""
        start, end = _window()
        await reader.read("user_alice", start, end, domains=None)

        call_params = mock_executor.execute_query.call_args[0][1]
        entity_types = call_params["entity_types"]
        assert set(entity_types) == {"task", "goal", "habit", "principle"}

    @pytest.mark.asyncio
    async def test_tasks_only_passes_task_type(self, reader, mock_executor):
        """domains=['tasks'] → entity_types=['task']."""
        start, end = _window()
        await reader.read("user_alice", start, end, domains=["tasks"])

        call_params = mock_executor.execute_query.call_args[0][1]
        assert call_params["entity_types"] == ["task"]

    @pytest.mark.asyncio
    async def test_events_only_passes_empty_entity_types(self, reader, mock_executor):
        """domains=['events'] → entity_types=[] (events come from event_records block)."""
        start, end = _window()
        await reader.read("user_alice", start, end, domains=["events"])

        call_params = mock_executor.execute_query.call_args[0][1]
        assert call_params["entity_types"] == []


# ============================================================================
# RECORD PARTITIONING
# ============================================================================


class TestRecordPartitioning:
    """Records from the query row are correctly placed into ActivityData fields."""

    @pytest.mark.asyncio
    async def test_main_event_choice_records_partitioned(self, reader, mock_executor):
        """main_records, event_records, choice_records all land in the right fields."""
        main = [{"entity_type": "task", "uid": "t1", "title": "Do thing", "status": "active"}]
        events = [{"uid": "e1", "title": "Workshop", "status": "completed"}]
        choices = [{"uid": "c1", "title": "Chose rest", "principle_titles": ["Balance"]}]

        mock_executor.execute_query.return_value = Result.ok(
            [{"main_records": main, "event_records": events, "choice_records": choices}]
        )
        start, end = _window()

        result = await reader.read("user_alice", start, end)

        data = result.value
        assert len(data.main_records) == 1
        assert data.main_records[0]["uid"] == "t1"
        assert len(data.event_records) == 1
        assert data.event_records[0]["uid"] == "e1"
        assert len(data.choice_records) == 1
        assert data.choice_records[0]["uid"] == "c1"


# ============================================================================
# ERROR PROPAGATION
# ============================================================================


class TestErrorPropagation:
    """Executor errors propagate as Result failures."""

    @pytest.mark.asyncio
    async def test_executor_error_propagates(self, reader, mock_executor):
        """Database error → Result.fail() with the error."""
        mock_executor.execute_query.return_value = Result.fail(
            Errors.database("execute", "Connection refused")
        )
        start, end = _window()

        result = await reader.read("user_alice", start, end)

        assert result.is_error
