"""Find-or-create doors for the five periodic-note kinds.

``GET /journals/{kind}/...`` computes the period key + display title and hands
both to ``UserEntryService.ensure_periodic_note`` (which owns the UID scheme),
then redirects to the note page. These tests pin the key each door mints — the
vault authors the SAME key from frontmatter (``quarter_of``/``year_of``), so a
drift here silently splits a period into two nodes.

All five doors must stay declared ABOVE the ``{entry_uid}`` catch-all;
``test_kind_doors_are_not_swallowed_by_the_catch_all`` is that guarantee.
Harness mirrors ``test_journals_planning_panel.py``.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.journals_routes import create_journals_routes
from core.utils.result_simplified import Result

_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )


def _client() -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    user_entry = MagicMock()

    async def _ensure(user_uid: str, kind: str, period_key: str, title: str) -> Result[str]:
        return Result.ok(f"ue:{kind}:{user_uid}:{period_key}")

    user_entry.ensure_periodic_note = AsyncMock(side_effect=_ensure)

    services = MagicMock()
    services.user = MagicMock()
    services.user_entry = user_entry
    services.calendar = MagicMock()
    create_journals_routes(app, rt, services)
    return TestClient(app, follow_redirects=False), user_entry


def _door(path: str) -> tuple[tuple[str, str, str, str], str]:
    """Drive one door; return ``ensure_periodic_note``'s args + the redirect."""
    client, user_entry = _client()
    response = client.get(path)
    assert response.status_code == 302, path
    return user_entry.ensure_periodic_note.await_args.args, response.headers["location"]


def test_quarterly_door_mints_the_quarter_key() -> None:
    args, location = _door("/journals/quarterly/2026/3")
    assert args == (_USER_UID, "quarterly", "2026-Q3", "Quarterly Note: Q3 2026")
    assert location == f"/journals/ue:quarterly:{_USER_UID}:2026-Q3"


def test_yearly_door_mints_the_year_key() -> None:
    args, location = _door("/journals/yearly/2026")
    assert args == (_USER_UID, "yearly", "2026", "Yearly Note: 2026")
    assert location == f"/journals/ue:yearly:{_USER_UID}:2026"


def test_ride_along_daily_weekly_monthly_doors_keep_their_keys() -> None:
    """The three shipped doors are the grammar the two new ones mirror."""
    assert _door("/journals/daily/2026-08-04")[0][1:3] == ("daily", "2026-08-04")
    assert _door("/journals/weekly/2026/32")[0][1:3] == ("weekly", "2026-W32")
    assert _door("/journals/monthly/2026/8")[0][1:3] == ("monthly", "2026-08")


@pytest.mark.parametrize("quarter", [0, 5, 13])
def test_out_of_range_quarter_degrades_to_the_current_one(quarter: int) -> None:
    """Never a 500, and never a key no parser accepts (``2026-Q5`` would make
    the note panel-less forever). Mirrors the daily door's bad-date fallback."""
    args, _location = _door(f"/journals/quarterly/2026/{quarter}")
    assert args[2] == f"2026-Q{(date.today().month - 1) // 3 + 1}"


@pytest.mark.parametrize("year", [0, 99, 12345])
def test_out_of_width_year_degrades_to_the_current_one(year: int) -> None:
    """``yearly_period_start`` demands exactly four digits — a 3- or 5-digit
    year would mint a note its own panel could never parse."""
    args, _location = _door(f"/journals/yearly/{year}")
    assert args[2] == str(date.today().year)


def test_kind_doors_are_not_swallowed_by_the_catch_all() -> None:
    """``/journals/{entry_uid}`` would match ``/journals/yearly`` — every kind
    door must stay declared above it (FastHTML resolves in declaration order)."""
    client, user_entry = _client()
    for path in (
        "/journals/daily/2026-08-04",
        "/journals/weekly/2026/32",
        "/journals/monthly/2026/8",
        "/journals/quarterly/2026/3",
        "/journals/yearly/2026",
    ):
        assert client.get(path).status_code == 302, path
    assert user_entry.ensure_periodic_note.await_count == 5
