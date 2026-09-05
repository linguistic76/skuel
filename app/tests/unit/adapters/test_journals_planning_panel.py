"""Periodic-note page read panel — route gate tests (periodic-notes arc S3).

The WEEKLY and MONTHLY note pages carry the panel over their own range; the
daily note stays panel-less; a failed calendar fetch degrades to a panel-less
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
