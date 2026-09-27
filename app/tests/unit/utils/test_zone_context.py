"""Unit tests for core.utils.zone_context — whose zone a calendar value is read in.

The app default is ``SKUEL_TIMEZONE`` (America/Vancouver when unset or blank);
a user's choice is an IANA name zoneinfo lists, validated strictly at the doors
(``validated_zone_name``) and resolved leniently from storage (``zone_for``);
``current_zone()`` is the request's zone, else the app default.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest
from structlog.testing import capture_logs

from core.utils.zone_context import (
    DEFAULT_TIMEZONE,
    configured_zone_name,
    current_zone,
    current_zone_var,
    default_zone,
    validated_zone_name,
    zone_for,
    zone_names,
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
