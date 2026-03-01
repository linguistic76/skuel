"""
Unit Tests for SubmissionsSharingService
=================================

Tests all 6 service methods with a mocked SubmissionsBackend:
- share_submission()
- unshare_submission()
- set_visibility()
- check_access()
- get_shared_with_users()
- get_submissions_shared_with_me()

Also tests helper methods:
- _verify_ownership()
- _verify_shareable()
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.services.submissions.submissions_sharing_service import SubmissionsSharingService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_backend():
    """Create a mock SubmissionsBackend with all sharing methods as AsyncMocks."""
    backend = MagicMock()
    backend.verify_ownership = AsyncMock()
    backend.verify_shareable = AsyncMock()
    backend.share_submission = AsyncMock()
    backend.unshare_submission = AsyncMock()
    backend.get_shared_with_users = AsyncMock()
    backend.get_submissions_shared_with_me = AsyncMock()
    backend.set_visibility = AsyncMock()
    backend.check_access = AsyncMock()
    return backend


@pytest.fixture
def sharing_service(mock_backend):
    """Create SubmissionsSharingService with mocked backend."""
    return SubmissionsSharingService(backend=mock_backend)


# ============================================================================
# SHARE REPORT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_ku_success(sharing_service, mock_backend):
    """Test successfully sharing a report."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.verify_shareable.return_value = Result.ok(True)
    mock_backend.share_submission.return_value = Result.ok(True)

    result = await sharing_service.share_submission(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True
    mock_backend.verify_ownership.assert_called_once_with("report_123", "user_owner")
    mock_backend.verify_shareable.assert_called_once_with("report_123")
    mock_backend.share_submission.assert_called_once_with(
        "report_123", "user_teacher", "teacher"
    )


@pytest.mark.asyncio
async def test_share_ku_not_owner(sharing_service, mock_backend):
    """Test sharing fails if user is not owner."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.validation("User user_not_owner does not own entity report_123")
    )

    result = await sharing_service.share_submission(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)
    mock_backend.verify_shareable.assert_not_called()


@pytest.mark.asyncio
async def test_share_ku_not_completed(sharing_service, mock_backend):
    """Test sharing fails if report is not completed."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.verify_shareable.return_value = Result.fail(
        Errors.validation("Only completed Ku can be shared. Current status: processing")
    )

    result = await sharing_service.share_submission(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)
    mock_backend.share_submission.assert_not_called()


@pytest.mark.asyncio
async def test_share_ku_not_found(sharing_service, mock_backend):
    """Test sharing fails if report doesn't exist."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.not_found(resource="Entity", identifier="report_nonexistent")
    )

    result = await sharing_service.share_submission(
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
async def test_unshare_ku_success(sharing_service, mock_backend):
    """Test successfully unsharing a report."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.unshare_submission.return_value = Result.ok(True)

    result = await sharing_service.unshare_submission(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_unshare_ku_not_shared(sharing_service, mock_backend):
    """Test unsharing fails if no relationship exists."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.unshare_submission.return_value = Result.fail(
        Errors.not_found(
            "No sharing relationship found between user_teacher and report_123"
        )
    )

    result = await sharing_service.unshare_submission(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "No sharing relationship found" in str(result.error)


@pytest.mark.asyncio
async def test_unshare_ku_not_owner(sharing_service, mock_backend):
    """Test unsharing fails if user is not owner."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.validation("User user_not_owner does not own entity report_123")
    )

    result = await sharing_service.unshare_submission(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)
    mock_backend.unshare_submission.assert_not_called()


# ============================================================================
# GET SHARED WITH USERS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_shared_with_users_success(sharing_service, mock_backend):
    """Test getting list of users report is shared with."""
    mock_backend.get_shared_with_users.return_value = Result.ok(
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
async def test_get_shared_with_users_empty(sharing_service, mock_backend):
    """Test getting shared users when none exist."""
    mock_backend.get_shared_with_users.return_value = Result.ok([])

    result = await sharing_service.get_shared_with_users(ku_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# GET REPORTS SHARED WITH ME TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_kus_shared_with_me_success(sharing_service, mock_backend):
    """Test getting reports shared with a user."""
    submission = MagicMock()
    submission.uid = "report_123"
    submission.original_filename = "report.pdf"
    mock_backend.get_submissions_shared_with_me.return_value = Result.ok([submission])

    result = await sharing_service.get_submissions_shared_with_me(
        user_uid="user_teacher",
        limit=50,
    )

    assert not result.is_error
    assert len(result.value) == 1
    assert result.value[0].uid == "report_123"
    assert result.value[0].original_filename == "report.pdf"


@pytest.mark.asyncio
async def test_get_kus_shared_with_me_empty(sharing_service, mock_backend):
    """Test getting shared reports when none exist."""
    mock_backend.get_submissions_shared_with_me.return_value = Result.ok([])

    result = await sharing_service.get_submissions_shared_with_me(
        user_uid="user_teacher",
        limit=50,
    )

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# SET VISIBILITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_set_visibility_to_public_success(sharing_service, mock_backend):
    """Test setting report visibility to PUBLIC."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.verify_shareable.return_value = Result.ok(True)
    mock_backend.set_visibility.return_value = Result.ok(True)

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PUBLIC,
    )

    assert not result.is_error
    assert result.value is True
    mock_backend.verify_shareable.assert_called_once_with("report_123")


@pytest.mark.asyncio
async def test_set_visibility_to_private_no_shareable_check(sharing_service, mock_backend):
    """Test setting visibility to PRIVATE doesn't require shareability check."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.set_visibility.return_value = Result.ok(True)

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PRIVATE,
    )

    assert not result.is_error
    assert result.value is True
    mock_backend.verify_shareable.assert_not_called()


@pytest.mark.asyncio
async def test_set_visibility_not_owner(sharing_service, mock_backend):
    """Test setting visibility fails if user is not owner."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.validation("User user_not_owner does not own entity report_123")
    )

    result = await sharing_service.set_visibility(
        ku_uid="report_123",
        owner_uid="user_not_owner",
        visibility=Visibility.PUBLIC,
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_set_visibility_shared_not_completed(sharing_service, mock_backend):
    """Test setting visibility to SHARED fails if not completed."""
    mock_backend.verify_ownership.return_value = Result.ok(True)
    mock_backend.verify_shareable.return_value = Result.fail(
        Errors.validation("Only completed Ku can be shared. Current status: processing")
    )

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
async def test_check_access_owner(sharing_service, mock_backend):
    """Test owner always has access."""
    mock_backend.check_access.return_value = Result.ok(True)

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_public(sharing_service, mock_backend):
    """Test anyone can access PUBLIC entity."""
    mock_backend.check_access.return_value = Result.ok(True)

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_with_relationship(sharing_service, mock_backend):
    """Test user with SHARES_WITH relationship can access SHARED entity."""
    mock_backend.check_access.return_value = Result.ok(True)

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_without_relationship(sharing_service, mock_backend):
    """Test user without SHARES_WITH relationship cannot access SHARED entity."""
    mock_backend.check_access.return_value = Result.ok(False)

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_unauthorized",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_private_not_owner(sharing_service, mock_backend):
    """Test non-owner cannot access PRIVATE entity."""
    mock_backend.check_access.return_value = Result.ok(False)

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_report_not_found(sharing_service, mock_backend):
    """Test check_access returns error if report doesn't exist."""
    mock_backend.check_access.return_value = Result.fail(
        Errors.not_found(resource="Entity", identifier="report_nonexistent")
    )

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
async def test_verify_ownership_success(sharing_service, mock_backend):
    """Test _verify_ownership succeeds when user is owner."""
    mock_backend.verify_ownership.return_value = Result.ok(True)

    result = await sharing_service._verify_ownership(
        ku_uid="report_123",
        owner_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_ownership_failure(sharing_service, mock_backend):
    """Test _verify_ownership fails when user is not owner."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.validation("User user_not_owner does not own entity report_123")
    )

    result = await sharing_service._verify_ownership(
        ku_uid="report_123",
        owner_uid="user_not_owner",
    )

    assert result.is_error
    assert "does not own" in str(result.error)


@pytest.mark.asyncio
async def test_verify_shareable_completed(sharing_service, mock_backend):
    """Test _verify_shareable succeeds for completed reports."""
    mock_backend.verify_shareable.return_value = Result.ok(True)

    result = await sharing_service._verify_shareable(
        ku_uid="report_123",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(sharing_service, mock_backend):
    """Test _verify_shareable fails for non-completed reports."""
    mock_backend.verify_shareable.return_value = Result.fail(
        Errors.validation("Only completed Ku can be shared. Current status: processing")
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
async def test_share_ku_database_error(sharing_service, mock_backend):
    """Test share_submission handles database errors gracefully."""
    mock_backend.verify_ownership.return_value = Result.fail(
        Errors.database("share_ku", "Database connection failed")
    )

    result = await sharing_service.share_submission(
        ku_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_check_access_database_error(sharing_service, mock_backend):
    """Test check_access handles database errors gracefully."""
    mock_backend.check_access.return_value = Result.fail(
        Errors.database("check_access", "Query timeout")
    )

    result = await sharing_service.check_access(
        ku_uid="report_123",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "Query timeout" in str(result.error)
