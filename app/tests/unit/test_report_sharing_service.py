"""
Unit Tests for ReportsSharingService
=================================

Tests all 6 service methods with mocked Neo4j driver:
- share_ku()
- unshare_ku()
- set_visibility()
- check_access()
- get_shared_with_users()
- get_kus_shared_with_me()

Also tests helper methods:
- _verify_ownership()
- _verify_shareable()
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.services.reports.report_sharing_service import ReportsSharingService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def sharing_service(mock_driver):
    """Create ReportsSharingService with mocked driver."""
    return ReportsSharingService(executor=mock_driver)


# ============================================================================
# SHARE REPORT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_ku_success(sharing_service, mock_driver):
    """Test successfully sharing a report."""
    # Mock verify_ownership (success)
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # _verify_shareable query
        Result.ok([{"status": "completed", "ku_type": "submission"}]),
        # share_ku query
        Result.ok([{"success": True}]),
    ]

    result = await sharing_service.share_report(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True

    # Verify all 3 queries were called
    assert mock_driver.execute_query.call_count == 3


@pytest.mark.asyncio
async def test_share_ku_not_owner(sharing_service, mock_driver):
    """Test sharing fails if user is not owner."""
    # Mock ownership check (failure)
    mock_driver.execute_query.return_value = Result.ok(
        [{"actual_owner": "user_other"}]
    )

    result = await sharing_service.share_report(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_share_ku_not_completed(sharing_service, mock_driver):
    """Test sharing fails if report is not completed."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query (success)
        Result.ok([{"actual_owner": "user_owner"}]),
        # _verify_shareable query (failure - not completed)
        Result.ok([{"status": "processing", "ku_type": "submission"}]),
    ]

    result = await sharing_service.share_report(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)


@pytest.mark.asyncio
async def test_share_ku_not_found(sharing_service, mock_driver):
    """Test sharing fails if report doesn't exist."""
    # Mock ownership check (report not found)
    mock_driver.execute_query.return_value = Result.ok([])

    result = await sharing_service.share_report(
        ku_uid="report_nonexistent",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "not found" in str(result.error)


# ============================================================================
# UNSHARE REPORT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unshare_ku_success(sharing_service, mock_driver):
    """Test successfully unsharing a report."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # unshare query (1 relationship deleted)
        Result.ok([{"deleted_count": 1}]),
    ]

    result = await sharing_service.unshare_report(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_unshare_ku_not_shared(sharing_service, mock_driver):
    """Test unsharing fails if no relationship exists."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # unshare query (0 relationships deleted)
        Result.ok([{"deleted_count": 0}]),
    ]

    result = await sharing_service.unshare_report(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "No sharing relationship found" in str(result.error)


@pytest.mark.asyncio
async def test_unshare_ku_not_owner(sharing_service, mock_driver):
    """Test unsharing fails if user is not owner."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"actual_owner": "user_other"}]
    )

    result = await sharing_service.unshare_report(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


# ============================================================================
# GET SHARED WITH USERS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_shared_with_users_success(sharing_service, mock_driver):
    """Test getting list of users report is shared with."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "user_uid": "user_teacher",
                "user_name": "Teacher Mike",
                "role": "teacher",
                "shared_at": "2026-02-02T12:00:00",
            },
            {
                "user_uid": "user_peer",
                "user_name": "Peer Sarah",
                "role": "peer",
                "shared_at": "2026-02-01T10:00:00",
            },
        ]
    )

    result = await sharing_service.get_shared_with_users(ku_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 2
    assert result.value[0]["user_uid"] == "user_teacher"
    assert result.value[0]["role"] == "teacher"
    assert result.value[1]["user_uid"] == "user_peer"


@pytest.mark.asyncio
async def test_get_shared_with_users_empty(sharing_service, mock_driver):
    """Test getting shared users when none exist."""
    mock_driver.execute_query.return_value = Result.ok([])

    result = await sharing_service.get_shared_with_users(ku_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# GET REPORTS SHARED WITH ME TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_kus_shared_with_me_success(sharing_service, mock_driver):
    """Test getting reports shared with a user."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "ku": {
                    "uid": "report_123",
                    "user_uid": "user_owner",
                    "original_filename": "report.pdf",
                    "ku_type": "submission",
                    "status": "completed",
                    "file_path": "/path/to/file",
                    "file_size": 1024,
                    "file_type": "application/pdf",
                    "processor_type": "llm",
                    "visibility": "shared",
                },
                "role": "teacher",
                "shared_at": "2026-02-02T12:00:00",
            },
        ]
    )

    result = await sharing_service.get_reports_shared_with_me(
        user_uid="user_teacher",
        limit=50,
    )

    assert not result.is_error
    assert len(result.value) == 1
    assert result.value[0].uid == "report_123"
    assert result.value[0].original_filename == "report.pdf"


@pytest.mark.asyncio
async def test_get_kus_shared_with_me_empty(sharing_service, mock_driver):
    """Test getting shared reports when none exist."""
    mock_driver.execute_query.return_value = Result.ok([])

    result = await sharing_service.get_reports_shared_with_me(
        user_uid="user_teacher",
        limit=50,
    )

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# SET VISIBILITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_set_visibility_to_public_success(sharing_service, mock_driver):
    """Test setting report visibility to PUBLIC."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # _verify_shareable query (PUBLIC requires completed)
        Result.ok([{"status": "completed", "ku_type": "submission"}]),
        # set_visibility query
        Result.ok([{"uid": "report_123"}]),
    ]

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PUBLIC,
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_set_visibility_to_private_no_shareable_check(sharing_service, mock_driver):
    """Test setting visibility to PRIVATE doesn't require shareability check."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # No _verify_shareable query (PRIVATE doesn't need it)
        # set_visibility query
        Result.ok([{"uid": "report_123"}]),
    ]

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PRIVATE,
    )

    assert not result.is_error
    assert result.value is True
    # Only 2 queries (ownership + set_visibility, no shareable check)
    assert mock_driver.execute_query.call_count == 2


@pytest.mark.asyncio
async def test_set_visibility_not_owner(sharing_service, mock_driver):
    """Test setting visibility fails if user is not owner."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"actual_owner": "user_other"}]
    )

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        visibility=Visibility.PUBLIC,
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_set_visibility_shared_not_completed(sharing_service, mock_driver):
    """Test setting visibility to SHARED fails if not completed."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        Result.ok([{"actual_owner": "user_owner"}]),
        # _verify_shareable query (not completed)
        Result.ok([{"status": "processing", "ku_type": "submission"}]),
    ]

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.SHARED,
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)


# ============================================================================
# CHECK ACCESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_access_owner(sharing_service, mock_driver):
    """Test owner always has access."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_public(sharing_service, mock_driver):
    """Test anyone can access PUBLIC Ku."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "owner_uid": "user_owner",
                "visibility": "public",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_with_relationship(sharing_service, mock_driver):
    """Test user with SHARES_WITH relationship can access SHARED Ku."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "owner_uid": "user_owner",
                "visibility": "shared",
                "ku_type": "submission",
                "has_share_relationship": True,
            }
        ]
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_without_relationship(sharing_service, mock_driver):
    """Test user without SHARES_WITH relationship cannot access SHARED Ku."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "owner_uid": "user_owner",
                "visibility": "shared",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_unauthorized",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_private_not_owner(sharing_service, mock_driver):
    """Test non-owner cannot access PRIVATE Ku."""
    mock_driver.execute_query.return_value = Result.ok(
        [
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_report_not_found(sharing_service, mock_driver):
    """Test check_access returns error if report doesn't exist."""
    mock_driver.execute_query.return_value = Result.ok([])

    result = await sharing_service.check_access(
        ku_uid="report_nonexistent",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "not found" in str(result.error)


# ============================================================================
# HELPER METHOD TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_verify_ownership_success(sharing_service, mock_driver):
    """Test _verify_ownership succeeds when user is owner."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"actual_owner": "user_owner"}]
    )

    result = await sharing_service._verify_ownership(
        ku_uid="report_123",
        owner_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_ownership_failure(sharing_service, mock_driver):
    """Test _verify_ownership fails when user is not owner."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"actual_owner": "user_other"}]
    )

    result = await sharing_service._verify_ownership(
        ku_uid="report_123",
        owner_uid="user_not_owner",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_verify_shareable_completed(sharing_service, mock_driver):
    """Test _verify_shareable succeeds for completed reports."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"status": "completed", "ku_type": "submission"}]
    )

    result = await sharing_service._verify_shareable(
        ku_uid="report_123",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(sharing_service, mock_driver):
    """Test _verify_shareable fails for non-completed reports."""
    mock_driver.execute_query.return_value = Result.ok(
        [{"status": "processing", "ku_type": "submission"}]
    )

    result = await sharing_service._verify_shareable(
        ku_uid="report_123",
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_ku_database_error(sharing_service, mock_driver):
    """Test share_ku handles database errors gracefully."""
    mock_driver.execute_query.return_value = Result.fail(
        Errors.database("share_ku", "Database connection failed")
    )

    result = await sharing_service.share_report(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_check_access_database_error(sharing_service, mock_driver):
    """Test check_access handles database errors gracefully."""
    mock_driver.execute_query.return_value = Result.fail(
        Errors.database("check_access", "Query timeout")
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "Query timeout" in str(result.error)
