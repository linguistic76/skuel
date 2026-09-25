"""
Unit Tests for UnifiedSharingService
======================================

Tests all service methods with a mocked SharingBackend:
- share()
- unshare()
- set_visibility()
- get_shared_with()
- get_shared_with_me()
- submit_to_group()
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
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"created": True}]))

    result = await sharing_service.share(
        entity_uid="report_123",
        owner_uid="user_owner",
        recipient_uid="user_teacher",
        role="teacher",
    )

    assert not result.is_error
    assert result.value is True
    # R8 rides into the statement by default (ADR-088 §7).
    assert mock_backend.create_share.await_args.kwargs["require_co_membership"] is True
    assert mock_backend.create_share.await_args.kwargs["owner_uid"] == "user_owner"


@pytest.mark.asyncio
async def test_share_that_already_stood_is_a_success_not_created(mock_backend, sharing_service):
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "active", "entity_type": "user_entry"}]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"created": False}]))

    result = await sharing_service.share(
        entity_uid="ue_1", owner_uid="user_owner", recipient_uid="user_peer"
    )

    assert not result.is_error
    assert result.value is False


@pytest.mark.asyncio
async def test_share_refused_by_the_guard_is_one_not_found(mock_backend, sharing_service):
    """No row = the recipient does not exist or is not a co-member; the
    service says the same in both cases."""
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "active", "entity_type": "user_entry"}]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.share(
        entity_uid="ue_1", owner_uid="user_owner", recipient_uid="user_stranger"
    )

    assert result.is_error
    assert result.error.category.value == "not_found"
    assert "user_stranger" in str(result.error)


@pytest.mark.asyncio
async def test_share_without_co_membership_is_the_admin_exemption(mock_backend, sharing_service):
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "actual_owner": "user_owner",
                    "status": "completed",
                    "entity_type": "form_submission",
                }
            ]
        )
    )
    mock_backend.create_share = AsyncMock(return_value=Result.ok([{"created": True}]))

    result = await sharing_service.share(
        entity_uid="fs_1",
        owner_uid="user_owner",
        recipient_uid="user_admin",
        require_co_membership=False,
    )

    assert not result.is_error
    assert mock_backend.create_share.await_args.kwargs["require_co_membership"] is False


# ============================================================================
# R8 CO-MEMBERSHIP READS
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_co_member_returns_the_uid(mock_backend, sharing_service):
    mock_backend.query_co_member_uid = AsyncMock(return_value=Result.ok([{"uid": "user_alice"}]))
    result = await sharing_service.resolve_co_member("user_owner", "Alice")
    assert result.value == "user_alice"
    mock_backend.query_co_member_uid.assert_awaited_once_with("user_owner", username="Alice")


@pytest.mark.asyncio
async def test_resolve_co_member_is_none_for_unknown_and_stranger_alike(
    mock_backend, sharing_service
):
    mock_backend.query_co_member_uid = AsyncMock(return_value=Result.ok([]))
    assert (await sharing_service.resolve_co_member("user_owner", "nobody")).value is None


@pytest.mark.asyncio
async def test_shares_group_with_by_uid(mock_backend, sharing_service):
    mock_backend.query_co_member_uid = AsyncMock(return_value=Result.ok([{"uid": "user_peer"}]))
    assert (await sharing_service.shares_group_with("user_owner", "user_peer")).value is True
    mock_backend.query_co_member_uid.assert_awaited_once_with(
        "user_owner", recipient_uid="user_peer"
    )


@pytest.mark.asyncio
async def test_shares_group_with_is_never_true_for_oneself(mock_backend, sharing_service):
    mock_backend.query_co_member_uid = AsyncMock(return_value=Result.ok([{"uid": "user_owner"}]))
    assert (await sharing_service.shares_group_with("user_owner", "user_owner")).value is False
    mock_backend.query_co_member_uid.assert_not_awaited()


@pytest.mark.asyncio
async def test_reachable_groups_is_the_subset_the_backend_returns(mock_backend, sharing_service):
    mock_backend.query_reachable_groups = AsyncMock(return_value=Result.ok([{"group_uid": "g_a"}]))
    result = await sharing_service.reachable_groups("user_owner", ["g_a", "g_b"])
    assert result.value == frozenset({"g_a"})


@pytest.mark.asyncio
async def test_reachable_groups_with_nothing_named_reads_nothing(mock_backend, sharing_service):
    mock_backend.query_reachable_groups = AsyncMock()
    result = await sharing_service.reachable_groups("user_owner", [])
    assert result.value == frozenset()
    mock_backend.query_reachable_groups.assert_not_awaited()


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


# ============================================================================
# SUBMIT TO GROUP — THE FEEDBACK REQUEST (ADR-088 §2)
# ============================================================================


def _owned_user_entry(mock_backend) -> None:
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_owner", "status": "submitted", "entity_type": "user_entry"}]
        )
    )


@pytest.mark.asyncio
async def test_submit_to_group_rejects_non_member(mock_backend, sharing_service):
    """No row = the guard refused (not a member or owner, or the group is
    missing or inactive) — ``forbidden``, never ``not_found``."""
    _owned_user_entry(mock_backend)
    mock_backend.create_group_submission = AsyncMock(return_value=Result.ok([]))

    result = await sharing_service.submit_to_group(
        entity_uid="ue_1", owner_uid="user_owner", group_uid="group_someone_elses_class"
    )

    assert result.is_error
    err = result.expect_error()
    assert err.category.value == "forbidden"
    assert "member" in str(err).lower()
    _, kwargs = mock_backend.create_group_submission.await_args
    assert kwargs["owner_uid"] == "user_owner"
    assert kwargs["group_uid"] == "group_someone_elses_class"


@pytest.mark.asyncio
async def test_submit_to_group_created_is_true_for_a_new_request(mock_backend, sharing_service):
    _owned_user_entry(mock_backend)
    mock_backend.create_group_submission = AsyncMock(return_value=Result.ok([{"created": True}]))

    result = await sharing_service.submit_to_group(
        entity_uid="ue_1", owner_uid="user_owner", group_uid="group_my_class"
    )

    assert result.is_ok
    assert result.value is True


@pytest.mark.asyncio
async def test_submit_to_group_matched_request_is_a_success_not_created(
    mock_backend, sharing_service
):
    """The MERGE matched an existing request: success (the request stands),
    ``created`` False — never copy ``share_with_group``'s empty-value refusal
    onto this bool."""
    _owned_user_entry(mock_backend)
    mock_backend.create_group_submission = AsyncMock(return_value=Result.ok([{"created": False}]))

    result = await sharing_service.submit_to_group(
        entity_uid="ue_1", owner_uid="user_owner", group_uid="group_my_class"
    )

    assert result.is_ok
    assert result.value is False


@pytest.mark.asyncio
async def test_submit_to_group_requires_ownership(mock_backend, sharing_service):
    mock_backend.query_ownership_and_status = AsyncMock(
        return_value=Result.ok(
            [{"actual_owner": "user_other", "status": "submitted", "entity_type": "user_entry"}]
        )
    )
    mock_backend.create_group_submission = AsyncMock()

    result = await sharing_service.submit_to_group(
        entity_uid="ue_1", owner_uid="user_owner", group_uid="group_my_class"
    )

    assert result.is_error
    assert result.expect_error().category.value == "not_found"
    mock_backend.create_group_submission.assert_not_called()
