"""
GroupService Unit Tests
========================

CRUD, ownership verification, membership, and event emission for GroupService.
Mocks GroupBackend; no Neo4j required.

See: ADR-053, /core/services/groups/group_service.py
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.group.group import Group, create_group
from core.services.groups.group_service import GroupService
from core.utils.result_simplified import Errors, Result


def _make_group(**overrides) -> Group:
    defaults = {
        "uid": "group_physics-101_abc",
        "name": "Physics 101",
        "owner_uid": "user_teacher_01",
        "description": "Intro physics",
        "max_members": None,
    }
    defaults.update(overrides)
    return create_group(**defaults)


def _make_service(backend=None, event_bus=None) -> tuple[GroupService, MagicMock, MagicMock]:
    backend = backend or MagicMock()
    event_bus = event_bus or MagicMock()
    event_bus.publish_async = AsyncMock()
    service = GroupService(backend=backend, event_bus=event_bus)
    return service, backend, event_bus


class TestCreate:
    @pytest.mark.anyio
    async def test_create_success_publishes_event(self):
        group = _make_group()
        service, backend, event_bus = _make_service()
        backend.create = AsyncMock(return_value=Result.ok(group))
        backend.create_owns_relationship = AsyncMock(return_value=Result.ok(True))

        result = await service.create(group)

        assert result.is_ok
        assert result.value.uid == group.uid
        backend.create.assert_awaited_once_with(group)
        backend.create_owns_relationship.assert_awaited_once_with(group.owner_uid, group.uid)
        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.group_uid == group.uid
        assert event.teacher_uid == group.owner_uid

    @pytest.mark.anyio
    async def test_create_backend_failure(self):
        group = _make_group()
        service, backend, _ = _make_service()
        backend.create = AsyncMock(
            return_value=Result.fail(Errors.database(operation="create", message="boom"))
        )

        result = await service.create(group)

        assert result.is_error

    @pytest.mark.anyio
    async def test_create_owns_failure_does_not_fail_create(self):
        """OWNS edge failure is logged but doesn't fail the create."""
        group = _make_group()
        service, backend, _ = _make_service()
        backend.create = AsyncMock(return_value=Result.ok(group))
        backend.create_owns_relationship = AsyncMock(
            return_value=Result.fail(Errors.database(operation="rel", message="boom"))
        )

        result = await service.create(group)

        assert result.is_ok


class TestVerifyOwnership:
    @pytest.mark.anyio
    async def test_owner_sees_group(self):
        group = _make_group()
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))

        result = await service.verify_ownership(group.uid, group.owner_uid)

        assert result.is_ok
        assert result.value.uid == group.uid

    @pytest.mark.anyio
    async def test_non_owner_gets_not_found(self):
        group = _make_group(owner_uid="user_teacher_01")
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))

        result = await service.verify_ownership(group.uid, "user_other")

        assert result.is_error
        assert result.error.category.value == "not_found"

    @pytest.mark.anyio
    async def test_missing_group_returns_not_found(self):
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(None))

        result = await service.verify_ownership("group_missing", "user_anyone")

        assert result.is_error


class TestAddMember:
    @pytest.mark.anyio
    async def test_add_member_success_publishes_event(self):
        group = _make_group()
        service, backend, event_bus = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.add_member = AsyncMock(return_value=Result.ok([{"user_uid": "user_stud_01"}]))

        result = await service.add_member(group.uid, "user_stud_01", role="student")

        assert result.is_ok
        backend.add_member.assert_awaited_once()
        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.call_args[0][0]
        assert event.user_uid == "user_stud_01"
        assert event.role == "student"

    @pytest.mark.anyio
    async def test_add_member_missing_group(self):
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(None))

        result = await service.add_member("group_missing", "user_stud_01")

        assert result.is_error

    @pytest.mark.anyio
    async def test_add_member_enforces_max_members(self):
        group = _make_group(max_members=2)
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.get_member_count = AsyncMock(return_value=Result.ok(2))

        result = await service.add_member(group.uid, "user_stud_03")

        assert result.is_error
        # validation error category
        assert "limit" in str(result.error.message).lower()


class TestRemoveMember:
    @pytest.mark.anyio
    async def test_remove_member_success(self):
        service, backend, event_bus = _make_service()
        backend.remove_member = AsyncMock(return_value=Result.ok([{"deleted_count": 1}]))

        result = await service.remove_member("group_x", "user_stud_01")

        assert result.is_ok
        event_bus.publish_async.assert_awaited_once()

    @pytest.mark.anyio
    async def test_remove_member_not_a_member(self):
        service, backend, _ = _make_service()
        backend.remove_member = AsyncMock(return_value=Result.ok([{"deleted_count": 0}]))

        result = await service.remove_member("group_x", "user_stud_01")

        assert result.is_error


class TestGetUserGroups:
    @pytest.mark.anyio
    async def test_get_user_groups_returns_groups(self):
        service, backend, _ = _make_service()
        group_props = {
            "uid": "group_a",
            "name": "Group A",
            "owner_uid": "user_teacher_01",
        }
        backend.get_user_groups = AsyncMock(return_value=Result.ok([group_props]))

        result = await service.get_user_groups("user_stud_01")

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0].uid == "group_a"

    @pytest.mark.anyio
    async def test_get_user_groups_skips_malformed(self):
        service, backend, _ = _make_service()
        backend.get_user_groups = AsyncMock(
            return_value=Result.ok(
                [
                    {"uid": "group_good", "name": "Good", "owner_uid": "t"},
                    {"uid": "group_bad", "unknown_field": 1},  # missing name
                ]
            )
        )

        result = await service.get_user_groups("user_stud_01")

        assert result.is_ok
        assert {g.uid for g in result.value} == {"group_good"}


class TestStudentGroupCap:
    """MAX_STUDENT_GROUPS cap enforcement in add_member()."""

    @pytest.mark.anyio
    async def test_add_member_cap_rejects_5th_group_for_student(self):
        group = _make_group(uid="group_new")
        existing = [_make_group(uid=f"group_{i}") for i in range(4)]  # student already in 4 groups
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.get_user_groups = AsyncMock(
            return_value=Result.ok(
                [{"uid": g.uid, "name": g.name, "owner_uid": g.owner_uid} for g in existing]
            )
        )
        backend.add_member = AsyncMock()

        result = await service.add_member(group.uid, "user_stud_01", role="student")

        assert result.is_error
        assert "4" in str(result.error.message)
        backend.add_member.assert_not_called()

    @pytest.mark.anyio
    async def test_add_member_cap_allows_readd_to_existing_group(self):
        """Student already in group_x can be re-added to group_x even at cap."""
        group = _make_group(uid="group_x")
        existing = [
            _make_group(uid="group_x"),
            _make_group(uid="group_2"),
            _make_group(uid="group_3"),
            _make_group(uid="group_4"),
        ]
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.get_user_groups = AsyncMock(
            return_value=Result.ok(
                [{"uid": g.uid, "name": g.name, "owner_uid": g.owner_uid} for g in existing]
            )
        )
        backend.add_member = AsyncMock(return_value=Result.ok([{"user_uid": "user_stud_01"}]))

        result = await service.add_member(group.uid, "user_stud_01", role="student")

        assert result.is_ok
        backend.add_member.assert_awaited_once()

    @pytest.mark.anyio
    async def test_add_member_cap_does_not_apply_to_teacher_role(self):
        group = _make_group(uid="group_new")
        existing = [_make_group(uid=f"group_{i}") for i in range(4)]
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.get_user_groups = AsyncMock(
            return_value=Result.ok(
                [{"uid": g.uid, "name": g.name, "owner_uid": g.owner_uid} for g in existing]
            )
        )
        backend.add_member = AsyncMock(return_value=Result.ok([{"user_uid": "user_teach_01"}]))

        result = await service.add_member(group.uid, "user_teach_01", role="teacher")

        assert result.is_ok
        backend.add_member.assert_awaited_once()

    @pytest.mark.anyio
    async def test_add_member_cap_allows_4th_group(self):
        """Boundary: student in 3 groups can be added to a 4th (3 < 4)."""
        group = _make_group(uid="group_4")
        existing = [_make_group(uid=f"group_{i}") for i in range(3)]
        service, backend, _ = _make_service()
        backend.get = AsyncMock(return_value=Result.ok(group))
        backend.get_user_groups = AsyncMock(
            return_value=Result.ok(
                [{"uid": g.uid, "name": g.name, "owner_uid": g.owner_uid} for g in existing]
            )
        )
        backend.add_member = AsyncMock(return_value=Result.ok([{"user_uid": "user_stud_01"}]))

        result = await service.add_member(group.uid, "user_stud_01", role="student")

        assert result.is_ok
        backend.add_member.assert_awaited_once()
