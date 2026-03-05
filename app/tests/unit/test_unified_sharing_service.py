"""
Unit Tests for UnifiedSharingService
======================================

Tests all service methods with a mocked SharingBackend:
- share()
- unshare()
- set_visibility()
- check_access()
- get_shared_with()
- get_shared_with_me()
- verify_shareable()
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend():
    """Create a mock SharingBackend."""
    return MagicMock()


@pytest.fixture
def sharing_service(mock_backend):
    """Create UnifiedSharingService with mocked backend."""
    return UnifiedSharingService(backend=mock_backend)


# ============================================================================
# SHARE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_success(mock_backend, sharing_service):
    """Test successfully sharing an entity."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "completed", "ku_type": "submission"}]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"success": True}]))

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_share_not_owner(mock_backend, sharing_service):
    """Test sharing fails if user is not owner."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_other", "status": "completed", "ku_type": "submission"}]
        )
    )

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert result.error.category.value == "not_found"
    # Only ownership check — no share query executed
    mock_backend.create_share.assert_not_called()


@pytest.mark.asyncio
async def test_share_not_completed(mock_backend, sharing_service):
    """Test sharing fails if entity is not shareable (e.g. processing)."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "processing", "ku_type": "submission"}]
        )
    )

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)
    mock_backend.create_share.assert_not_called()


@pytest.mark.asyncio
async def test_share_entity_not_found(mock_backend, sharing_service):
    """Test sharing fails if entity doesn't exist."""
    mock_backend.query_ownership_and_status = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.share(
        entity_uid="report_nonexistent",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "not found" in str(result.error)


# ============================================================================
# UNSHARE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unshare_success(mock_backend, sharing_service):
    """Test successfully unsharing an entity."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "completed", "ku_type": "submission"}]
        )
    )
    mock_backend.delete_share = AsyncMock(return_value=Result.ok([{"deleted_count": 1}]))

    result = await sharing_service.unshare(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_unshare_not_owner(mock_backend, sharing_service):
    """Test unsharing fails if user is not owner."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_other", "status": "completed", "ku_type": "submission"}]
        )
    )

    result = await sharing_service.unshare(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert result.error.category.value == "not_found"
    mock_backend.delete_share.assert_not_called()


@pytest.mark.asyncio
async def test_unshare_no_relationship(mock_backend, sharing_service):
    """Test unsharing fails if no sharing relationship exists."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "completed", "ku_type": "submission"}]
        )
    )
    mock_backend.delete_share = AsyncMock(return_value=Result.ok([{"deleted_count": 0}]))

    result = await sharing_service.unshare(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "No sharing relationship found" in str(result.error)


# ============================================================================
# GET SHARED WITH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_shared_with_success(mock_backend, sharing_service):
    """Test getting list of users an entity is shared with."""
    mock_backend.query_shared_with_users = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "user_uid": "user_teacher",
                    "user_name": "Teacher Mike",
                    "role": "teacher",
                    "share_version": "original",
                    "shared_at": "2026-02-02T12:00:00",
                },
                {
                    "user_uid": "user_peer",
                    "user_name": "Peer Sarah",
                    "role": "peer",
                    "share_version": "original",
                    "shared_at": "2026-02-01T10:00:00",
                },
            ]
        )
    )

    result = await sharing_service.get_shared_with(entity_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 2
    assert result.value[0]["user_uid"] == "user_teacher"
    assert result.value[0]["role"] == "teacher"
    assert result.value[1]["user_uid"] == "user_peer"


@pytest.mark.asyncio
async def test_get_shared_with_empty(mock_backend, sharing_service):
    """Test getting shared users when none exist."""
    mock_backend.query_shared_with_users = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.get_shared_with(entity_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# GET SHARED WITH ME TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_shared_with_me_success(mock_backend, sharing_service):
    """Test getting entities shared with a user."""
    entity_data = {
        "uid": "report_123",
        "user_uid": "user_student",
        "ku_type": "submission",
        "status": "completed",
        "title": "My Report",
        "original_filename": "report.pdf",
    }
    mock_backend.query_shared_with_me = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "ku": entity_data,
                    "role": "teacher",
                    "shared_at": "2026-02-02T12:00:00",
                    "share_version": "original",
                }
            ]
        )
    )

    result = await sharing_service.get_shared_with_me(user_uid="user_teacher", limit=50)

    assert not result.is_error
    assert len(result.value) == 1


@pytest.mark.asyncio
async def test_get_shared_with_me_empty(mock_backend, sharing_service):
    """Test getting shared entities when none exist."""
    mock_backend.query_shared_with_me = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.get_shared_with_me(user_uid="user_teacher", limit=50)

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# SET VISIBILITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_set_visibility_to_public_success(mock_backend, sharing_service):
    """Test setting entity visibility to PUBLIC."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "completed", "ku_type": "submission"}]
        )
    )
    mock_backend.update_visibility = AsyncMock(return_value=Result.ok([{"uid": "report_123"}]))

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PUBLIC,
    )

    assert not result.is_error
    assert result.value is True
    mock_backend.query_ownership_and_status.assert_awaited_once()
    mock_backend.update_visibility.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_visibility_to_private_no_shareable_check(mock_backend, sharing_service):
    """Test setting visibility to PRIVATE skips shareability check."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "active", "ku_type": "task"}]
        )
    )
    mock_backend.update_visibility = AsyncMock(return_value=Result.ok([{"uid": "report_123"}]))

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PRIVATE,
    )

    assert not result.is_error
    assert result.value is True
    mock_backend.query_ownership_and_status.assert_awaited_once()
    mock_backend.update_visibility.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_visibility_not_owner(mock_backend, sharing_service):
    """Test setting visibility fails if user is not owner."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_other", "status": "completed", "ku_type": "submission"}]
        )
    )

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        visibility=Visibility.PUBLIC,
    )

    assert result.is_error
    assert result.error.category.value == "not_found"


# ============================================================================
# CHECK ACCESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_access_owner(mock_backend, sharing_service):
    """Test owner always has access."""
    mock_backend.query_access = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "owner_uid": "user_owner",
                    "visibility": "private",
                    "ku_type": "submission",
                    "has_direct_share": False,
                    "has_group_share": False,
                }
            ]
        )
    )

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_public(mock_backend, sharing_service):
    """Test anyone can access PUBLIC entity."""
    mock_backend.query_access = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "owner_uid": "user_owner",
                    "visibility": "public",
                    "ku_type": "submission",
                    "has_direct_share": False,
                    "has_group_share": False,
                }
            ]
        )
    )

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_with_relationship(mock_backend, sharing_service):
    """Test user with SHARES_WITH relationship can access SHARED entity."""
    mock_backend.query_access = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "owner_uid": "user_owner",
                    "visibility": "shared",
                    "ku_type": "submission",
                    "has_direct_share": True,
                    "has_group_share": False,
                }
            ]
        )
    )

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_private_not_owner(mock_backend, sharing_service):
    """Test non-owner cannot access PRIVATE entity."""
    mock_backend.query_access = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "owner_uid": "user_owner",
                    "visibility": "private",
                    "ku_type": "submission",
                    "has_direct_share": False,
                    "has_group_share": False,
                }
            ]
        )
    )

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_entity_not_found(mock_backend, sharing_service):
    """Test check_access returns error if entity doesn't exist."""
    mock_backend.query_access = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.check_access(
        entity_uid="report_nonexistent",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "not found" in str(result.error)


# ============================================================================
# VERIFY SHAREABLE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_verify_shareable_completed(mock_backend, sharing_service):
    """Test verify_shareable succeeds for completed entities."""
    mock_backend.query_shareable_status = AsyncMock(
        return_value=Result.ok([{"status": "completed", "ku_type": "submission"}])
    )

    result = await sharing_service.verify_shareable(entity_uid="report_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_activity_active(mock_backend, sharing_service):
    """Test verify_shareable succeeds for active activity entities."""
    mock_backend.query_shareable_status = AsyncMock(
        return_value=Result.ok([{"status": "active", "ku_type": "task"}])
    )

    result = await sharing_service.verify_shareable(entity_uid="task_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(mock_backend, sharing_service):
    """Test verify_shareable fails for non-completed non-activity entities."""
    mock_backend.query_shareable_status = AsyncMock(
        return_value=Result.ok([{"status": "processing", "ku_type": "submission"}])
    )

    result = await sharing_service.verify_shareable(entity_uid="report_123")

    assert result.is_error
    assert "Only completed Ku" in str(result.error)


# ============================================================================
# ERROR HANDLING
# ============================================================================


@pytest.mark.asyncio
async def test_share_database_error(mock_backend, sharing_service):
    """Test share handles database errors from backend."""
    from core.utils.result_simplified import Errors

    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.fail(
            Errors.database(operation="execute_query", message="Database connection failed")
        )
    )

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_check_access_database_error(mock_backend, sharing_service):
    """Test check_access handles database errors from backend."""
    from core.utils.result_simplified import Errors

    mock_backend.query_access = AsyncMock(
        return_value=Result.fail(
            Errors.database(operation="execute_query", message="Query timeout")
        )
    )

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "Query timeout" in str(result.error)
