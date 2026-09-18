"""The period-key parsers — one canonical spelling per kind, nothing else admitted.

``core/utils/period_keys.py`` is the contract behind every surface that names a
period as a string: the periodic notes' UID scheme (``ensure_periodic_note``),
the navigator's anchor on the note page (``_note_anchor``), and the activity
reports' calendar-aligned tokens. The four written forms overlap dangerously —
``2026-Q3`` and ``2026-W32`` share a shape, ``2026`` is a prefix of the other
three — so each parser must answer ``None`` for every key that is not its own;
a coerced key would silently anchor the wrong period.
"""

from __future__ import annotations

from datetime import date

from core.utils.period_keys import (
    monthly_period_start,
    quarterly_period_start,
    weekly_period_start,
    yearly_period_start,
)

_FOREIGN_KEYS = ("2026-W32", "2026-08", "2026-08-03", "2026-Q3", "2026")


def test_weekly_period_start_parses_the_contract_form() -> None:
    monday = weekly_period_start("2026-W32")
    assert monday == date(2026, 8, 3)
    assert monday is not None and monday.weekday() == 0  # Monday-start, permanent


def test_weekly_period_start_rejects_non_weekly_keys() -> None:
    assert weekly_period_start("2026-08-03") is None  # a daily key
    assert weekly_period_start("2026-08") is None  # a monthly key
    assert weekly_period_start("junk") is None
    assert weekly_period_start("2026-W99") is None  # no such ISO week


def test_monthly_period_start_parses_the_contract_form() -> None:
    assert monthly_period_start("2026-08") == date(2026, 8, 1)
    assert monthly_period_start("2026-12") == date(2026, 12, 1)


def test_monthly_period_start_rejects_non_monthly_keys() -> None:
    assert monthly_period_start("2026-08-03") is None  # a daily key — never truncated
    assert monthly_period_start("2026-W32") is None  # a weekly key
    assert monthly_period_start("2026") is None
    assert monthly_period_start("junk") is None
    assert monthly_period_start("2026-13") is None  # no such month


def test_quarterly_period_start_parses_the_contract_form() -> None:
    assert quarterly_period_start("2026-Q1") == date(2026, 1, 1)
    assert quarterly_period_start("2026-Q3") == date(2026, 7, 1)
    assert quarterly_period_start("2026-Q4") == date(2026, 10, 1)


def test_quarterly_period_start_rejects_an_out_of_range_quarter() -> None:
    """Q5 would wrap into month 13 — rejected, never coerced."""
    assert quarterly_period_start("2026-Q0") is None
    assert quarterly_period_start("2026-Q5") is None


def test_yearly_period_start_parses_the_contract_form() -> None:
    assert yearly_period_start("2026") == date(2026, 1, 1)
    assert yearly_period_start("2024") == date(2024, 1, 1)


def test_every_parser_rejects_every_foreign_key_form() -> None:
    parsers = {
        "2026-W32": weekly_period_start,
        "2026-08": monthly_period_start,
        "2026-Q3": quarterly_period_start,
        "2026": yearly_period_start,
    }
    for own_key, parser in parsers.items():
        assert parser(own_key) is not None, own_key
        for foreign in _FOREIGN_KEYS:
            if foreign == own_key:
                continue
            assert parser(foreign) is None, f"{parser.__name__} accepted {foreign}"
