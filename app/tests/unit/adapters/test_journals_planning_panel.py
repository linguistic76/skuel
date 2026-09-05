"""Periodic-note page read panel — route gate tests (periodic-notes arc S3).

The WEEKLY, MONTHLY, QUARTERLY and YEARLY note pages carry the panel over their
own range; the daily note stays panel-less; a failed calendar fetch degrades to a panel-less
page (the note is primary, never a 5xx); a vault-ingested note (no
``period_key`` metadata stamp) derives its period from the UID's last colon
segment. Harness mirrors ``test_journals_discussion_routes.py`` — real
``fast_app`` + mocked services.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.journals_routes import create_journals_routes
from core.models.enums.entity_enums import EntityStatus
from core.models.event.calendar_models import CalendarItem, CalendarItemType
from core.models.user_entry.user_entry import UserEntry
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_test"


def _fake_require_authenticated_user(request: object) -> str:
    return _USER_UID


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "adapters.inbound.journals_routes.require_authenticated_user",
        _fake_require_authenticated_user,
    )


def _entry(kind: str, period_key: str, *, stamp_period_key: bool = True) -> UserEntry:
    created = datetime(2026, 8, 1, 8, 0)
    metadata: dict[str, str] = {"entry_kind": kind}
    if stamp_period_key:
        metadata["period_key"] = period_key
    return UserEntry(
        uid=f"ue:{kind}:{_USER_UID}:{period_key}",
        user_uid=_USER_UID,
        title=f"{kind.title()} Note",
        content="",
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        metadata=metadata,
    )


def _task(day: date) -> CalendarItem:
    start = datetime.combine(day, datetime.min.time().replace(hour=9))
    return CalendarItem(
        uid="task-task_1",
        source_uid="task_1",
        item_type=CalendarItemType.TASK,
        title="Write draft",
        start_time=start,
        end_time=start,
    )


def _client(
    entry: UserEntry,
    calendar_result: Result[list[CalendarItem]] | None = None,
) -> tuple[TestClient, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)

    user_entry = MagicMock()
    user_entry.get_entry = AsyncMock(return_value=Result.ok(entry))
    user_entry.update_entry = AsyncMock(return_value=Result.ok(entry))
    # Periodic-ness is a model predicate (UserEntry.is_periodic_note) — the
    # real entry's entry_kind metadata answers it; nothing to mock.

    calendar = MagicMock()
    calendar.get_planning_items = AsyncMock(
        return_value=(
            calendar_result if calendar_result is not None else Result.ok([_task(date(2026, 8, 4))])
        )
    )

    services = MagicMock()
    services.user = MagicMock()
    services.user_entry = user_entry
    services.calendar = calendar
    create_journals_routes(app, rt, services)
    return TestClient(app), calendar


def _get_note_page(client: TestClient, entry_uid: str) -> str:
    response = client.get(f"/journals/{entry_uid}", headers={"HX-Request": "true"})
    assert response.status_code == 200
    return response.text


def test_weekly_note_page_shows_the_week_panel() -> None:
    entry = _entry("weekly", "2026-W32")
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    assert "This week" in body
    assert "Tasks + Events" in body and "Goals + Habits" in body
    assert "Write draft" in body
    assert 'href="/today/2026-08-04"' in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 8, 3), date(2026, 8, 9)
    )


def test_monthly_note_page_shows_the_month_panel() -> None:
    """Parity: the monthly note plans against its own month."""
    entry = _entry("monthly", "2026-08")
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    assert "This month" in body and "August 2026" in body
    assert "Write draft" in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 8, 1), date(2026, 8, 31)
    )


def test_vault_ingested_weekly_note_derives_week_from_uid() -> None:
    """No ``period_key`` metadata stamp (vault ingestion) — the UID's last
    colon segment carries the same key form (the join contract)."""
    entry = _entry("weekly", "2026-W32", stamp_period_key=False)
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 8, 3), date(2026, 8, 9)
    )


def test_vault_ingested_monthly_note_derives_month_from_uid() -> None:
    entry = _entry("monthly", "2026-08", stamp_period_key=False)
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 8, 1), date(2026, 8, 31)
    )


def test_daily_note_page_has_no_panel() -> None:
    entry = _entry("daily", "2026-08-04")
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' not in body
    calendar.get_planning_items.assert_not_called()


def test_failed_panel_fetch_degrades_to_a_panel_less_page() -> None:
    """The note is the primary surface — a calendar failure never 5xxs it."""
    entry = _entry("weekly", "2026-W32")
    client, _calendar = _client(
        entry, calendar_result=Result.fail(Errors.database("calendar.get_planning_items", "boom"))
    )

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' not in body
    assert "Weekly Note" in body  # the editor still renders


def test_quarterly_note_page_shows_the_quarter_panel() -> None:
    entry = _entry("quarterly", "2026-Q3")
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    # Escaped: ruff flags a literal en dash as confusable, and the label must
    # match the panel byte-for-byte.
    assert "This quarter" in body and "Q3 2026 \u00b7 Jul \u2013 Sep" in body
    assert "Write draft" in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 7, 1), date(2026, 9, 30)
    )


def test_yearly_note_page_shows_the_year_panel() -> None:
    entry = _entry("yearly", "2026")
    client, calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'id="planning-panel"' in body
    assert "This year" in body
    assert "Write draft" in body
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 1, 1), date(2026, 12, 31)
    )


def test_vault_ingested_quarterly_note_derives_quarter_from_uid() -> None:
    """No ``period_key`` stamp (vault ingestion) — the UID's last colon segment
    carries the same key form. ``2026-Q3`` must not read as a weekly key."""
    entry = _entry("quarterly", "2026-Q3", stamp_period_key=False)
    client, calendar = _client(entry)

    assert 'id="planning-panel"' in _get_note_page(client, entry.uid)
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 7, 1), date(2026, 9, 30)
    )


def test_vault_ingested_yearly_note_derives_year_from_uid() -> None:
    entry = _entry("yearly", "2026", stamp_period_key=False)
    client, calendar = _client(entry)

    assert 'id="planning-panel"' in _get_note_page(client, entry.uid)
    calendar.get_planning_items.assert_awaited_once_with(
        _USER_UID, date(2026, 1, 1), date(2026, 12, 31)
    )


# The month sub-head's own class — a month NAME is not a usable marker on a
# page whose period rail also names months ("Open the July 2026 note").
_SUB_HEAD_MARKER = "tracking-[0.06em]"


def test_long_period_pages_sub_head_their_rows_by_month() -> None:
    """The panel's long-period affordance reaches the page (quarterly/yearly)
    and leaves the weekly page's flat list alone."""
    quarterly = _entry("quarterly", "2026-Q3")
    client, _cal = _client(quarterly)
    quarterly_body = _get_note_page(client, quarterly.uid)
    assert _SUB_HEAD_MARKER in quarterly_body
    assert "August 2026" in quarterly_body

    weekly = _entry("weekly", "2026-W32")
    client, _cal = _client(weekly)
    assert _SUB_HEAD_MARKER not in _get_note_page(client, weekly.uid)


def test_every_periodic_kind_reaches_every_other_period_from_its_own_page() -> None:
    """The sidebar's period rail is the in-note door to all five periods — and
    for the quarterly and yearly notes one of only two doors anywhere, since
    the calendar has week and month views only (ruling 2026-09-05).

    Route-level, not component-level: the rail is only a door if the served
    page carries it. Which *period* each row opens is anchored to the note and
    pinned in ``tests/unit/ui/test_periodic_note_sidebar.py``; this pins that
    the route reaches all five rows on every kind.
    """
    pages = {
        "daily": "2026-08-04",
        "weekly": "2026-W32",
        "monthly": "2026-08",
        "quarterly": "2026-Q3",
        "yearly": "2026",
    }
    for kind, period_key in pages.items():
        client, _cal = _client(_entry(kind, period_key))
        body = _get_note_page(client, f"ue:{kind}:{_USER_UID}:{period_key}")
        for row_kind in pages:
            assert f'href="/journals/{row_kind}/' in body, (
                f"{kind} note is missing its {row_kind} rail row"
            )


def test_the_rail_anchors_every_row_on_the_note_own_period() -> None:
    """An August note's wider rows name August's quarter and year — the anchor
    is the note's period, not today's. A yearly note anchors on January, so its
    quarterly row is Q1: the rail follows the note, and says which period it
    landed on."""
    client, _cal = _client(_entry("monthly", "2026-08"))
    august = _get_note_page(client, f"ue:monthly:{_USER_UID}:2026-08")
    assert 'href="/journals/quarterly/2026/3"' in august
    assert 'href="/journals/yearly/2026"' in august

    client, _cal = _client(_entry("yearly", "2026"))
    year = _get_note_page(client, f"ue:yearly:{_USER_UID}:2026")
    assert 'href="/journals/quarterly/2026/1"' in year
    assert 'href="/journals/monthly/2026/1"' in year


def test_the_yearly_note_steps_between_years_and_still_reaches_every_period() -> None:
    """A year contains no wider period, which under the old "up"-links ladder
    left the yearly note with no rail at all. The rail is kind-independent:
    the widest note still steps its own period and still reaches the narrower
    ones."""
    entry = _entry("yearly", "2026")
    client, _cal = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert 'href="/journals/yearly/2025"' in body  # prev
    assert 'href="/journals/yearly/2027"' in body  # next
    for narrower in ("/journals/weekly/", "/journals/monthly/", "/journals/quarterly/"):
        assert narrower in body


# ---------------------------------------------------------------------------
# The save guard — the fourth thing PERIODIC_NOTE_KINDS membership switches on
# ---------------------------------------------------------------------------


def _save_note(entry: UserEntry, *, content: str = "edited") -> str:
    """POST the note-save route as its owner; return the status fragment."""
    from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token

    client, _calendar = _client(entry)
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    response = client.post(
        f"/journals/{entry.uid}/note",
        data={"content": content},
        headers={CSRF_HEADER_NAME: token},
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.parametrize("kind,period_key", [("quarterly", "2026-Q3"), ("yearly", "2026")])
def test_new_kinds_pass_the_note_save_guard(kind: str, period_key: str) -> None:
    """The guard is ``is_periodic_note()`` — a kind outside PERIODIC_NOTE_KINDS
    is refused as "Not a periodic note", so an unwidened frozenset would leave
    these two notes readable but unsaveable."""
    assert "Saved" in _save_note(_entry(kind, period_key))


def test_a_non_periodic_entry_is_still_refused_by_the_save_guard() -> None:
    """Widening the vocabulary must not open the route to every entry kind."""
    entry = _entry("weekly", "2026-W32")
    entry = UserEntry(
        uid="ue_abcd1234",
        user_uid=_USER_UID,
        title="Turn-in",
        content="",
        status=entry.status,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        metadata={},
    )
    assert "Not a periodic note" in _save_note(entry)
