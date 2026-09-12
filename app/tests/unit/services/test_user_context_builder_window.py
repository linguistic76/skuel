"""``build_rich(window=)`` speaks the report-period vocabulary — one resolver
with the report generator — and refuses a token it does not know instead of
substituting a default lookback."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.user.user import User
from core.services.user.user_context_builder import UserContextBuilder
from core.utils.result_simplified import Errors, Result


def _executor() -> MagicMock:
    executor = MagicMock()
    executor.execute_mega_query = AsyncMock(
        return_value=Result.ok({"uids": {}, "entities": {}, "rich": {}})
    )
    executor.execute_consolidated_query = AsyncMock(return_value=Result.ok({}))
    executor.fetch_current_path_steps = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    executor.fetch_user_groups = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    return executor


def _user() -> User:
    return User(uid="user_window", title="user_window", email="w@test.local", display_name="W")


@pytest.mark.asyncio
async def test_unknown_window_is_a_validation_failure_before_any_query() -> None:
    executor = _executor()
    builder = UserContextBuilder(executor)

    result = await builder.build_rich_user_context("user_window", _user(), window="someday")

    assert result.is_error
    assert result.expect_error().category.value == "validation"
    executor.execute_mega_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_calendar_window_starts_the_touched_selection_at_the_periods_start() -> None:
    executor = _executor()
    builder = UserContextBuilder(executor)

    result = await builder.build_rich_user_context("user_window", _user(), window="2026-09")

    assert result.is_ok, result.error
    _, kwargs = executor.execute_mega_query.call_args
    assert kwargs["window_start"] == datetime(2026, 9, 1)
    # The period's own end rides along; the query applies no upper bound.
    assert kwargs["window_end"].date().isoformat() == "2026-09-30"


@pytest.mark.asyncio
async def test_trailing_window_reaches_back_its_days_from_now() -> None:
    executor = _executor()
    builder = UserContextBuilder(executor)

    result = await builder.build_rich_user_context("user_window", _user(), window="7d")

    assert result.is_ok, result.error
    _, kwargs = executor.execute_mega_query.call_args
    assert (kwargs["window_end"] - kwargs["window_start"]).days == 7
