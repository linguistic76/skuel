"""Changing a display name: the service checks the name, writes it alone, and the
facade drops the cached context."""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.type_hints import UserUID
from core.models.user import User, create_user
from core.models.user.user import DISPLAY_NAME_MAX_LENGTH
from core.services.user.user_activity_service import InvalidationReason
from core.services.user.user_core_service import UserCoreService
from core.services.user_service import UserService
from core.utils.result_simplified import ErrorCategory, Errors, Result

_UID = UserUID("user_namer")


class _Repo:
    """The one backend member the write uses; records what it was given."""

    def __init__(self, result: Result[User | None] | None = None) -> None:
        self.user = create_user(username="namer", email="n@example.com", display_name="Old")
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def set_display_name(self, user_uid: UserUID, display_name: str) -> Result[User | None]:
        self.calls.append((user_uid, display_name))
        if self.result is not None:
            return self.result
        return Result.ok(dataclasses.replace(self.user, display_name=display_name))


def _core(repo: _Repo) -> UserCoreService:
    return UserCoreService(repo, event_bus=MagicMock())  # type: ignore[arg-type]


class TestCore:
    @pytest.mark.asyncio
    async def test_the_trimmed_name_is_the_only_thing_handed_to_the_writer(self) -> None:
        repo = _Repo()
        result = await _core(repo).update_display_name(_UID, "  Ana María ")
        assert result.is_ok and result.value.display_name == "Ana María"
        assert repo.calls == [(_UID, "Ana María")]

    @pytest.mark.parametrize(
        "name",
        ["", "   ", "two\nlines", "x" * (DISPLAY_NAME_MAX_LENGTH + 1)],
        ids=["blank", "spaces", "newline", "too-long"],
    )
    @pytest.mark.asyncio
    async def test_a_name_that_is_not_one_is_refused_before_any_write(self, name: str) -> None:
        repo = _Repo()
        result = await _core(repo).update_display_name(_UID, name)
        assert result.is_error
        assert result.expect_error().category == ErrorCategory.VALIDATION
        assert repo.calls == []

    @pytest.mark.asyncio
    async def test_no_such_user_is_not_found(self) -> None:
        result = await _core(_Repo(Result.ok(None))).update_display_name(_UID, "Bo")
        assert result.is_error
        assert result.expect_error().category == ErrorCategory.NOT_FOUND

    @pytest.mark.asyncio
    async def test_a_failed_write_is_passed_on(self) -> None:
        failure: Result[User | None] = Result.fail(Errors.database("set_display_name", "down"))
        result = await _core(_Repo(failure)).update_display_name(_UID, "Bo")
        assert result.is_error
        assert result.expect_error().category == ErrorCategory.DATABASE


def _facade(core_result: Result[User]) -> tuple[MagicMock, AsyncMock, AsyncMock]:
    """``UserService.update_display_name`` over stubbed ``core`` and ``activity``."""
    facade = MagicMock()
    facade.core.update_display_name = AsyncMock(return_value=core_result)
    facade.activity.invalidate_context = AsyncMock()
    facade.get_rich_unified_context = AsyncMock()
    return facade, facade.activity.invalidate_context, facade.get_rich_unified_context


class TestFacade:
    @pytest.mark.asyncio
    async def test_a_save_drops_the_cached_context_at_once_and_builds_nothing(self) -> None:
        facade, invalidate, rebuild = _facade(Result.ok(MagicMock()))
        result = await UserService.update_display_name(facade, _UID, "Bo")
        assert result.is_ok
        invalidate.assert_awaited_once_with(
            _UID, reason=InvalidationReason.DISPLAY_NAME_UPDATED, immediate=True
        )
        rebuild.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_refused_save_leaves_the_cache_alone(self) -> None:
        facade, invalidate, _ = _facade(Result.fail(Errors.validation("blank")))
        result = await UserService.update_display_name(facade, _UID, " ")
        assert result.is_error
        invalidate.assert_not_awaited()
