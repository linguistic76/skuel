"""Tests for UserCoreService deletion (Finding 9 — soft vs. hard delete)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from core.events.user_events import UserDeleted
from core.models.enums import UserRole
from core.models.type_hints import UserUID
from core.services.user.user_core_service import UserCoreService
from core.utils.result_simplified import ErrorCategory, Result


@dataclass
class _StubRepo:
    """Minimal UserCrudOperations stub — tracks last call + scripted result."""

    delete_result: Result[bool]
    hard_delete_result: Result[int]
    delete_calls: list[UserUID]
    hard_delete_calls: list[UserUID]

    async def delete_user(self, user_uid: UserUID) -> Result[bool]:
        self.delete_calls.append(user_uid)
        return self.delete_result

    async def hard_delete_user(self, user_uid: UserUID) -> Result[int]:
        self.hard_delete_calls.append(user_uid)
        return self.hard_delete_result


class _StubBus:
    """Records events published to exercise the emission pathway."""

    def __init__(self) -> None:
        self.published: list[Any] = []

    async def publish_async(self, event: Any) -> None:
        self.published.append(event)

    def publish(self, event: Any) -> None:
        self.published.append(event)

    def subscribe(self, event_type: type, handler: Any) -> None:  # pragma: no cover
        return None


def _make_service(
    delete_result: Result[bool] | None = None,
    hard_delete_result: Result[int] | None = None,
    bus: _StubBus | None = None,
) -> tuple[UserCoreService, _StubRepo, _StubBus]:
    repo = _StubRepo(
        delete_result=delete_result if delete_result is not None else Result.ok(True),
        hard_delete_result=hard_delete_result if hard_delete_result is not None else Result.ok(1),
        delete_calls=[],
        hard_delete_calls=[],
    )
    event_bus = bus if bus is not None else _StubBus()
    service = UserCoreService(repo, event_bus=event_bus)  # type: ignore[arg-type]
    return service, repo, event_bus


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_delegates_to_repo_delete_user(self) -> None:
        service, repo, _ = _make_service()

        result = await service.delete_user(UserUID("user_alice"))

        assert result.is_ok
        assert result.value is True
        assert repo.delete_calls == [UserUID("user_alice")]
        # Soft-delete path — hard_delete_user must NOT be invoked.
        assert repo.hard_delete_calls == []

    @pytest.mark.asyncio
    async def test_publishes_user_deleted_with_hard_delete_false(self) -> None:
        service, _, bus = _make_service()

        await service.delete_user(UserUID("user_bob"), reason="account closure", deleted_by=None)

        assert len(bus.published) == 1
        event = bus.published[0]
        assert isinstance(event, UserDeleted)
        assert event.user_uid == "user_bob"
        assert event.hard_delete is False
        assert event.reason == "account closure"
        assert event.deleted_by is None

    @pytest.mark.asyncio
    async def test_no_event_when_no_row_affected(self) -> None:
        service, _, bus = _make_service(delete_result=Result.ok(False))

        result = await service.delete_user(UserUID("user_ghost"))

        assert result.is_ok
        assert result.value is False
        assert bus.published == []


class TestHardDelete:
    @pytest.mark.asyncio
    async def test_non_admin_requester_is_forbidden(self) -> None:
        service, repo, bus = _make_service()

        result = await service.hard_delete_user(
            UserUID("user_target"),
            requester_role=UserRole.TEACHER,
            deleted_by=UserUID("user_teacher"),
            reason="test",
        )

        assert result.is_error
        assert result.expect_error().category == ErrorCategory.FORBIDDEN
        # Repo must not be touched when the gate rejects.
        assert repo.hard_delete_calls == []
        # No event emitted on forbidden.
        assert bus.published == []

    @pytest.mark.asyncio
    async def test_admin_requester_cascades_and_publishes_event(self) -> None:
        service, repo, bus = _make_service(hard_delete_result=Result.ok(7))

        result = await service.hard_delete_user(
            UserUID("user_target"),
            requester_role=UserRole.ADMIN,
            deleted_by=UserUID("user_admin"),
            reason="GDPR request 42",
        )

        assert result.is_ok
        assert result.value == 7
        assert repo.hard_delete_calls == [UserUID("user_target")]
        assert len(bus.published) == 1
        event = bus.published[0]
        assert isinstance(event, UserDeleted)
        assert event.hard_delete is True
        assert event.deleted_by == "user_admin"
        assert event.reason == "GDPR request 42"

    @pytest.mark.asyncio
    async def test_no_event_when_repo_reports_zero_deleted(self) -> None:
        service, _, bus = _make_service(hard_delete_result=Result.ok(0))

        result = await service.hard_delete_user(
            UserUID("user_missing"),
            requester_role=UserRole.ADMIN,
            deleted_by=UserUID("user_admin"),
            reason="typo UID",
        )

        assert result.is_ok
        assert result.value == 0
        assert bus.published == []
