"""The navbar "Notes" picker: five periodic notes, one door, period-aware.

The picker moved off the calendar toolbar into the top bar, so the period each
row opens is no longer handed to it by the page — it is read off the request
path. These tests pin that derivation against the paths the routes actually
register (``adapters/inbound/calendar_ui.py``, ``today_routes.py``,
``journals_routes.py``): a route rename that is not mirrored in
``viewed_period`` silently degrades every row to "current period", which no
page would fail on.
"""

import re
from datetime import date

from fasthtml.common import to_xml

from ui.journals.period_links import PERIOD_KINDS, period_link
from ui.layouts.navbar import create_navbar
from ui.layouts.period_notes import PeriodNotesPicker, viewed_period
from ui.profile.hub import ProfileHubView

# ---------------------------------------------------------------------------
# viewed_period — the path IS the view context
# ---------------------------------------------------------------------------


def test_month_view_path_names_the_month_on_screen() -> None:
    assert viewed_period("/cal/month/2026/10") == ("monthly", date(2026, 10, 1))


def test_week_view_path_names_the_week_on_screen() -> None:
    # /cal/week/{date_str} carries a date, not an ISO week number.
    assert viewed_period("/cal/week/2026-08-20") == ("weekly", date(2026, 8, 20))


def test_today_lens_path_names_the_viewed_day() -> None:
    assert viewed_period("/today/2026-08-02") == ("daily", date(2026, 8, 2))
    assert viewed_period("/today") == ("daily", date.today())


def test_bare_calendar_redirect_paths_still_name_their_period() -> None:
    """/cal/month and /cal/week answer with a 302, but a shown period is a
    property of the path, not of who rendered it."""
    assert viewed_period("/cal/month") == ("monthly", date.today().replace(day=1))
    assert viewed_period("/cal/week") == ("weekly", date.today())


def test_periodic_note_paths_round_trip_through_period_link() -> None:
    """Reading a note's own URL back out yields the same URL — the derivation
    and the link builder agree on every period's boundary, including the
    quarter and the ISO week that cross month ends."""
    ref = date(2026, 8, 20)
    for kind in PERIOD_KINDS:
        href = period_link(kind, ref).href
        derived_kind, derived_date = viewed_period(href)
        assert derived_kind == kind, href
        assert period_link(derived_kind, derived_date).href == href


def test_pages_that_show_no_period_get_no_view() -> None:
    for path in ("/", "/explore", "/tasks", "/profile", "/cal/optimize"):
        kind, ref = viewed_period(path)
        assert kind == "", path
        assert ref == date.today()


def test_a_malformed_url_degrades_to_no_view_instead_of_raising() -> None:
    """The navbar renders on every page: a hand-typed URL must cost a menu
    row's precision, never the page around it."""
    for path in (
        "/cal/month/2026/13",
        "/cal/week/not-a-date",
        "/today/2026-02-30",
        "/journals/weekly/2026/99",
        "/journals/quarterly/2026/5",
        "/journals/monthly/2026",
    ):
        assert viewed_period(path)[0] == "", path


def test_a_period_kind_with_no_argument_keeps_the_current_period() -> None:
    assert viewed_period("/journals/daily") == ("daily", date.today())


# ---------------------------------------------------------------------------
# The picker: own row follows the view, every other row opens the current period
# ---------------------------------------------------------------------------


def test_picker_lists_all_five_periods() -> None:
    html = to_xml(PeriodNotesPicker("/explore"))
    for name in ("Daily", "Weekly", "Monthly", "Quarterly", "Yearly"):
        assert f">{name}</span>" in html, name


def test_own_period_row_follows_the_view() -> None:
    """The month view's Monthly row opens the month ON SCREEN — the behaviour
    the toolbar picker carried before the move."""
    html = to_xml(PeriodNotesPicker("/cal/month/1999/2"))
    assert 'href="/journals/monthly/1999/2"' in html


def test_other_rows_open_the_current_period() -> None:
    """A month view far from today: only the Monthly row moves with the view."""
    html = to_xml(PeriodNotesPicker("/cal/month/1999/2"))
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    assert "/journals/yearly/1999" not in html
    assert f'href="/journals/yearly/{today.year}"' in html
    assert f'href="/journals/quarterly/{today.year}/{quarter}"' in html


def test_a_page_with_no_period_opens_the_current_one_on_every_row() -> None:
    html = to_xml(PeriodNotesPicker("/explore"))
    today = date.today()
    assert f'href="/journals/daily/{today.isoformat()}"' in html
    assert f'href="/journals/monthly/{today.year}/{today.month}"' in html


def test_picker_is_a_keyboard_operable_disclosure() -> None:
    """Accessible name + expanded state on the trigger, Escape returns focus."""
    html = to_xml(PeriodNotesPicker("/today"))
    assert 'aria-controls="period-note-menu"' in html
    assert 'aria-expanded="false"' in html
    assert ":aria-expanded=\"open ? 'true' : 'false'\"" in html
    assert "$refs.trigger.focus()" in html
    # Every row carries a name that survives the icon-free trailing label.
    assert 'aria-label="Quarterly note' in html


# ---------------------------------------------------------------------------
# Navbar placement — one Notes door everywhere, one sign-out door per width
# ---------------------------------------------------------------------------


def _authed_navbar(path: str = "/explore") -> str:
    return to_xml(create_navbar(current_user="user_mike", is_authenticated=True, path=path))


def test_navbar_carries_the_picker_and_it_follows_the_page() -> None:
    html = _authed_navbar("/cal/month/2026/10")
    assert html.count('id="period-note-menu"') == 1
    assert 'href="/journals/monthly/2026/10"' in html


def test_anonymous_navbar_has_no_picker() -> None:
    html = to_xml(create_navbar(is_authenticated=False, path="/"))
    assert "period-note-menu" not in html


def _logout_tag(html: str) -> str:
    """The opening ``<a ... href="/logout" ...>`` tag, with its classes."""
    match = re.search(r"<a[^>]*href=\"/logout\"[^>]*>", html)
    assert match is not None, "no sign-out link rendered"
    return match.group(0)


def test_signout_is_desktop_only_and_profile_carries_the_phone_door() -> None:
    """Six 44px icons plus the brand overflow a 320px top bar, so sign-out
    gives way — and /profile picks it up at exactly the width it disappears."""
    assert "hidden sm:inline-flex" in _logout_tag(_authed_navbar())
    assert "sm:hidden" in _logout_tag(to_xml(ProfileHubView()))
