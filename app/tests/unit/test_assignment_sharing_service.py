"""
Unit Tests for AssignmentSharingService
========================================

Tests all 6 service methods with mocked Neo4j driver:
- share_assignment()
- unshare_assignment()
- set_visibility()
- check_access()
- get_shared_with_users()
- get_assignments_shared_with_me()

Also tests helper methods:
- _verify_ownership()
- _verify_shareable()
"""

from unittest.mock import MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.services.assignments.assignment_sharing_service import AssignmentSharingService


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    driver.execute_query = MagicMock()
    return driver


@pytest.fixture
def sharing_service(mock_driver):
    """Create AssignmentSharingService with mocked driver."""
    return AssignmentSharingService(driver=mock_driver)


# ============================================================================
# SHARE ASSIGNMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_assignment_success(sharing_service, mock_driver):
    """Test successfully sharing an assignment."""
    # Mock verify_ownership (success)
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        ([{"actual_owner": "user_owner"}], None, None),
        # _verify_shareable query
        ([{"status": "completed"}], None, None),
        # share_assignment query
        ([{"success": True}], None, None),
    ]

    result = await sharing_service.share_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True

    # Verify all 3 queries were called
    assert mock_driver.execute_query.call_count == 3


@pytest.mark.asyncio
async def test_share_assignment_not_owner(sharing_service, mock_driver):
    """Test sharing fails if user is not owner."""
    # Mock ownership check (failure)
    mock_driver.execute_query.return_value = (
        [{"actual_owner": "user_other"}],
        None,
        None,
    )

    result = await sharing_service.share_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_share_assignment_not_completed(sharing_service, mock_driver):
    """Test sharing fails if assignment is not completed."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query (success)
        ([{"actual_owner": "user_owner"}], None, None),
        # _verify_shareable query (failure - not completed)
        ([{"status": "processing"}], None, None),
    ]

    result = await sharing_service.share_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Only completed assignments" in str(result.error)


@pytest.mark.asyncio
async def test_share_assignment_not_found(sharing_service, mock_driver):
    """Test sharing fails if assignment doesn't exist."""
    # Mock ownership check (assignment not found)
    mock_driver.execute_query.return_value = ([], None, None)

    result = await sharing_service.share_assignment(
        assignment_uid="assignment_nonexistent",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "not found" in str(result.error)


# ============================================================================
# UNSHARE ASSIGNMENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unshare_assignment_success(sharing_service, mock_driver):
    """Test successfully unsharing an assignment."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        ([{"actual_owner": "user_owner"}], None, None),
        # unshare query (1 relationship deleted)
        ([{"deleted_count": 1}], None, None),
    ]

    result = await sharing_service.unshare_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_unshare_assignment_not_shared(sharing_service, mock_driver):
    """Test unsharing fails if no relationship exists."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        ([{"actual_owner": "user_owner"}], None, None),
        # unshare query (0 relationships deleted)
        ([{"deleted_count": 0}], None, None),
    ]

    result = await sharing_service.unshare_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "No sharing relationship found" in str(result.error)


@pytest.mark.asyncio
async def test_unshare_assignment_not_owner(sharing_service, mock_driver):
    """Test unsharing fails if user is not owner."""
    mock_driver.execute_query.return_value = (
        [{"actual_owner": "user_other"}],
        None,
        None,
    )

    result = await sharing_service.unshare_assignment(
        assignment_uid="assignment_123",
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
    """Test getting list of users assignment is shared with."""
    mock_driver.execute_query.return_value = (
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
        ],
        None,
        None,
    )

    result = await sharing_service.get_shared_with_users(assignment_uid="assignment_123")

    assert not result.is_error
    assert len(result.value) == 2
    assert result.value[0]["user_uid"] == "user_teacher"
    assert result.value[0]["role"] == "teacher"
    assert result.value[1]["user_uid"] == "user_peer"


@pytest.mark.asyncio
async def test_get_shared_with_users_empty(sharing_service, mock_driver):
    """Test getting shared users when none exist."""
    mock_driver.execute_query.return_value = ([], None, None)

    result = await sharing_service.get_shared_with_users(assignment_uid="assignment_123")

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# GET ASSIGNMENTS SHARED WITH ME TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_assignments_shared_with_me_success(sharing_service, mock_driver):
    """Test getting assignments shared with a user."""
    mock_driver.execute_query.return_value = (
        [
            {
                "assignment": {
                    "uid": "assignment_123",
                    "user_uid": "user_owner",
                    "original_filename": "report.pdf",
                    "assignment_type": "report",
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
        ],
        None,
        None,
    )

    result = await sharing_service.get_assignments_shared_with_me(
        user_uid="user_teacher",
        limit=50,
    )

    assert not result.is_error
    assert len(result.value) == 1
    assert result.value[0].uid == "assignment_123"
    assert result.value[0].original_filename == "report.pdf"


@pytest.mark.asyncio
async def test_get_assignments_shared_with_me_empty(sharing_service, mock_driver):
    """Test getting shared assignments when none exist."""
    mock_driver.execute_query.return_value = ([], None, None)

    result = await sharing_service.get_assignments_shared_with_me(
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
    """Test setting assignment visibility to PUBLIC."""
    mock_driver.execute_query.side_effect = [
        # _verify_ownership query
        ([{"actual_owner": "user_owner"}], None, None),
        # _verify_shareable query (PUBLIC requires completed)
        ([{"status": "completed"}], None, None),
        # set_visibility query
        ([{"uid": "assignment_123"}], None, None),
    ]

    result = await sharing_service.set_visibility(
        assignment_uid="assignment_123",
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
        ([{"actual_owner": "user_owner"}], None, None),
        # No _verify_shareable query (PRIVATE doesn't need it)
        # set_visibility query
        ([{"uid": "assignment_123"}], None, None),
    ]

    result = await sharing_service.set_visibility(
        assignment_uid="assignment_123",
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
    mock_driver.execute_query.return_value = (
        [{"actual_owner": "user_other"}],
        None,
        None,
    )

    result = await sharing_service.set_visibility(
        assignment_uid="assignment_123",
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
        ([{"actual_owner": "user_owner"}], None, None),
        # _verify_shareable query (not completed)
        ([{"status": "processing"}], None, None),
    ]

    result = await sharing_service.set_visibility(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        visibility=Visibility.SHARED,
    )

    assert result.is_error
    assert "Only completed assignments" in str(result.error)


# ============================================================================
# CHECK ACCESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_access_owner(sharing_service, mock_driver):
    """Test owner always has access."""
    mock_driver.execute_query.return_value = (
        [
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "has_share_relationship": False,
            }
        ],
        None,
        None,
    )

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_public(sharing_service, mock_driver):
    """Test anyone can access PUBLIC assignments."""
    mock_driver.execute_query.return_value = (
        [
            {
                "owner_uid": "user_owner",
                "visibility": "public",
                "has_share_relationship": False,
            }
        ],
        None,
        None,
    )

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_with_relationship(sharing_service, mock_driver):
    """Test user with SHARES_WITH relationship can access SHARED assignment."""
    mock_driver.execute_query.return_value = (
        [
            {
                "owner_uid": "user_owner",
                "visibility": "shared",
                "has_share_relationship": True,
            }
        ],
        None,
        None,
    )

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_without_relationship(sharing_service, mock_driver):
    """Test user without SHARES_WITH relationship cannot access SHARED assignment."""
    mock_driver.execute_query.return_value = (
        [
            {
                "owner_uid": "user_owner",
                "visibility": "shared",
                "has_share_relationship": False,
            }
        ],
        None,
        None,
    )

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_unauthorized",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_private_not_owner(sharing_service, mock_driver):
    """Test non-owner cannot access PRIVATE assignment."""
    mock_driver.execute_query.return_value = (
        [
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "has_share_relationship": False,
            }
        ],
        None,
        None,
    )

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_assignment_not_found(sharing_service, mock_driver):
    """Test check_access returns error if assignment doesn't exist."""
    mock_driver.execute_query.return_value = ([], None, None)

    result = await sharing_service.check_access(
        assignment_uid="assignment_nonexistent",
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
    mock_driver.execute_query.return_value = (
        [{"actual_owner": "user_owner"}],
        None,
        None,
    )

    result = await sharing_service._verify_ownership(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_ownership_failure(sharing_service, mock_driver):
    """Test _verify_ownership fails when user is not owner."""
    mock_driver.execute_query.return_value = (
        [{"actual_owner": "user_other"}],
        None,
        None,
    )

    result = await sharing_service._verify_ownership(
        assignment_uid="assignment_123",
        owner_uid="user_not_owner",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_verify_shareable_completed(sharing_service, mock_driver):
    """Test _verify_shareable succeeds for completed assignments."""
    mock_driver.execute_query.return_value = (
        [{"status": "completed"}],
        None,
        None,
    )

    result = await sharing_service._verify_shareable(
        assignment_uid="assignment_123",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(sharing_service, mock_driver):
    """Test _verify_shareable fails for non-completed assignments."""
    mock_driver.execute_query.return_value = (
        [{"status": "processing"}],
        None,
        None,
    )

    result = await sharing_service._verify_shareable(
        assignment_uid="assignment_123",
    )

    assert result.is_error
    assert "Only completed assignments" in str(result.error)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_assignment_database_error(sharing_service, mock_driver):
    """Test share_assignment handles database errors gracefully."""
    mock_driver.execute_query.side_effect = Exception("Database connection failed")

    result = await sharing_service.share_assignment(
        assignment_uid="assignment_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_check_access_database_error(sharing_service, mock_driver):
    """Test check_access handles database errors gracefully."""
    mock_driver.execute_query.side_effect = Exception("Query timeout")

    result = await sharing_service.check_access(
        assignment_uid="assignment_123",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "Query timeout" in str(result.error)
