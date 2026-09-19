"""The Tasks+ sidebar — the Journal row's door and the heading/title split.

Two things every page that carries the sidebar relies on: the Journal row opens
the periodic notes through the DATELESS daily door (so the constant item list
never freezes "today" at import time), and the sidebar heading is one name on
every page while ``title`` names only the browser tab.
"""

from __future__ import annotations

import re

from fasthtml.common import Div, to_xml

from ui.activities.nav import (
    ACTIVITY_SIDEBAR_ITEMS,
    ACTIVITY_SIDEBAR_TITLE,
    render_activity_sidebar_error,
    render_activity_sidebar_page,
)
from ui.components._icon_data import ICON_PATHS


def test_the_journal_row_opens_todays_daily_note_through_the_dateless_door() -> None:
    journal = next(item for item in ACTIVITY_SIDEBAR_ITEMS if item.slug == "journals")

    assert journal.href == "/journals/daily"
    assert journal.label == "Journal"


def test_the_gradebook_row_is_the_last_door_and_opens_the_one_gradebook_page() -> None:
    gradebook = ACTIVITY_SIDEBAR_ITEMS[-1]

    assert gradebook.slug == "gradebook"
    assert gradebook.href == "/gradebook"
    assert gradebook.label == "GradeBook"


def test_the_sidebar_heading_never_follows_the_page_title() -> None:
    xml = to_xml(
        render_activity_sidebar_page(Div("x"), active="journals", title="Weekly Note: W38, 2026")
    )

    assert re.search(rf"<h3[^>]*>{re.escape(ACTIVITY_SIDEBAR_TITLE)}</h3>", xml)
    assert "<title>Weekly Note: W38, 2026 - SKUEL</title>" in xml
    assert "Weekly Note: W38, 2026</h3>" not in xml


def test_the_default_title_is_the_heading() -> None:
    xml = to_xml(render_activity_sidebar_page(Div("x"), active="tasks"))

    assert f"<title>{ACTIVITY_SIDEBAR_TITLE} - SKUEL</title>" in xml


def test_the_error_page_names_its_tab_like_any_other_sidebar_page() -> None:
    xml = to_xml(
        render_activity_sidebar_error("Report not found", active="gradebook", title="GradeBook")
    )

    assert "<title>GradeBook - SKUEL</title>" in xml
    assert "Report not found" in xml
    assert re.search(rf"<h3[^>]*>{re.escape(ACTIVITY_SIDEBAR_TITLE)}</h3>", xml)


def test_the_events_row_follows_habits_and_carries_a_registered_icon() -> None:
    slugs = [item.slug for item in ACTIVITY_SIDEBAR_ITEMS]
    events = ACTIVITY_SIDEBAR_ITEMS[slugs.index("events")]

    assert slugs.index("events") == slugs.index("habits") + 1
    assert events.href == "/events"
    assert events.label == "Events"
    assert events.icon in ICON_PATHS  # a lucide name — an unregistered one renders help-circle


def test_the_events_pages_light_their_own_row() -> None:
    xml = to_xml(render_activity_sidebar_page(Div("x"), active="events"))

    assert re.search(r'<a href="/events"[^>]*aria-current="page"', xml)
    assert not re.search(r'<a href="/cal/month"[^>]*aria-current="page"', xml)
