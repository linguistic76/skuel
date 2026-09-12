"""The activity sidebar's calendar/Today variant (calendar-priority-lens arc E.1).

Ruling 6: the calendar and Today pages carry a slimmer sidebar — the temporal
lenses, the Journal and a Reports door — with no domain rows and no
``/api/sidebar/badges`` request (that request builds the rich UserContext to
fill badges these rows never show). Domain pages keep the full list and the
request.
"""

from __future__ import annotations

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from ui.activities.nav import (
    ACTIVITY_SIDEBAR_ITEMS,
    CALENDAR_SIDEBAR_ITEMS,
    render_activity_sidebar_page,
)
from ui.patterns.sidebar import SidebarItem, SidebarNav


def test_calendar_variant_rows_are_the_lenses_the_journal_and_the_reports_door() -> None:
    assert [item.slug for item in CALENDAR_SIDEBAR_ITEMS] == [
        "today",
        "weekly",
        "monthly",
        "journals",
        "reports",
    ]
    reports = CALENDAR_SIDEBAR_ITEMS[-1]
    assert reports.href == "/activity-reports/latest"
    # The full list keeps every domain row — and the same three lenses first.
    assert [item.slug for item in ACTIVITY_SIDEBAR_ITEMS[:3]] == ["today", "weekly", "monthly"]
    assert {"tasks", "goals", "habits", "principles", "choices"} <= {
        item.slug for item in ACTIVITY_SIDEBAR_ITEMS
    }


def test_the_variant_issues_no_badge_request_and_the_full_list_does() -> None:
    variant = to_xml(
        render_activity_sidebar_page("x", active="today", items=CALENDAR_SIDEBAR_ITEMS)
    )
    full = to_xml(render_activity_sidebar_page("x", active="tasks"))
    assert "/api/sidebar/badges" not in variant
    assert 'hx-get="/api/sidebar/badges"' in full
    assert 'href="/activity-reports/latest"' in variant
    assert 'href="/tasks"' not in variant
    assert 'href="/tasks"' in full


def test_sidebar_nav_badges_gate_removes_the_loader_attributes() -> None:
    items = [SidebarItem("A", "/a", "a")]
    with_badges = to_xml(SidebarNav(items, active="a", title="T"))
    without = to_xml(SidebarNav(items, active="a", title="T", badges=False))
    assert 'hx-get="/api/sidebar/badges"' in with_badges and 'hx-trigger="load"' in with_badges
    assert "hx-get" not in without
