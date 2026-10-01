"""``build_rich(window=)`` speaks the report-period vocabulary — one resolver
with the report generator — and refuses a token it does not know instead of
substituting a default lookback. A calendar window's days are the context
user's, in the user's own zone, whoever asked for the context."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from core.models.user.user import User, UserPreferences
from core.services.user.user_context_builder import UserContextBuilder
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import day_of
from core.utils.zone_context import current_zone, zone_scope
from tests.helpers.laptop_clock import laptop_wall

# A calendar window's bounds are its midnights in the user's zone, held on the
# stored (UTC) clock; the default user here is the laptop's, in Vancouver.
pytestmark = pytest.mark.usefixtures("laptop_zone")


def _executor() -> MagicMock:
    executor = MagicMock()
    executor.execute_mega_query = AsyncMock(
        return_value=Result.ok({"uids": {}, "entities": {}, "rich": {}})
    )
    executor.execute_consolidated_query = AsyncMock(return_value=Result.ok({}))
    executor.fetch_current_path_steps = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    executor.fetch_mastered_path_steps = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    executor.fetch_user_groups = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    # Fetched beside the MEGA-QUERY; a failure in either fails the rich build
    # (they are its own reads in separate statements), so both answer empty.
    executor.fetch_submission_stats = AsyncMock(return_value=Result.ok({}))
    executor.fetch_entry_knowledge_applied = AsyncMock(return_value=Result.ok([]))
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
    assert kwargs["window_start"] == laptop_wall(2026, 9, 1)
    # The period's own end rides along; the query applies no upper bound.
    assert day_of(kwargs["window_end"], ZoneInfo("America/Vancouver")).isoformat() == "2026-09-30"


@pytest.mark.asyncio
async def test_trailing_window_reaches_back_its_days_from_now() -> None:
    executor = _executor()
    builder = UserContextBuilder(executor)

    result = await builder.build_rich_user_context("user_window", _user(), window="7d")

    assert result.is_ok, result.error
    _, kwargs = executor.execute_mega_query.call_args
    assert (kwargs["window_end"] - kwargs["window_start"]).days == 7


@pytest.mark.asyncio
async def test_a_bangkok_users_window_is_bangkok_days_whoever_asks() -> None:
    """An admin in another zone builds a Bangkok user's context: September starts at
    midnight in Bangkok — 10:00 on August 31st on the Vancouver host clock."""
    executor = _executor()
    builder = UserContextBuilder(executor)
    bangkok_user = dataclasses.replace(
        _user(), preferences=UserPreferences(timezone="Asia/Bangkok")
    )

    with zone_scope(ZoneInfo("Europe/Paris")):  # the reviewing admin's request
        result = await builder.build_rich_user_context(
            "user_window", bangkok_user, window="2026-09"
        )
        assert current_zone() == ZoneInfo("Europe/Paris")

    assert result.is_ok, result.error
    _, kwargs = executor.execute_mega_query.call_args
    # 2026-09-01 00:00 in Bangkok is 2026-08-31 17:00Z.
    assert kwargs["window_start"] == datetime(2026, 8, 31, 17, 0)


@pytest.mark.asyncio
async def test_an_unparsed_preferences_blob_follows_the_default_zone() -> None:
    """The mapper's fail-soft hands the raw blob string through; the build neither
    fails nor guesses — the user follows the app default."""
    executor = _executor()
    builder = UserContextBuilder(executor)
    garbled = dataclasses.replace(_user(), preferences="{not json")  # type: ignore[arg-type]

    result = await builder.build_rich_user_context("user_window", garbled, window="2026-09")

    assert result.is_ok, result.error
    _, kwargs = executor.execute_mega_query.call_args
    assert kwargs["window_start"] == laptop_wall(2026, 9, 1)
