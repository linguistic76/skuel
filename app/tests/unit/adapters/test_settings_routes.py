"""The Settings preferences editor and its save door.

The editor is one form posting every field to ``/settings/save``; the time zone
is a list — the SKUEL default entry, labelled with the configured
``SKUEL_TIMEZONE``, then every name zoneinfo lists — plus a "Use this device's
time zone" button. The door refuses a name zoneinfo does not list (400,
nothing saved) and saves an empty choice as None (no choice).
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml
from starlette.datastructures import FormData

from adapters.inbound.settings_routes import create_settings_routes
from core.models.user import UserPreferences, create_user
from core.utils.result_simplified import Result

Handler = Callable[..., Awaitable[Any]]
CSRF = "tok-settings"


class _UserService:
    """Serves one user; records every preferences update."""

    def __init__(self, timezone: str | None = None) -> None:
        user = create_user(username="zone_settings", email="zs@example.com")
        self.user = dataclasses.replace(user, preferences=UserPreferences(timezone=timezone))
        self.updates: list[dict[str, Any]] = []

    async def get_user(self, _user_uid: str) -> Result[Any]:
        return Result.ok(self.user)

    async def update_preferences(self, _user_uid: str, update: dict[str, Any]) -> Result[Any]:
        self.updates.append(update)
        return Result.ok(self.user)


def _handlers(user_service: _UserService) -> dict[str, Handler]:
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def register(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return register

    create_settings_routes(SimpleNamespace(), rt, SimpleNamespace(user=user_service))
    return registered


class _Request:
    """Session-authenticated request with the CSRF pair and a form body."""

    def __init__(self, form: dict[str, str] | None = None, method: str = "GET") -> None:
        self.method = method
        self.session = {"user_uid": "user_zone_settings"}
        self.cookies = {"csrf_token": CSRF}
        self.headers = {"X-CSRF-Token": CSRF}
        self.url = SimpleNamespace(path="/settings/save")
        self.state = SimpleNamespace()
        self._form = FormData(list((form or {}).items()))

    async def form(self) -> FormData:
        return self._form


@pytest.fixture(autouse=True)
def default_zone(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    return monkeypatch


async def _editor(user_service: _UserService) -> str:
    return to_xml(await _handlers(user_service)["/settings/content"](_Request()))


def _zone_options(html: str) -> list[tuple[str, str, bool]]:
    select = re.search(r'<select[^>]*name="timezone"[^>]*>(.*?)</select>', html, re.DOTALL)
    assert select is not None, "the editor has a zone list"
    return [
        (value, label.strip(), "selected" in attrs)
        for attrs, value, label in re.findall(
            r'<option([^>]*?value="([^"]*)"[^>]*)>([^<]*)</option>', select.group(1)
        )
    ]


class TestZoneList:
    @pytest.mark.asyncio
    async def test_no_choice_selects_the_skuel_default_labelled_with_the_setting(self) -> None:
        options = _zone_options(await _editor(_UserService(timezone=None)))
        assert options[0] == ("", "SKUEL default (America/Vancouver)", True)
        assert [selected for *_, selected in options].count(True) == 1

    @pytest.mark.asyncio
    async def test_the_default_label_is_built_from_skuel_timezone(self, default_zone) -> None:
        default_zone.setenv("SKUEL_TIMEZONE", "Europe/Lisbon")
        options = _zone_options(await _editor(_UserService(timezone=None)))
        assert options[0][:2] == ("", "SKUEL default (Europe/Lisbon)")

    @pytest.mark.asyncio
    async def test_a_choice_is_selected_among_the_iana_names(self) -> None:
        options = _zone_options(await _editor(_UserService(timezone="Asia/Bangkok")))
        values = [value for value, *_ in options]
        assert {"America/Vancouver", "Asia/Bangkok", "UTC"} <= set(values)
        assert "localtime" not in values
        assert [value for value, _, selected in options if selected] == ["Asia/Bangkok"]

    @pytest.mark.asyncio
    async def test_the_device_zone_button_drives_the_list(self) -> None:
        html = await _editor(_UserService())
        button = re.search(r"<button[^>]*>Use this device's time zone</button>", html)
        assert button is not None
        assert 'type="button"' in button.group(0), "the button selects; it does not submit"
        assert "SKUEL.useDeviceZone('timezone', 'timezone-device-note')" in button.group(0)
        assert re.search(r'<p[^>]*aria-live="polite"[^>]*id="timezone-device-note"', html)


class TestOneForm:
    @pytest.mark.asyncio
    async def test_every_field_and_the_save_button_post_together(self) -> None:
        html = await _editor(_UserService())
        form = re.search(r'<form[^>]*id="preferences-form"[^>]*>(.*?)</form>', html, re.DOTALL)
        assert form is not None, "one form holds the editor"
        assert html.count("<form") == 1
        assert 'hx-post="/settings/save"' in form.group(0)
        assert 'hx-target="#settings-content"' in form.group(0)
        body = form.group(1)
        for name in (
            "learning_level",
            "preferred_time_of_day",
            "enable_reminders",
            "theme",
            "timezone",
            "weekly_task_goal",
        ):
            assert f'name="{name}"' in body, f"{name} posts with the form"
        assert re.search(r'<button[^>]*type="submit"[^>]*>Save All Changes</button>', body)


class TestSaveDoor:
    async def _save(self, user_service: _UserService, timezone: str) -> Any:
        request = _Request({"timezone": timezone, "theme": "light"}, method="POST")
        return await _handlers(user_service)["/settings/save"](request)

    @pytest.mark.asyncio
    async def test_an_unlisted_name_is_refused_and_nothing_is_saved(self) -> None:
        service = _UserService()
        response = await self._save(service, "Mars/Olympus")
        assert response.status_code == 400
        assert b"Unknown time zone 'Mars/Olympus'" in response.body
        assert service.updates == []

    @pytest.mark.asyncio
    async def test_a_listed_name_is_saved(self) -> None:
        service = _UserService()
        await self._save(service, "Asia/Bangkok")
        assert [update["timezone"] for update in service.updates] == ["Asia/Bangkok"]

    @pytest.mark.asyncio
    async def test_the_skuel_default_saves_as_no_choice(self) -> None:
        service = _UserService(timezone="Asia/Bangkok")
        await self._save(service, "")
        assert [update["timezone"] for update in service.updates] == [None]
