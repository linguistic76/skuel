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

from core.models.enums.entity_enums import EntityType
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
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
            [
                {
                    "actual_owner": "user_other",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
            [
                {
                    "actual_owner": "user_owner",
                    "status": "processing",
                    "entity_type": "entry_report",
                }
            ]
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
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
            [
                {
                    "actual_owner": "user_other",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
    """Test getting entities shared with a user, with share-edge metadata."""
    entity_data = {
        "uid": "er_abc123",
        "user_uid": "user_student",
        "entity_type": "entry_report",
        "status": "completed",
        "title": "Feedback: ue_xyz",
        "created_by": "user_teacher",
    }
    mock_backend.query_shared_with_me = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "entity": entity_data,
                    "role": "student",
                    "shared_at": "2026-02-02T12:00:00",
                    "shared_by": "Teacher Name",
                    "sharer_uid": "user_teacher",
                    "share_version": None,
                    # Subject context resolved by the backend join (C4).
                    "subject_exercise_uid": "ex_essay",
                    "subject_exercise_title": "Essay Exercise",
                    "subject_ps_uid": "ps.test.essays",
                    "subject_ps_title": "Writing Essays",
                }
            ]
        )
    )

    result = await sharing_service.get_shared_with_me(user_uid="user_student", limit=50)

    assert not result.is_error
    assert len(result.value) == 1
    item = result.value[0]
    assert item["entity"].uid == "er_abc123"
    assert item["entity"].title == "Feedback: ue_xyz"
    assert item["shared_by"] == "Teacher Name"
    assert item["sharer_uid"] == "user_teacher"
    assert item["shared_at"] == "2026-02-02T12:00:00"
    assert item["role"] == "student"
    assert item["subject_exercise_uid"] == "ex_essay"
    assert item["subject_exercise_title"] == "Essay Exercise"
    assert item["subject_ps_uid"] == "ps.test.essays"
    assert item["subject_ps_title"] == "Writing Essays"
    # No filters requested → the backend must see explicit None (no filter),
    # not stale or omitted arguments.
    mock_backend.query_shared_with_me.assert_awaited_once_with(
        user_uid="user_student", limit=50, entity_type=None, sharer_uid=None
    )


@pytest.mark.asyncio
async def test_get_shared_with_me_passes_filters_as_canonical_values(mock_backend, sharing_service):
    """Arc 2 C4: the EntityType filter crosses to the backend as its canonical
    enum value and the sharer filter as the raw uid — both driver parameters."""
    mock_backend.query_shared_with_me = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.get_shared_with_me(
        user_uid="user_student",
        limit=50,
        entity_type=EntityType.ENTRY_REPORT,
        sharer_uid="user_teacher",
    )

    assert not result.is_error
    mock_backend.query_shared_with_me.assert_awaited_once_with(
        user_uid="user_student",
        limit=50,
        entity_type="entry_report",
        sharer_uid="user_teacher",
    )


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
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
            [{"actual_owner": "user_owner", "status": "active", "entity_type": "task"}]
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
            [
                {
                    "actual_owner": "user_other",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
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
                    "entity_type": "user_entry",
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
                    "entity_type": "user_entry",
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
                    "entity_type": "user_entry",
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
                    "entity_type": "user_entry",
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
        return_value=Result.ok([{"status": "completed", "entity_type": "user_entry"}])
    )

    result = await sharing_service.verify_shareable(entity_uid="report_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_activity_active(mock_backend, sharing_service):
    """Test verify_shareable succeeds for active activity entities."""
    mock_backend.query_shareable_status = AsyncMock(
        return_value=Result.ok([{"status": "active", "entity_type": "task"}])
    )

    result = await sharing_service.verify_shareable(entity_uid="task_123")

    assert not result.is_error
    assert result.value is True


@pytest.mark.asyncio
async def test_verify_shareable_not_completed(mock_backend, sharing_service):
    """Test verify_shareable fails for non-completed non-activity entities."""
    mock_backend.query_shareable_status = AsyncMock(
        return_value=Result.ok([{"status": "processing", "entity_type": "entry_report"}])
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


# ============================================================================
# GET USER ENTRIES SHARED WITH GROUP TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_entries_shared_with_group_success(mock_backend, sharing_service):
    """Returns list of dicts with entity/author_name/share_version/shared_at keys."""
    mock_backend.query_user_entries_shared_with_group = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "entry": {"uid": "ue_1", "title": "Reflection 1"},
                    "author_name": "Alex Rivera",
                    "share_version": "original",
                    "shared_at": "2026-04-10T12:00:00",
                },
                {
                    "entry": {"uid": "ue_2", "title": "Reflection 2"},
                    "author_name": None,
                    "share_version": "original",
                    "shared_at": "2026-04-11T12:00:00",
                },
            ]
        )
    )

    result = await sharing_service.get_user_entries_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
    )

    assert result.is_ok
    assert len(result.value) == 2
    assert result.value[0]["entity"] == {"uid": "ue_1", "title": "Reflection 1"}
    assert result.value[0]["author_name"] == "Alex Rivera"
    assert result.value[0]["share_version"] == "original"
    assert result.value[0]["shared_at"] == "2026-04-10T12:00:00"
    assert result.value[1]["author_name"] is None


@pytest.mark.asyncio
async def test_get_user_entries_shared_with_group_empty(mock_backend, sharing_service):
    """Empty backend result (e.g., non-member) yields Result.ok([])."""
    mock_backend.query_user_entries_shared_with_group = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.get_user_entries_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
    )

    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
async def test_get_user_entries_shared_with_group_backend_error(mock_backend, sharing_service):
    """Backend errors propagate via Result.fail."""
    from core.utils.result_simplified import Errors

    mock_backend.query_user_entries_shared_with_group = AsyncMock(
        return_value=Result.fail(Errors.database(operation="execute_query", message="boom"))
    )

    result = await sharing_service.get_user_entries_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
    )

    assert result.is_error
    assert "boom" in str(result.error)


@pytest.mark.asyncio
async def test_get_user_entries_shared_with_group_forwards_limit(mock_backend, sharing_service):
    """Custom limit is forwarded to the backend query."""
    mock_backend.query_user_entries_shared_with_group = AsyncMock(return_value=Result.ok([]))

    await sharing_service.get_user_entries_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
        limit=5,
    )

    mock_backend.query_user_entries_shared_with_group.assert_awaited_once_with(
        user_uid="user_stud_01",
        group_uid="group_physics",
        limit=5,
    )


# ============================================================================
# GET USER ENTRY SHARED WITH GROUP (single-entry peer fetch) TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_entry_shared_with_group_success(mock_backend, sharing_service):
    """Returns flattened payload with entity/group_name/author_name."""
    mock_backend.query_user_entry_shared_with_group = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "entry": {
                        "uid": "ue_1",
                        "title": "Reflection 1",
                        "content": "body text",
                        "user_uid": "user_peer",
                    },
                    "group_name": "Physics 101",
                    "author_name": "Alex Rivera",
                    "share_version": "original",
                    "shared_at": "2026-04-10T12:00:00",
                }
            ]
        )
    )

    result = await sharing_service.get_user_entry_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
        entry_uid="ue_1",
    )

    assert result.is_ok
    payload = result.value
    assert payload is not None
    assert payload["entity"]["uid"] == "ue_1"
    assert payload["entity"]["content"] == "body text"
    assert payload["group_name"] == "Physics 101"
    assert payload["author_name"] == "Alex Rivera"
    assert payload["shared_at"] == "2026-04-10T12:00:00"


@pytest.mark.asyncio
async def test_get_user_entry_shared_with_group_not_visible(mock_backend, sharing_service):
    """Empty backend result (non-member, wrong group, own entry) -> Result.ok(None).

    We explicitly want ok(None) rather than Result.fail so callers render a
    404-equivalent page without distinguishing the failure mode to the viewer.
    """
    mock_backend.query_user_entry_shared_with_group = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.get_user_entry_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
        entry_uid="ue_missing",
    )

    assert result.is_ok
    assert result.value is None


@pytest.mark.asyncio
async def test_get_user_entry_shared_with_group_backend_error(mock_backend, sharing_service):
    """Backend errors propagate via Result.fail."""
    from core.utils.result_simplified import Errors

    mock_backend.query_user_entry_shared_with_group = AsyncMock(
        return_value=Result.fail(Errors.database(operation="execute_query", message="boom"))
    )

    result = await sharing_service.get_user_entry_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
        entry_uid="ue_1",
    )

    assert result.is_error
    assert "boom" in str(result.error)


@pytest.mark.asyncio
async def test_get_user_entry_shared_with_group_passes_all_uids(mock_backend, sharing_service):
    """All three UIDs (viewer, group, entry) are forwarded to the backend."""
    mock_backend.query_user_entry_shared_with_group = AsyncMock(return_value=Result.ok([]))

    await sharing_service.get_user_entry_shared_with_group(
        user_uid="user_stud_01",
        group_uid="group_physics",
        entry_uid="ue_abc",
    )

    mock_backend.query_user_entry_shared_with_group.assert_awaited_once_with(
        user_uid="user_stud_01",
        group_uid="group_physics",
        entry_uid="ue_abc",
    )


# ============================================================================
# SHARE WITH GROUP — MEMBERSHIP GUARD (Finding 1)
# ============================================================================


@pytest.mark.asyncio
async def test_share_with_group_rejects_non_member(mock_backend, sharing_service):
    """The backend's MEMBER_OF MATCH returns empty when the owner is not a
    member — the service maps that to ``forbidden``, not ``not_found``,
    so the uploader sees the real reason.
    """
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
        )
    )
    # Empty result simulates either missing group/entity OR non-membership.
    mock_backend.create_group_share = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.share_with_group(
        entity_uid="ue_1",
        owner_uid="user_owner",
        group_uid="group_someone_elses_class",
    )

    assert result.is_error
    err = result.expect_error()
    assert err.category.value == "forbidden"
    assert "member" in str(err).lower()
    # The backend received the owner_uid so membership could be enforced at Cypher.
    _, kwargs = mock_backend.create_group_share.await_args
    assert kwargs["owner_uid"] == "user_owner"
    assert kwargs["group_uid"] == "group_someone_elses_class"


@pytest.mark.asyncio
async def test_share_with_group_success_passes_owner_uid(mock_backend, sharing_service):
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "user_entry",
                }
            ]
        )
    )
    mock_backend.create_group_share = AsyncMock(return_value=Result.ok([{"success": True}]))

    result = await sharing_service.share_with_group(
        entity_uid="ue_1",
        owner_uid="user_owner",
        group_uid="group_my_class",
    )

    assert result.is_ok
    _, kwargs = mock_backend.create_group_share.await_args
    assert kwargs["owner_uid"] == "user_owner"
