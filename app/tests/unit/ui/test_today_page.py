"""Render tests for the Today surface page (``ui/today/page.py``).

Shape-level: the Alpine behaviour lives in ``static/js/today.js`` and is
exercised by the render-smoke gate. These guard the server-rendered pieces —
notably the day-lens Prev/Next hrefs, which must survive arbitrary ISO dates
the ``/today/{date_str}`` route accepts.
"""

from __future__ import annotations

from datetime import date

from fasthtml.common import to_xml

from ui.today.page import TodayPage, _step_day


def _ctx(today_iso: str, *, heading: str = "Today", is_today: bool = True) -> dict:
    return {
        "today_iso": today_iso,
        "date_label": "X",
        "heading": heading,
        "is_today": is_today,
        "now_hhmm": "09:00",
        "stats": {"nodes": 0, "committed_min": 0, "done": 0},
        "triage": [],
        "lifepaths": [],
        "principles": [],
        "goals": [],
        "tasks": [],
        "rituals": [],
        "kinds": {},
        "ritual_icons": {"past": "", "upcoming": ""},
    }


def test_step_day_steps_within_range() -> None:
    d = date(2026, 7, 22)
    assert _step_day(d, -1) == date(2026, 7, 21)
    assert _step_day(d, +1) == date(2026, 7, 23)


def test_step_day_clamps_at_boundaries() -> None:
    # ±1 past the representable range would raise OverflowError; clamp instead.
    assert _step_day(date.min, -1) == date.min
    assert _step_day(date.max, +1) == date.max
    # The opposite direction still steps normally at each boundary.
    assert _step_day(date.min, +1) == date(1, 1, 2)
    assert _step_day(date.max, -1) == date(9999, 12, 30)


def test_today_page_renders_at_date_boundaries() -> None:
    # Boundary dates must not crash render; the boundary arrow self-links.
    min_xml = to_xml(TodayPage(_ctx("0001-01-01", heading="Jan 1")))
    assert 'href="/today/0001-01-01"' in min_xml  # Prev clamped to self

    max_xml = to_xml(TodayPage(_ctx("9999-12-31", heading="Dec 31")))
    assert 'href="/today/9999-12-31"' in max_xml  # Next clamped to self


def test_task_rows_are_keyed_by_source_and_uid() -> None:
    """C7: a dual-membership task renders one card per surface — every card
    binding (row key, selection, drawer open) must carry the source prefix so
    the two cards act independently."""
    xml = to_xml(TodayPage(_ctx("2026-08-02")))
    # Both surfaces emit composite-key bindings, never a bare t.id key.
    assert "data-task-row=\"'triage:' + t.id\"" in xml
    assert "data-task-row=\"'ribbon:' + t.id\"" in xml
    assert 'data-task-row="t.id"' not in xml
    assert "selectedId" not in xml  # replaced by selectedKey end to end


def test_drawer_defer_buttons_have_exactly_one_transport() -> None:
    """C7: the drawer defer buttons must NOT carry an hx-post twin — the
    deferTask() fetch (with rollback-on-error) is the only request. Same for
    the complete button (identical double-submit family)."""
    xml = to_xml(TodayPage(_ctx("2026-08-02")))
    assert "/defer`" not in xml  # no `:hx-post` template literal for defer
    assert "/complete`" not in xml  # no hx-post twin on Mark complete either
    assert "deferTask(keySource(openTaskKey), keyId(openTaskKey)" in xml
