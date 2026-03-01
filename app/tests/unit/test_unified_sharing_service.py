"""
Unit Tests for UnifiedSharingService
======================================

Tests all service methods with a mocked Neo4j driver:
- share()
- unshare()
- set_visibility()
- check_access()
- get_shared_with()
- get_shared_with_me()
- verify_shareable()

Also tests the private helper:
- _verify_ownership()
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.metadata_enums import Visibility
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver with session context manager."""
    driver = MagicMock()
    session = AsyncMock()
    driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
    driver.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return driver, session


@pytest.fixture
def sharing_service(mock_driver):
    """Create UnifiedSharingService with mocked driver."""
    driver, _ = mock_driver
    return UnifiedSharingService(driver=driver)


def make_session_returning(mock_driver, records):
    """Helper: configure session to return given records from result.data()."""
    driver, session = mock_driver
    result_mock = AsyncMock()
    result_mock.data = AsyncMock(return_value=records)
    session.run = AsyncMock(return_value=result_mock)
    return session


# ============================================================================
# SHARE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_share_success(mock_driver, sharing_service):
    """Test successfully sharing an entity."""
    driver, session = mock_driver

    # _verify_ownership returns owner match, then verify_shareable, then share
    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    shareable_result = AsyncMock()
    shareable_result.data = AsyncMock(
        return_value=[{"status": "completed", "ku_type": "submission"}]
    )
    share_result = AsyncMock()
    share_result.data = AsyncMock(return_value=[{"success": True}])

    session.run = AsyncMock(
        side_effect=[ownership_result, shareable_result, share_result]
    )

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_share_not_owner(mock_driver, sharing_service):
    """Test sharing fails if user is not owner."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_other"}])
    session.run = AsyncMock(return_value=ownership_result)

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)
    # Only one query executed (ownership check)
    assert session.run.call_count == 1


@pytest.mark.asyncio
async def test_share_not_completed(mock_driver, sharing_service):
    """Test sharing fails if entity is not shareable (e.g. processing)."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    shareable_result = AsyncMock()
    shareable_result.data = AsyncMock(
        return_value=[{"status": "processing", "ku_type": "submission"}]
    )
    session.run = AsyncMock(side_effect=[ownership_result, shareable_result])

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Only completed Ku" in str(result.error)
    # Share query NOT executed
    assert session.run.call_count == 2


@pytest.mark.asyncio
async def test_share_entity_not_found(mock_driver, sharing_service):
    """Test sharing fails if entity doesn't exist."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[])  # Empty = not found
    session.run = AsyncMock(return_value=ownership_result)

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
async def test_unshare_success(mock_driver, sharing_service):
    """Test successfully unsharing an entity."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    unshare_result = AsyncMock()
    unshare_result.data = AsyncMock(return_value=[{"deleted_count": 1}])
    session.run = AsyncMock(side_effect=[ownership_result, unshare_result])

    result = await sharing_service.unshare(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_unshare_not_owner(mock_driver, sharing_service):
    """Test unsharing fails if user is not owner."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_other"}])
    session.run = AsyncMock(return_value=ownership_result)

    result = await sharing_service.unshare(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        recipient_uid="user_teacher",
    )

    assert result.is_error
    assert "does not own" in str(result.error)
    assert session.run.call_count == 1


@pytest.mark.asyncio
async def test_unshare_no_relationship(mock_driver, sharing_service):
    """Test unsharing fails if no sharing relationship exists."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    unshare_result = AsyncMock()
    unshare_result.data = AsyncMock(return_value=[{"deleted_count": 0}])
    session.run = AsyncMock(side_effect=[ownership_result, unshare_result])

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
async def test_get_shared_with_success(mock_driver, sharing_service):
    """Test getting list of users an entity is shared with."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
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
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.get_shared_with(entity_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 2
    assert result.value[0]["user_uid"] == "user_teacher"
    assert result.value[0]["role"] == "teacher"
    assert result.value[1]["user_uid"] == "user_peer"


@pytest.mark.asyncio
async def test_get_shared_with_empty(mock_driver, sharing_service):
    """Test getting shared users when none exist."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(return_value=[])
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.get_shared_with(entity_uid="report_123")

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# GET SHARED WITH ME TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_shared_with_me_success(mock_driver, sharing_service):
    """Test getting entities shared with a user."""
    driver, session = mock_driver

    entity_data = {
        "uid": "report_123",
        "user_uid": "user_student",
        "ku_type": "submission",
        "status": "completed",
        "title": "My Report",
        "original_filename": "report.pdf",
    }
    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
            {
                "ku": entity_data,
                "role": "teacher",
                "shared_at": "2026-02-02T12:00:00",
                "share_version": "original",
            }
        ]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.get_shared_with_me(user_uid="user_teacher", limit=50)

    assert not result.is_error
    assert len(result.value) == 1


@pytest.mark.asyncio
async def test_get_shared_with_me_empty(mock_driver, sharing_service):
    """Test getting shared entities when none exist."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(return_value=[])
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.get_shared_with_me(user_uid="user_teacher", limit=50)

    assert not result.is_error
    assert len(result.value) == 0


# ============================================================================
# SET VISIBILITY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_set_visibility_to_public_success(mock_driver, sharing_service):
    """Test setting entity visibility to PUBLIC."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    shareable_result = AsyncMock()
    shareable_result.data = AsyncMock(
        return_value=[{"status": "completed", "ku_type": "submission"}]
    )
    visibility_result = AsyncMock()
    visibility_result.data = AsyncMock(return_value=[{"uid": "report_123"}])
    session.run = AsyncMock(
        side_effect=[ownership_result, shareable_result, visibility_result]
    )

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PUBLIC,
    )

    assert not result.is_error
    assert result.value is True
    # 3 queries: ownership, shareable, update
    assert session.run.call_count == 3


@pytest.mark.asyncio
async def test_set_visibility_to_private_no_shareable_check(mock_driver, sharing_service):
    """Test setting visibility to PRIVATE skips shareability check."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_owner"}])
    visibility_result = AsyncMock()
    visibility_result.data = AsyncMock(return_value=[{"uid": "report_123"}])
    session.run = AsyncMock(side_effect=[ownership_result, visibility_result])

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_owner",
        visibility=Visibility.PRIVATE,
    )

    assert not result.is_error
    assert result.value is True
    # 2 queries: ownership + update (no shareability check for PRIVATE)
    assert session.run.call_count == 2


@pytest.mark.asyncio
async def test_set_visibility_not_owner(mock_driver, sharing_service):
    """Test setting visibility fails if user is not owner."""
    driver, session = mock_driver

    ownership_result = AsyncMock()
    ownership_result.data = AsyncMock(return_value=[{"actual_owner": "user_other"}])
    session.run = AsyncMock(return_value=ownership_result)

    result = await sharing_service.set_visibility(
        entity_uid="report_123",
        owner_uid="user_not_owner",
        visibility=Visibility.PUBLIC,
    )

    assert result.is_error
    assert "does not own" in str(result.error)


# ============================================================================
# CHECK ACCESS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_check_access_owner(mock_driver, sharing_service):
    """Test owner always has access."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_owner",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_public(mock_driver, sharing_service):
    """Test anyone can access PUBLIC entity."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
            {
                "owner_uid": "user_owner",
                "visibility": "public",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_shared_with_relationship(mock_driver, sharing_service):
    """Test user with SHARES_WITH relationship can access SHARED entity."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
            {
                "owner_uid": "user_owner",
                "visibility": "shared",
                "ku_type": "submission",
                "has_share_relationship": True,
            }
        ]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_teacher",
    )

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_check_access_private_not_owner(mock_driver, sharing_service):
    """Test non-owner cannot access PRIVATE entity."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[
            {
                "owner_uid": "user_owner",
                "visibility": "private",
                "ku_type": "submission",
                "has_share_relationship": False,
            }
        ]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_other",
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_check_access_entity_not_found(mock_driver, sharing_service):
    """Test check_access returns error if entity doesn't exist."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(return_value=[])
    session.run = AsyncMock(return_value=query_result)

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
async def test_verify_shareable_completed(mock_driver, sharing_service):
    """Test verify_shareable succeeds for completed entities."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[{"status": "completed", "ku_type": "submission"}]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.verify_shareable(entity_uid="report_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_activity_active(mock_driver, sharing_service):
    """Test verify_shareable succeeds for active activity entities."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[{"status": "active", "ku_type": "task"}]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.verify_shareable(entity_uid="task_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(mock_driver, sharing_service):
    """Test verify_shareable fails for non-completed non-activity entities."""
    driver, session = mock_driver

    query_result = AsyncMock()
    query_result.data = AsyncMock(
        return_value=[{"status": "processing", "ku_type": "submission"}]
    )
    session.run = AsyncMock(return_value=query_result)

    result = await sharing_service.verify_shareable(entity_uid="report_123")

    assert result.is_error
    assert "Only completed Ku" in str(result.error)


# ============================================================================
# ERROR HANDLING
# ============================================================================


@pytest.mark.asyncio
async def test_share_database_error(mock_driver, sharing_service):
    """Test share handles database errors gracefully."""
    driver, session = mock_driver

    session.run = AsyncMock(side_effect=Exception("Database connection failed"))

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert result.is_error
    assert "Database connection failed" in str(result.error)


@pytest.mark.asyncio
async def test_check_access_database_error(mock_driver, sharing_service):
    """Test check_access handles database errors gracefully."""
    driver, session = mock_driver

    session.run = AsyncMock(side_effect=Exception("Query timeout"))

    result = await sharing_service.check_access(
        entity_uid="report_123",
        user_uid="user_owner",
    )

    assert result.is_error
    assert "Query timeout" in str(result.error)
