"""Unit tests for core.utils.zone_context — whose zone a calendar value is read in.

The app default is ``SKUEL_TIMEZONE`` (America/Vancouver when unset or blank);
a user's choice is an IANA name zoneinfo lists, validated strictly at the doors
(``validated_zone_name``) and resolved leniently from storage (``zone_for``);
``current_zone()`` is the request's zone, else the app default.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from structlog.testing import capture_logs

from core.utils import timestamp_helpers
from core.utils.zone_context import (
    DEFAULT_TIMEZONE,
    configured_zone_name,
    current_zone,
    current_zone_var,
    default_zone,
    today_in_current_zone,
    validated_zone_name,
    zone_for,
    zone_names,
    zone_scope,
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """SKUEL_TIMEZONE unset; a test sets it through the returned patcher."""
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    return monkeypatch


class TestZoneNames:
    def test_iana_names_are_listed(self) -> None:
        names = zone_names()
        assert {"America/Vancouver", "Asia/Bangkok", "UTC", "Europe/Lisbon"} <= names

    def test_the_hosts_own_alias_is_not(self) -> None:
        # zoneinfo lists "localtime" wherever the host's zone directory links it;
        # a choice naming it would follow whichever machine runs the app.
        assert "localtime" not in zone_names()

    def test_every_listed_name_loads(self) -> None:
        for name in sorted(zone_names()):
            assert ZoneInfo(name).key == name


class TestValidatedZoneName:
    def test_a_listed_name_is_kept(self) -> None:
        assert validated_zone_name("Asia/Bangkok") == "Asia/Bangkok"
        assert validated_zone_name("  Asia/Bangkok  ") == "Asia/Bangkok"

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_is_no_choice(self, blank: str | None) -> None:
        assert validated_zone_name(blank) is None

    @pytest.mark.parametrize("bad", ["Mars/Olympus", "asia/bangkok", "UTC+7", "localtime"])
    def test_anything_else_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError, match="Unknown time zone"):
            validated_zone_name(bad)


class TestDefaultZone:
    def test_unset_or_blank_is_america_vancouver(self, env: pytest.MonkeyPatch) -> None:
        assert DEFAULT_TIMEZONE == "America/Vancouver"
        assert configured_zone_name() == "America/Vancouver"
        assert default_zone() == ZoneInfo("America/Vancouver")
        env.setenv("SKUEL_TIMEZONE", "  ")
        assert default_zone() == ZoneInfo("America/Vancouver")

    def test_skuel_timezone_names_it(self, env: pytest.MonkeyPatch) -> None:
        env.setenv("SKUEL_TIMEZONE", "Asia/Bangkok")
        assert configured_zone_name() == "Asia/Bangkok"
        assert default_zone() == ZoneInfo("Asia/Bangkok")

    def test_an_unknown_name_is_refused(self, env: pytest.MonkeyPatch) -> None:
        env.setenv("SKUEL_TIMEZONE", "Mars/Olympus")
        assert configured_zone_name() == "Mars/Olympus"  # read as configured...
        with pytest.raises(ValueError, match="SKUEL_TIMEZONE='Mars/Olympus'"):
            default_zone()  # ...never built


class TestZoneFor:
    def test_a_choice_is_its_zone(self, env: pytest.MonkeyPatch) -> None:
        assert zone_for("Asia/Bangkok") == ZoneInfo("Asia/Bangkok")
        assert zone_for("UTC") == ZoneInfo("UTC")

    def test_no_choice_follows_the_app_default(self, env: pytest.MonkeyPatch) -> None:
        assert zone_for(None) == ZoneInfo("America/Vancouver")
        env.setenv("SKUEL_TIMEZONE", "Europe/Lisbon")
        assert zone_for(None) == ZoneInfo("Europe/Lisbon")
        assert zone_for("") == ZoneInfo("Europe/Lisbon")

    def test_a_stored_name_zoneinfo_does_not_list_follows_the_default_with_a_warning(
        self, env: pytest.MonkeyPatch
    ) -> None:
        with capture_logs() as logs:
            assert zone_for("Mars/Olympus") == ZoneInfo("America/Vancouver")
        assert [log["log_level"] for log in logs] == ["warning"]
        assert "Mars/Olympus" in logs[0]["event"]


class TestCurrentZone:
    def test_outside_a_request_it_is_the_app_default(self, env: pytest.MonkeyPatch) -> None:
        assert current_zone() == ZoneInfo("America/Vancouver")
        env.setenv("SKUEL_TIMEZONE", "Asia/Bangkok")
        assert current_zone() == ZoneInfo("Asia/Bangkok")

    def test_in_a_request_it_is_the_zone_the_middleware_set(self, env: pytest.MonkeyPatch) -> None:
        token = current_zone_var.set(ZoneInfo("Asia/Bangkok"))
        try:
            assert current_zone() == ZoneInfo("Asia/Bangkok")
        finally:
            current_zone_var.reset(token)
        assert current_zone() == ZoneInfo("America/Vancouver")


# 02:00Z on 2026-09-28: the 27th in Vancouver, the 28th in Bangkok.
_FROZEN = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)


class _FrozenClock(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return _FROZEN.astimezone(tz) if tz is not None else _FROZEN.replace(tzinfo=None)


class TestTodayInCurrentZone:
    def test_it_is_today_in_the_current_zone(
        self, env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(timestamp_helpers, "datetime", _FrozenClock)
        assert today_in_current_zone() == date(2026, 9, 27)  # the default, Vancouver
        with zone_scope(ZoneInfo("Asia/Bangkok")):
            assert today_in_current_zone() == date(2026, 9, 28)


class TestZoneScope:
    def test_inside_the_scope_the_current_zone_is_the_scopes(self, env: pytest.MonkeyPatch) -> None:
        with zone_scope(ZoneInfo("Asia/Bangkok")) as zone:
            assert zone == ZoneInfo("Asia/Bangkok")
            assert current_zone() == ZoneInfo("Asia/Bangkok")
        assert current_zone() == ZoneInfo("America/Vancouver")

    def test_it_overrides_a_requests_zone_and_restores_it(self, env: pytest.MonkeyPatch) -> None:
        token = current_zone_var.set(ZoneInfo("Europe/Paris"))
        try:
            with zone_scope(ZoneInfo("Asia/Bangkok")):
                assert current_zone() == ZoneInfo("Asia/Bangkok")
            assert current_zone() == ZoneInfo("Europe/Paris")
        finally:
            current_zone_var.reset(token)

    def test_it_restores_the_zone_when_the_block_raises(self, env: pytest.MonkeyPatch) -> None:
        with pytest.raises(RuntimeError), zone_scope(ZoneInfo("Asia/Bangkok")):
            raise RuntimeError("the work failed")
        assert current_zone() == ZoneInfo("America/Vancouver")

    def test_a_task_started_inside_the_scope_inherits_it(self, env: pytest.MonkeyPatch) -> None:
        async def zone_seen_by_a_task() -> ZoneInfo:
            async def read() -> ZoneInfo:
                return current_zone()

            with zone_scope(ZoneInfo("Asia/Bangkok")):
                task = asyncio.create_task(read())
            return await task

        assert asyncio.run(zone_seen_by_a_task()) == ZoneInfo("Asia/Bangkok")
