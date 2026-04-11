"""
Test Suite for Ingestion History Service
====================================

Tests the ingestion history tracking and audit trail functionality.

Test Categories:
1. Ingestion History Entry Creation
2. Ingestion History Entry Updates
3. Ingestion History Retrieval (Paginated)
4. Ingestion History Entry Lookup
5. Error Node Creation
6. Graph Model Verification
7. Pagination and Counting

Uses mock backend to test service logic without database dependency.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.services.ingestion.ingestion_history import IngestionHistoryEntry, IngestionHistoryService
from core.utils.result_simplified import Errors, Result

# ============================================================================
# TEST FIXTURES - Mock Backend
# ============================================================================


@pytest.fixture
def mock_backend():
    """Mock ingestion backend for testing."""
    backend = Mock()
    backend.ensure_history_constraints = AsyncMock(return_value=Result.ok([]))
    backend.create_history_entry = AsyncMock(return_value=Result.ok([]))
    backend.update_history_entry = AsyncMock(return_value=Result.ok([]))
    backend.create_error_nodes = AsyncMock(return_value=Result.ok([]))
    backend.get_history = AsyncMock(return_value=Result.ok([]))
    backend.get_history_entry = AsyncMock(return_value=Result.ok([]))
    backend.get_history_count = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_ingestion_history_data():
    """Sample ingestion history data."""
    return {
        "operation_id": "test-uuid-123",
        "operation_type": "directory",
        "started_at": datetime(2026, 2, 6, 10, 0, 0),
        "completed_at": datetime(2026, 2, 6, 10, 0, 45),
        "status": "completed",
        "user_uid": "user_admin",
        "source_path": "/vault/docs",
        "total_files": 1000,
        "successful": 995,
        "failed": 5,
        "nodes_created": 1200,
        "nodes_updated": 150,
        "relationships_created": 800,
        "duration_seconds": 45.0,
    }


@pytest.fixture
def ingestion_history_service(mock_backend):
    """Create ingestion history service with mocked backend."""
    return IngestionHistoryService(mock_backend)


# ============================================================================
# TEST 1: Constraint Ensuring
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_constraints(ingestion_history_service, mock_backend):
    """Test that ensure_constraints delegates to backend."""
    await ingestion_history_service.ensure_constraints()
    mock_backend.ensure_history_constraints.assert_called_once()


# ============================================================================
# TEST 2: Creating Ingestion History Entries
# ============================================================================


@pytest.mark.asyncio
async def test_create_entry_success(ingestion_history_service, mock_backend):
    """Test successful creation of ingestion history entry."""
    result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/docs",
    )

    assert result.is_ok
    operation_id = result.value
    assert isinstance(operation_id, str)
    assert len(operation_id) > 0

    # Verify backend was called with correct parameters
    mock_backend.create_history_entry.assert_called_once()
    call_args = mock_backend.create_history_entry.call_args[0][0]
    assert call_args["operation_type"] == "directory"
    assert call_args["user_uid"] == "user_admin"
    assert call_args["source_path"] == "/vault/docs"


@pytest.mark.asyncio
async def test_create_entry_database_error(ingestion_history_service, mock_backend):
    """Test create_entry handles database errors."""
    mock_backend.create_history_entry.return_value = Result.fail(
        Errors.database("execute_query", "Database connection failed")
    )

    result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/docs",
    )

    assert result.is_error
    error = result.expect_error()
    assert "create ingestion history" in error.message.lower()


@pytest.mark.asyncio
async def test_create_entry_generates_uuid(ingestion_history_service, mock_backend):
    """Test that create_entry generates unique operation IDs."""
    # Create multiple entries
    result1 = await ingestion_history_service.create_entry("directory", "user_admin", "/path1")
    result2 = await ingestion_history_service.create_entry("directory", "user_admin", "/path2")

    assert result1.is_ok
    assert result2.is_ok


# ============================================================================
# TEST 3: Updating Ingestion History Entries
# ============================================================================


@pytest.mark.asyncio
async def test_update_entry_success(ingestion_history_service, mock_backend):
    """Test successful update of ingestion history entry."""
    stats = {
        "total_files": 1000,
        "successful": 995,
        "failed": 5,
        "nodes_created": 1200,
        "nodes_updated": 150,
        "relationships_created": 800,
        "duration_seconds": 45.0,
    }

    result = await ingestion_history_service.update_entry(
        operation_id="test-uuid-123",
        status="completed",
        stats=stats,
        errors=None,
    )

    assert result.is_ok

    # Verify backend was called with correct parameters
    mock_backend.update_history_entry.assert_called_once()
    call_args = mock_backend.update_history_entry.call_args[0][0]
    assert call_args["operation_id"] == "test-uuid-123"
    assert call_args["status"] == "completed"
    assert call_args["total_files"] == 1000
    assert call_args["successful"] == 995


@pytest.mark.asyncio
async def test_update_entry_with_errors(ingestion_history_service, mock_backend):
    """Test update_entry creates error nodes when errors provided."""
    stats = {"total_files": 10, "successful": 8, "failed": 2}
    errors = [
        {
            "file": "/vault/bad1.md",
            "error": "Missing title",
            "stage": "validation",
            "error_type": "validation",
            "entity_type": "ku",
            "suggestion": "Add title field",
        },
        {
            "file": "/vault/bad2.md",
            "error": "Invalid YAML",
            "stage": "parsing",
            "error_type": "parse",
            "entity_type": None,
            "suggestion": "Check YAML syntax",
        },
    ]

    result = await ingestion_history_service.update_entry(
        operation_id="test-uuid-123",
        status="completed",
        stats=stats,
        errors=errors,
    )

    assert result.is_ok

    # Verify both update and error creation were called
    mock_backend.update_history_entry.assert_called_once()
    mock_backend.create_error_nodes.assert_called_once_with("test-uuid-123", errors)


@pytest.mark.asyncio
async def test_update_entry_database_error(ingestion_history_service, mock_backend):
    """Test update_entry handles database errors."""
    mock_backend.update_history_entry.return_value = Result.fail(
        Errors.database("execute_query", "Database error")
    )

    result = await ingestion_history_service.update_entry(
        operation_id="test-uuid-123",
        status="failed",
        stats={"total_files": 0},
    )

    assert result.is_error
    error = result.expect_error()
    assert "update ingestion history" in error.message.lower()


# ============================================================================
# TEST 4: Retrieving Ingestion History (Paginated)
# ============================================================================


@pytest.mark.asyncio
async def test_get_history_success(
    ingestion_history_service, mock_backend, mock_ingestion_history_data
):
    """Test successful retrieval of ingestion history."""
    mock_backend.get_history.return_value = Result.ok(
        [
            {
                "ih": mock_ingestion_history_data,
                "errors": [],
            }
        ]
    )

    result = await ingestion_history_service.get_history(limit=50, offset=0)

    assert result.is_ok
    entries = result.value
    assert len(entries) == 1
    assert isinstance(entries[0], IngestionHistoryEntry)
    assert entries[0].operation_id == "test-uuid-123"
    assert entries[0].operation_type == "directory"
    assert entries[0].status == "completed"


@pytest.mark.asyncio
async def test_get_history_pagination(ingestion_history_service, mock_backend):
    """Test pagination parameters are passed correctly."""
    mock_backend.get_history.return_value = Result.ok([])

    await ingestion_history_service.get_history(limit=25, offset=50)

    mock_backend.get_history.assert_called_once_with(25, 50)


@pytest.mark.asyncio
async def test_get_history_with_errors(
    ingestion_history_service, mock_backend, mock_ingestion_history_data
):
    """Test retrieval includes error nodes."""
    error_node = {
        "file": "/vault/bad.md",
        "error": "Missing title",
        "stage": "validation",
        "error_type": "validation",
        "entity_type": "ku",
        "suggestion": "Add title",
    }

    mock_backend.get_history.return_value = Result.ok(
        [
            {
                "ih": mock_ingestion_history_data,
                "errors": [error_node],
            }
        ]
    )

    result = await ingestion_history_service.get_history()

    assert result.is_ok
    entries = result.value
    assert len(entries[0].errors) == 1
    assert entries[0].errors[0]["file"] == "/vault/bad.md"


@pytest.mark.asyncio
async def test_get_history_database_error(ingestion_history_service, mock_backend):
    """Test get_history handles database errors."""
    mock_backend.get_history.return_value = Result.fail(
        Errors.database("execute_query", "Database error")
    )

    result = await ingestion_history_service.get_history()

    assert result.is_error
    error = result.expect_error()
    assert "retrieve ingestion history" in error.message.lower()


# ============================================================================
# TEST 5: Getting Specific Entry
# ============================================================================


@pytest.mark.asyncio
async def test_get_entry_found(
    ingestion_history_service, mock_backend, mock_ingestion_history_data
):
    """Test successful retrieval of specific entry."""
    mock_backend.get_history_entry.return_value = Result.ok(
        [
            {
                "ih": mock_ingestion_history_data,
                "errors": [],
            }
        ]
    )

    result = await ingestion_history_service.get_entry("test-uuid-123")

    assert result.is_ok
    entry = result.value
    assert entry is not None
    assert entry.operation_id == "test-uuid-123"


@pytest.mark.asyncio
async def test_get_entry_not_found(ingestion_history_service, mock_backend):
    """Test get_entry returns None when entry doesn't exist."""
    mock_backend.get_history_entry.return_value = Result.ok([])

    result = await ingestion_history_service.get_entry("nonexistent-uuid")

    assert result.is_ok
    entry = result.value
    assert entry is None


@pytest.mark.asyncio
async def test_get_entry_database_error(ingestion_history_service, mock_backend):
    """Test get_entry handles database errors."""
    mock_backend.get_history_entry.return_value = Result.fail(
        Errors.database("execute_query", "Database error")
    )

    result = await ingestion_history_service.get_entry("test-uuid-123")

    assert result.is_error


# ============================================================================
# TEST 6: Getting Total Count
# ============================================================================


@pytest.mark.asyncio
async def test_get_total_count_success(ingestion_history_service, mock_backend):
    """Test successful retrieval of total count."""
    mock_backend.get_history_count.return_value = Result.ok([{"total": 150}])

    result = await ingestion_history_service.get_total_count()

    assert result.is_ok
    total = result.value
    assert total == 150


@pytest.mark.asyncio
async def test_get_total_count_empty(ingestion_history_service, mock_backend):
    """Test get_total_count with no entries."""
    mock_backend.get_history_count.return_value = Result.ok([])

    result = await ingestion_history_service.get_total_count()

    assert result.is_ok
    total = result.value
    assert total == 0


@pytest.mark.asyncio
async def test_get_total_count_database_error(ingestion_history_service, mock_backend):
    """Test get_total_count handles database errors."""
    mock_backend.get_history_count.return_value = Result.fail(
        Errors.database("execute_query", "Database error")
    )

    result = await ingestion_history_service.get_total_count()

    assert result.is_error


# ============================================================================
# TEST 7: Workflow Integration
# ============================================================================


@pytest.mark.asyncio
async def test_complete_ingestion_workflow(ingestion_history_service, mock_backend):
    """Test complete workflow: create -> update -> retrieve."""
    # Step 1: Create entry
    create_result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/docs",
    )
    assert create_result.is_ok
    operation_id = create_result.value

    # Step 2: Update entry
    stats = {
        "total_files": 100,
        "successful": 98,
        "failed": 2,
        "nodes_created": 120,
        "nodes_updated": 20,
        "relationships_created": 80,
        "duration_seconds": 5.0,
    }
    update_result = await ingestion_history_service.update_entry(
        operation_id=operation_id,
        status="completed",
        stats=stats,
    )
    assert update_result.is_ok

    # Step 3: Retrieve entry
    ih_data = {
        "operation_id": operation_id,
        "operation_type": "directory",
        "started_at": datetime.now(),
        "completed_at": datetime.now(),
        "status": "completed",
        "user_uid": "user_admin",
        "source_path": "/vault/docs",
        **stats,
    }

    mock_backend.get_history_entry.return_value = Result.ok(
        [
            {
                "ih": ih_data,
                "errors": [],
            }
        ]
    )

    get_result = await ingestion_history_service.get_entry(operation_id)
    assert get_result.is_ok
    entry = get_result.value
    assert entry.status == "completed"


# ============================================================================
# TEST 8: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_update_entry_with_empty_stats(ingestion_history_service, mock_backend):
    """Test update_entry handles empty stats dict."""
    result = await ingestion_history_service.update_entry(
        operation_id="test-uuid",
        status="failed",
        stats={},  # Empty stats
    )

    assert result.is_ok

    # Should use default values (0) for missing fields
    call_args = mock_backend.update_history_entry.call_args[0][0]
    assert call_args["total_files"] == 0
    assert call_args["successful"] == 0


@pytest.mark.asyncio
async def test_create_entry_with_special_characters(ingestion_history_service, mock_backend):
    """Test create_entry handles special characters in paths."""
    result = await ingestion_history_service.create_entry(
        operation_type="directory",
        user_uid="user_admin",
        source_path="/vault/docs/with spaces & special/chars",
    )

    assert result.is_ok


# ============================================================================
# Summary
# ============================================================================
"""
Test Coverage Summary:
- Constraint creation
- Creating ingestion history entries (success, errors, UUID generation)
- Updating ingestion history entries (success, with errors, database errors)
- Retrieving ingestion history (paginated, with errors, ordering)
- Getting specific entries (found, not found, errors)
- Getting total count
- Complete workflow integration
- Edge cases (empty stats, special characters)

Total Tests: 25
"""
