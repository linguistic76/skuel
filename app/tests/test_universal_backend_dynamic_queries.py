#!/usr/bin/env python3
"""
Comprehensive Unit Tests for UniversalBackend Dynamic Queries
===============================================================

Tests the 100% dynamic query pattern with find_by() and list() methods.

Coverage areas:
1. Simple equality filters
2. Comparison operators (gt, lt, gte, lte)
3. String matching (contains)
4. List membership (in)
5. Multiple filter combinations
6. Edge cases and error handling
7. Count with dynamic filters
8. Date range queries
9. Integration with CypherGenerator
"""

from dataclasses import dataclass
from datetime import date, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import EntityStatus, Priority

# ============================================================================
# TEST FIXTURES - Domain Models (avoid "Test" prefix for pytest)
# ============================================================================


@dataclass(frozen=True)
class SampleTask:
    """Sample task model for query testing"""

    uid: str
    title: str
    priority: str
    status: str
    created_at: datetime
    due_date: date | None = None
    estimated_hours: float | None = None
    description: str | None = None
    user_uid: str | None = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_mock_backend():
    """Create a mock universal backend for testing"""
    mock_driver = Mock()
    mock_driver._closed = False  # Prevent _is_driver_closed() from returning truthy Mock
    mock_session = AsyncMock()

    # Create async context manager mock
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_session
    mock_context_manager.__aexit__.return_value = None
    mock_driver.session.return_value = mock_context_manager

    backend = UniversalNeo4jBackend[SampleTask](
        driver=mock_driver, label="SampleTask", entity_class=SampleTask, validate_label=False
    )

    return backend, mock_session


async def setup_mock_query_response(mock_session, records_data):
    """Setup mock query response with given records"""
    mock_result = AsyncMock()
    mock_result.data.return_value = records_data
    mock_session.run.return_value = mock_result
    return mock_result


# ============================================================================
# TEST: find_by() - Simple equality
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_simple_equality():
    """Test find_by with simple equality filters"""
    backend, mock_session = create_mock_backend()

    # Setup mock response with all required fields
    await setup_mock_query_response(
        mock_session,
        [
            {
                "n": {
                    "uid": "task-1",
                    "title": "High Priority Task",
                    "priority": "high",
                    "status": "in_progress",
                    "created_at": "2025-10-15T12:00:00",
                }
            }
        ],
    )

    # Execute
    result = await backend.find_by(priority="high", status="active")

    # Verify
    assert result.is_ok
    assert mock_session.run.called
    call_args = mock_session.run.call_args

    # Check generated Cypher
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.priority = $priority" in cypher
    assert "n.status = $status" in cypher
    assert params["priority"] == "high"
    assert params["status"] == "active"


@pytest.mark.asyncio
async def test_find_by_single_field():
    """Test find_by with single field filter"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(uid="task-123")

    assert result.is_ok
    assert mock_session.run.called


# ============================================================================
# TEST: find_by() - Comparison operators
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_greater_than():
    """Test find_by with greater than operator"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(estimated_hours__gt=5.0)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.estimated_hours > $estimated_hours_gt" in cypher
    assert params["estimated_hours_gt"] == 5.0


@pytest.mark.asyncio
async def test_find_by_less_than():
    """Test find_by with less than operator"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(estimated_hours__lt=10.0)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "n.estimated_hours < $estimated_hours_lt" in cypher


@pytest.mark.asyncio
async def test_find_by_gte():
    """Test find_by with greater than or equal operator"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(due_date__gte=date(2025, 10, 15))

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.due_date >= $due_date_gte" in cypher
    assert params["due_date_gte"] == "2025-10-15"  # Converted to ISO string


@pytest.mark.asyncio
async def test_find_by_lte():
    """Test find_by with less than or equal operator"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(estimated_hours__lte=8.0)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "n.estimated_hours <= $estimated_hours_lte" in cypher


# ============================================================================
# TEST: find_by() - String operators
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_contains():
    """Test find_by with contains operator for string matching"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(title__contains="urgent")

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.title CONTAINS $title_contains" in cypher
    assert params["title_contains"] == "urgent"


@pytest.mark.asyncio
async def test_find_by_contains_case_sensitive():
    """Test that contains is case-sensitive (Cypher default)"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(description__contains="URGENT")

    assert result.is_ok
    call_args = mock_session.run.call_args
    params = call_args[0][1]

    assert params["description_contains"] == "URGENT"


# ============================================================================
# TEST: find_by() - List membership (IN operator)
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_in_operator():
    """Test find_by with IN operator for list membership"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(priority__in=["high", "urgent", "critical"])

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.priority IN $priority_in" in cypher
    assert params["priority_in"] == ["high", "urgent", "critical"]


@pytest.mark.asyncio
async def test_find_by_in_empty_list():
    """Test find_by with empty IN list"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(priority__in=[])

    assert result.is_ok
    call_args = mock_session.run.call_args
    params = call_args[0][1]

    assert params["priority_in"] == []


# ============================================================================
# TEST: find_by() - Multiple filters combined
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_multiple_filters():
    """Test find_by with multiple filter types combined"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(
        priority="high",
        status="in_progress",
        due_date__gte=date(2025, 10, 15),
        estimated_hours__lt=5.0,
        title__contains="urgent",
    )

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    # All filters should be combined with AND
    assert "n.priority = $priority" in cypher
    assert "n.status = $status" in cypher
    assert "n.due_date >= $due_date_gte" in cypher
    assert "n.estimated_hours < $estimated_hours_lt" in cypher
    assert "n.title CONTAINS $title_contains" in cypher

    assert params["priority"] == "high"
    assert params["title_contains"] == "urgent"


@pytest.mark.asyncio
async def test_find_by_range_query():
    """Test find_by with range query (between values)"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(estimated_hours__gte=2.0, estimated_hours__lte=8.0)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    # Both conditions should be present
    assert "n.estimated_hours >= $estimated_hours_gte" in cypher
    assert "n.estimated_hours <= $estimated_hours_lte" in cypher


# ============================================================================
# TEST: find_by() - Edge cases
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_no_filters_returns_list():
    """Test find_by with no filters falls back to list()"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by()

    assert result.is_ok
    # Should call list() internally
    assert mock_session.run.called


@pytest.mark.asyncio
async def test_find_by_custom_limit():
    """Test find_by with custom limit parameter"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(priority="high", limit=50)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "LIMIT $limit" in cypher
    assert params["limit"] == 50


@pytest.mark.asyncio
async def test_find_by_invalid_field_skipped():
    """Test that invalid fields are skipped (logged as warning)"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    # CypherGenerator should skip invalid fields
    result = await backend.find_by(priority="high", nonexistent_field="value")

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    # Valid field should be included
    assert "n.priority = $priority" in cypher
    # Invalid field should be skipped
    assert "nonexistent_field" not in cypher


@pytest.mark.asyncio
async def test_find_by_unknown_operator_skipped():
    """Test that unknown operators are skipped"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(priority__unknown_op="high", status="active")

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    # Valid field should be included
    assert "n.status = $status" in cypher
    # Unknown operator should be skipped
    assert "unknown_op" not in cypher.lower()


# ============================================================================
# TEST: list() with dynamic filters
# ============================================================================


@pytest.mark.asyncio
async def test_list_with_filters():
    """Test list() method with dynamic filters"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.list(filters={"priority": "high", "status": "in_progress"}, limit=25)

    assert result.is_ok
    assert mock_session.run.called
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "n.priority = $priority" in cypher
    assert "n.status = $status" in cypher


@pytest.mark.asyncio
async def test_list_with_sorting():
    """Test list() with sorting"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.list(sort_by="due_date", sort_order="desc", limit=50)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "ORDER BY n.due_date DESC" in cypher


@pytest.mark.asyncio
async def test_list_with_pagination():
    """Test list() with pagination (offset + limit)"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.list(offset=25, limit=25)

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "SKIP $skip" in cypher  # CypherGenerator uses 'skip' not 'offset'
    assert "LIMIT $limit" in cypher
    assert params["skip"] == 25  # Backend maps offset -> skip
    assert params["limit"] == 25


# ============================================================================
# TEST: count() with dynamic filters
# ============================================================================


@pytest.mark.asyncio
async def test_count_with_filters():
    """Test count() method with dynamic filters.

    count() uses UnifiedQueryBuilder which calls execute_query(), and
    execute_query() uses session.run() + result.data() (returns list of dicts).
    """
    backend, mock_session = create_mock_backend()

    mock_result = AsyncMock()
    mock_result.data.return_value = [{"count": 42}]
    mock_session.run.return_value = mock_result

    result = await backend.count(priority="high", status="completed")

    assert result.is_ok
    assert result.value == 42
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "RETURN count(n) as count" in cypher
    assert "n.priority = $priority" in cypher
    assert "n.status = $status" in cypher


@pytest.mark.asyncio
async def test_count_no_filters():
    """Test count() without filters"""
    backend, mock_session = create_mock_backend()

    mock_result = AsyncMock()
    mock_result.data.return_value = [{"count": 100}]
    mock_session.run.return_value = mock_result

    result = await backend.count()

    assert result.is_ok
    assert result.value == 100
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "RETURN count(n) as count" in cypher


@pytest.mark.asyncio
async def test_count_with_comparison_operators():
    """Test count() with comparison operators"""
    backend, mock_session = create_mock_backend()

    mock_result = AsyncMock()
    mock_result.data.return_value = [{"count": 15}]
    mock_session.run.return_value = mock_result

    result = await backend.count(estimated_hours__gte=2.0, estimated_hours__lte=8.0)

    assert result.is_ok
    assert result.value == 15


# ============================================================================
# TEST: Date range queries
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_date_range_filters():
    """Test date range using comparison operators"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(
        due_date__gte=date(2025, 10, 1), due_date__lte=date(2025, 10, 31)
    )

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    assert "n.due_date >= $due_date_gte" in cypher
    assert "n.due_date <= $due_date_lte" in cypher
    assert params["due_date_gte"] == "2025-10-01"
    assert params["due_date_lte"] == "2025-10-31"


@pytest.mark.asyncio
async def test_find_by_date_range_backend():
    """Test find_by_date_range() method"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by_date_range(
        start_date=date(2025, 10, 1), end_date=date(2025, 10, 31), date_field="due_date"
    )

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]

    assert "date(n.due_date) >= date($start_date)" in cypher
    assert "date(n.due_date) <= date($end_date)" in cypher


# ============================================================================
# TEST: Type conversions
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_with_enum_values():
    """Test that enum values are automatically converted"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    # Using enum values directly
    result = await backend.find_by(priority=Priority.HIGH, status=EntityStatus.ACTIVE)

    assert result.is_ok
    call_args = mock_session.run.call_args
    params = call_args[0][1]

    # Enums should be converted to .value
    assert params["priority"] == "high"
    assert params["status"] == "active"


@pytest.mark.asyncio
async def test_find_by_with_datetime():
    """Test that datetime objects are converted to ISO strings"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    test_dt = datetime(2025, 10, 15, 14, 30, 0)

    result = await backend.find_by(created_at=test_dt)

    assert result.is_ok
    call_args = mock_session.run.call_args
    params = call_args[0][1]

    assert params["created_at"] == test_dt.isoformat()


# ============================================================================
# TEST: Error handling
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_database_error():
    """Test that database errors are handled gracefully"""
    backend, mock_session = create_mock_backend()

    # Simulate database error
    mock_session.run.side_effect = Exception("Database connection failed")

    result = await backend.find_by(priority="high")

    # Should return error Result
    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_find_by_empty_result():
    """Test find_by with no matching results"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    result = await backend.find_by(priority="nonexistent")

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_count_zero_results():
    """Test count() returning zero"""
    backend, mock_session = create_mock_backend()

    mock_result = AsyncMock()
    mock_result.data.return_value = [{"count": 0}]
    mock_session.run.return_value = mock_result

    result = await backend.count(priority="nonexistent")

    assert result.is_ok
    assert result.value == 0


# ============================================================================
# TEST: Integration with CypherGenerator
# ============================================================================


@pytest.mark.asyncio
async def test_find_by_uses_cypher_generator():
    """Test that find_by() uses UnifiedQueryBuilder internally"""
    backend, mock_session = create_mock_backend()

    await setup_mock_query_response(mock_session, [])

    # UniversalBackend now uses UnifiedQueryBuilder instead of CypherGenerator directly
    # The test verifies that find_by() still generates correct queries
    result = await backend.find_by(priority="high")

    assert result.is_ok
    call_args = mock_session.run.call_args
    cypher = call_args[0][0]
    params = call_args[0][1]

    # Verify correct Cypher was generated (via UnifiedQueryBuilder → CypherGenerator)
    assert "MATCH (n:SampleTask)" in cypher
    assert "n.priority = $priority" in cypher
    assert params["priority"] == "high"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
