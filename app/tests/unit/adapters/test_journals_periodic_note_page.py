"""The periodic-note page — its route-level shape (``GET /journals/{entry_uid}``).

The page is the note's editor with its period navigator beside it, served
INSIDE the Tasks+ sidebar page like the activity domains, the calendar views and
Today: the sidebar's Journal row is lit, the sidebar heading stays "Tasks+"
while the browser title is the note's, and nothing is read from the calendar
on the way (the page carries no planning panel). Every kind reaches every other
period through the navigator's rail, and the note-save guard admits every
periodic kind and nothing else. Harness mirrors
``test_journals_discussion_routes.py`` — real ``fast_app`` + mocked services.
"""

from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.journals_routes import create_journals_routes
from core.models.enums.entity_enums import EntityStatus
from core.models.user_entry.user_entry import UserEntry
from core.utils.result_simplified import Result
from ui.activities.nav import ACTIVITY_SIDEBAR_TITLE

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


def _client(entry: UserEntry) -> tuple[TestClient, MagicMock]:
    """A journals app over one owned entry; returns the client + the calendar mock."""
    app, rt = fast_app(pico=False, default_hdrs=False)

    user_entry = MagicMock()
    user_entry.get_entry = AsyncMock(return_value=Result.ok(entry))
    user_entry.update_entry = AsyncMock(return_value=Result.ok(entry))
    # Periodic-ness is a model predicate (UserEntry.is_periodic_note) — the
    # real entry's entry_kind metadata answers it; nothing to mock.

    calendar = MagicMock()

    services = MagicMock()
    services.user = MagicMock()
    services.user_entry = user_entry
    services.calendar = calendar
    create_journals_routes(app, rt, services)
    return TestClient(app), calendar


def _get_note_page(client: TestClient, entry_uid: str) -> str:
    """The served page — always the full document (the route has no HTMX branch)."""
    response = client.get(f"/journals/{entry_uid}")
    assert response.status_code == 200
    return response.text


# ---------------------------------------------------------------------------
# The shell — the Tasks+ sidebar page, Journal row lit
# ---------------------------------------------------------------------------


def test_the_note_page_is_served_inside_the_tasks_sidebar_with_journal_lit() -> None:
    """The same shell as /tasks, /cal and /today. The lit row is the Journal
    row — whose href is the dateless daily door — not a calendar view."""
    entry = _entry("weekly", "2026-W32")
    client, _calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert f'aria-label="{ACTIVITY_SIDEBAR_TITLE} sidebar"' in body
    assert re.search(r'href="/journals/daily"[^>]*bg-accent font-semibold', body), (
        "the Journal row is not the active sidebar row"
    )
    assert re.search(r'href="/cal/week"[^>]*bg-accent font-semibold', body) is None


def test_the_sidebar_heading_stays_tasks_plus_while_the_title_is_the_note() -> None:
    """One heading on every page that carries the sidebar; the note names only
    the browser tab."""
    entry = _entry("weekly", "2026-W32")
    client, _calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert re.search(rf"<h3[^>]*>{re.escape(ACTIVITY_SIDEBAR_TITLE)}</h3>", body)
    assert "<title>Weekly Note - SKUEL</title>" in body
    assert "Weekly Note</h3>" not in body


def test_editor_then_navigator_and_no_planning_panel_on_any_kind() -> None:
    """Every kind renders the editor first and the navigator after it, reads
    nothing from the calendar, and carries no planning panel — the period's
    entities are read on the calendar and Today, not beside the note."""
    for kind, period_key in {
        "daily": "2026-08-04",
        "weekly": "2026-W32",
        "monthly": "2026-08",
        "quarterly": "2026-Q3",
        "yearly": "2026",
    }.items():
        client, calendar = _client(_entry(kind, period_key))
        body = _get_note_page(client, f"ue:{kind}:{_USER_UID}:{period_key}")

        assert body.index('id="journal-workspace"') < body.index('id="period-navigator"'), kind
        assert 'id="planning-panel"' not in body, kind
        assert "Tasks + Events" not in body, kind
        assert calendar.mock_calls == [], f"{kind} note read the calendar: {calendar.mock_calls}"


def test_a_vault_ingested_note_anchors_its_navigator_on_the_uid_period() -> None:
    """No ``period_key`` metadata stamp (vault ingestion) — the UID's last colon
    segment carries the same key form (the join contract), so the navigator
    still centres on the note's own period, not on today."""
    entry = _entry("quarterly", "2026-Q3", stamp_period_key=False)
    client, _calendar = _client(entry)

    body = _get_note_page(client, entry.uid)

    assert "July 2026" in body  # the mini month opens on the quarter's first month
    assert 'aria-label="Quarterly note — Q3 2026" aria-current="page"' in body


# ---------------------------------------------------------------------------
# The rail — the in-note door to every period
# ---------------------------------------------------------------------------


def test_every_periodic_kind_reaches_every_other_period_from_its_own_page() -> None:
    """The navigator's period rail is the in-note door to all five periods — and
    for the quarterly and yearly notes one of only two doors anywhere, since
    the calendar has week and month views only (ruling 2026-09-05).

    Route-level, not component-level: the rail is only a door if the served
    page carries it. Which *period* each row opens is anchored to the note and
    pinned in ``tests/unit/ui/test_periodic_note_navigator.py``; this pins that
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
