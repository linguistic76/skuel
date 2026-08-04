"""Unit tests for the day's RHYTHM — truthful habit chips on the calendar grid.

Habit-rhythm arc S2. The habitual week is meant to be *seen* as an ordered
sequence (M5): a morning habit sits above an afternoon event, an evening habit
below it. That ordering already existed — ``sorted(..., key=_item_start)`` in
both grids — but habit expansion bypassed it, re-stamping every occurrence chip
to midnight so all habits clustered at day start no matter what the habit said.

These tests hold the two halves that make the rhythm real:

  1. ``_items_by_date`` RE-DATES each occurrence onto its day, carrying the
     habit's time of day and duration across — verified on a day that is NOT
     today, because the base item alone would look correct on today by
     accident.
  2. The chip STATES the duration ("20m") in both views, since duration is the
     load-bearing half of the habit vocabulary (M3).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.enums import TimeOfDay
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
    CalendarView,
)
from core.models.type_hints import EntityUID
from ui.calendar.components import (
    _event_chip,
    _items_by_date,
    create_day_cell,
    create_item_details_modal,
    create_week_grid,
)

# A week that contains no "today", so nothing can pass by accident: the chips
# under test are all expansions onto days the base item was never stamped with.
WEEK_START = date(2026, 8, 3)
NON_TODAY = date(2026, 8, 6)  # Thursday of that week


def _habit_base(
    uid: str,
    title: str,
    slot: TimeOfDay | None,
    minutes: int,
    *,
    placeholder_day: date = date(2026, 8, 1),
) -> CalendarItem:
    """A habit's base calendar item: its block on a placeholder date.

    Mirrors ``CalendarService._habit_to_calendar_item`` — the date is arbitrary
    (a habit recurs); the slot, its representative hour, and the length are the
    truth it carries.
    """
    # ANYTIME's hour PLACES an unstated habit; the slot itself rides along
    # unresolved, exactly as `_habit_to_calendar_item` does it.
    placing = slot or TimeOfDay.ANYTIME
    start = datetime.combine(placeholder_day, placing.get_representative_time())
    return CalendarItem(
        uid=f"habit-{uid}",
        source_uid=uid,
        item_type=CalendarItemType.HABIT,
        title=title,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        streak_count=4,
        time_of_day=slot,
    )


def _timed_item(
    uid: str, title: str, item_type: CalendarItemType, day: date, hour: int
) -> CalendarItem:
    start = datetime.combine(day, datetime.min.time().replace(hour=hour))
    return CalendarItem(
        uid=f"{item_type.value}-{uid}",
        source_uid=uid,
        item_type=item_type,
        title=title,
        start_time=start,
        end_time=start + timedelta(hours=1),
    )


def _all_day_marker(uid: str, title: str, day: date) -> CalendarItem:
    """A goal milestone — midnight + ``all_day``, the day's top marker."""
    return CalendarItem(
        uid=f"goal-{uid}",
        source_uid=uid,
        item_type=CalendarItemType.MILESTONE,
        title=title,
        start_time=datetime.combine(day, datetime.min.time()),
        end_time=datetime.combine(day, datetime.max.time()),
        all_day=True,
    )


def _data(
    items: list[CalendarItem],
    occurrences: dict[str, list[CalendarOccurrence]],
    *,
    view: CalendarView = CalendarView.WEEK,
) -> CalendarData:
    return CalendarData(
        items=items,
        occurrences={EntityUID(k): v for k, v in occurrences.items()},
        view=view,
        start_date=WEEK_START,
        end_date=WEEK_START + timedelta(days=6),
        metadata={},
    )


def _daily(uid: str, days: list[date], status: CompletionStatus = CompletionStatus.PENDING):
    return [CalendarOccurrence(calendar_item_uid=uid, date=d, status=status) for d in days]


# ---------------------------------------------------------------------------
# _items_by_date — the block survives occurrence expansion
# ---------------------------------------------------------------------------


def test_expansion_carries_the_habits_time_of_day_onto_every_day() -> None:
    """The chip the grid sorts is the EXPANSION, not the base item.

    Re-stamping it to midnight (what this did while habit times were fabricated)
    would keep every habit at day start however truthful the base became.
    """
    base = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    days = [WEEK_START, NON_TODAY]
    by_date = _items_by_date(_data([base], {"habit_1": _daily("habit_1", days)}))

    for day in days:
        chip = by_date[day][0]
        assert chip.start_time == datetime.combine(day, datetime.min.time().replace(hour=9))
        assert chip.end_time - chip.start_time == timedelta(minutes=20)


def test_expanded_habit_chips_are_not_all_day_markers() -> None:
    """``all_day`` short-circuits the chip's time label to "All day"."""
    base = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    by_date = _items_by_date(_data([base], {"habit_1": _daily("habit_1", [NON_TODAY])}))
    assert by_date[NON_TODAY][0].all_day is False


def test_expansion_still_stamps_the_occurrence_day_and_status() -> None:
    """The C3 day stamp is what makes the chip actionable — it must survive."""
    base = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    by_date = _items_by_date(
        _data([base], {"habit_1": _daily("habit_1", [NON_TODAY], CompletionStatus.DONE)})
    )
    assert by_date[NON_TODAY][0].occurrence_data == {
        "date": NON_TODAY.isoformat(),
        "status": "done",
    }


# ---------------------------------------------------------------------------
# The rhythm — chronological order among tasks, events and habits
# ---------------------------------------------------------------------------


def test_week_column_orders_the_day_into_its_rhythm_on_a_non_today_day() -> None:
    """Morning habit above an afternoon event, evening habit below it.

    The all-day milestone stays at the top (midnight), which is the property a
    midnight-stamped habit chip used to steal.
    """
    morning = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    evening = _habit_base("habit_2", "Prep tomorrow", TimeOfDay.EVENING, 15)
    data = _data(
        [
            _all_day_marker("goal_1", "Ship the arc", NON_TODAY),
            _timed_item("event_1", "Afternoon sync", CalendarItemType.EVENT, NON_TODAY, 14),
            morning,
            evening,
        ],
        {
            "habit_1": _daily("habit_1", [NON_TODAY]),
            "habit_2": _daily("habit_2", [NON_TODAY]),
        },
    )

    html = to_xml(create_week_grid(data))
    order = [
        html.index(title)
        for title in ("Ship the arc", "Meditate", "Afternoon sync", "Prep tomorrow")
    ]
    assert order == sorted(order)


def test_an_anytime_habit_lands_at_the_stable_fallback_position() -> None:
    """A habit with no stated slot still renders, at ANYTIME's hour (09:00).

    Two of the five live habits declare no slot, so this is the ordinary case.
    """
    anytime = _habit_base("habit_3", "Pause and name", TimeOfDay.ANYTIME, 30)
    evening = _habit_base("habit_2", "Prep tomorrow", TimeOfDay.EVENING, 15)
    data = _data(
        [
            _timed_item("event_1", "Afternoon sync", CalendarItemType.EVENT, NON_TODAY, 14),
            anytime,
            evening,
        ],
        {"habit_3": _daily("habit_3", [NON_TODAY]), "habit_2": _daily("habit_2", [NON_TODAY])},
    )

    html = to_xml(create_week_grid(data))
    assert "Pause and name" in html
    order = [html.index(t) for t in ("Pause and name", "Afternoon sync", "Prep tomorrow")]
    assert order == sorted(order)


def test_habits_sharing_a_slot_render_in_a_stable_order() -> None:
    """Slots collide by design, and nothing upstream orders habits.

    MORNING and ANYTIME both resolve to 09:00 and the habit fetch issues no
    ``ORDER BY``, so a bare start-time key would let the day's rhythm reshuffle
    between renders — and month and week (separate requests) disagree with each
    other. Feeding the same two habits in opposite orders must render the same.
    """
    first = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    second = _habit_base("habit_2", "Pause and name", TimeOfDay.ANYTIME, 30)
    occurrences = {
        "habit_1": _daily("habit_1", [NON_TODAY]),
        "habit_2": _daily("habit_2", [NON_TODAY]),
    }

    forward = to_xml(create_week_grid(_data([first, second], occurrences)))
    reversed_ = to_xml(create_week_grid(_data([second, first], occurrences)))

    assert forward.index("Meditate") < forward.index("Pause and name")  # title breaks the tie
    assert forward == reversed_


def test_the_tiebreak_never_reorders_non_habit_items() -> None:
    """The secondary key is habit-only, and that is load-bearing.

    ``_task_to_calendar_item`` stamps EVERY scheduled task 09:00 and every
    due-only task midnight, so tasks tie constantly. A tiebreak applied to all
    kinds would silently re-sort them from their query order (newest first)
    into alphabetical order, with milestones wedged between due tasks.
    """
    due = _all_day_marker("goal_1", "Zebra milestone", NON_TODAY)
    newest = _timed_item("task_1", "Zebra audit", CalendarItemType.TASK, NON_TODAY, 9)
    oldest = _timed_item("task_2", "Alpha review", CalendarItemType.TASK, NON_TODAY, 9)

    html = to_xml(create_week_grid(_data([due, newest, oldest], {})))

    # Insertion order preserved, NOT alphabetised.
    assert html.index("Zebra audit") < html.index("Alpha review")


# ---------------------------------------------------------------------------
# The chip states the duration
# ---------------------------------------------------------------------------


def _expanded_chip(slot: TimeOfDay, minutes: int) -> CalendarItem:
    base = _habit_base("habit_1", "Meditate", slot, minutes)
    return _items_by_date(_data([base], {"habit_1": _daily("habit_1", [NON_TODAY])}))[NON_TODAY][0]


def test_week_chip_speaks_the_slot_word_and_the_length() -> None:
    chip = to_xml(_event_chip(_expanded_chip(TimeOfDay.MORNING, 20), large=True))
    assert "Morning \u00b7 20m" in chip
    assert "All day" not in chip


def test_an_anytime_habit_never_reads_as_a_nine_oclock_commitment() -> None:
    """MORNING and ANYTIME share 09:00, so the hour cannot name the slot.

    Printing the representative hour would tell someone who chose *anytime*
    that they committed to nine o'clock — the fabricated habit time this arc
    exists to end.
    """
    chip = to_xml(_event_chip(_expanded_chip(TimeOfDay.ANYTIME, 30), large=True))
    assert "Anytime \u00b7 30m" in chip
    assert "9:00" not in chip
    assert "AM" not in chip


def test_a_habit_that_stated_no_slot_gets_the_length_alone() -> None:
    """Null is unstated, not "Anytime" \u2014 the calendar must not invent a choice.

    Two of the five live habits declare no slot. They are PLACED at ANYTIME's
    hour so the day still orders, but naming them "Anytime" would assert a
    preference the user never expressed, and contradict the habit detail page
    and Today's ritual spine, which both read null as unstated.
    """
    chip = to_xml(_event_chip(_expanded_chip(None, 15), large=True))
    assert ">15m<" in chip
    assert "Anytime" not in chip
    assert "9:00" not in chip


def test_month_chip_carries_the_block_in_its_tooltip_without_shrinking_the_title() -> None:
    """A month day column is pinned at ~93px, so the block rides in the tooltip.

    Measured at 375px, an inline duration cut the title box from 47px to 5px —
    the habit's NAME vanished, and with it the C3 completion tick, which
    calendar.css renders inside ``.calendar-item-title::after``. The title span
    must stay the chip's only flex child besides the dot.
    """
    cell = to_xml(
        create_day_cell(
            NON_TODAY,
            [_expanded_chip(TimeOfDay.MORNING, 20)],
            is_current_month=True,
            is_weekend=False,
        )
    )
    assert 'title="Meditate \u00b7 Morning \u00b7 20m"' in cell
    assert cell.count("<span") == 2  # the dot and the title, nothing squeezing them


def test_long_blocks_read_in_hours() -> None:
    assert "Morning \u00b7 1h 30m" in to_xml(
        _event_chip(_expanded_chip(TimeOfDay.MORNING, 90), large=True)
    )
    assert "Night \u00b7 3h" in to_xml(
        _event_chip(_expanded_chip(TimeOfDay.NIGHT, 180), large=True)
    )


def test_non_habit_chips_keep_their_start_end_range_and_gain_no_duration_tag() -> None:
    """The duration is the habit vocabulary — it must not leak onto other kinds."""
    event = _timed_item("event_1", "Afternoon sync", CalendarItemType.EVENT, NON_TODAY, 14)
    chip = to_xml(_event_chip(event, large=True))
    # An end time only the range branch prints, and no "slot (dot) length".
    assert "2:00 PM \u2013 3:00 PM" in chip
    assert "\u00b7" not in chip
    assert "1h" not in chip


# ---------------------------------------------------------------------------
# The chip's modal agrees with the chip
# ---------------------------------------------------------------------------


def test_day_stamped_chip_still_opens_its_day_aware_modal() -> None:
    chip = to_xml(_event_chip(_expanded_chip(TimeOfDay.MORNING, 20)))
    assert f'hx-get="/cal/item-details/habit-habit_1?date={NON_TODAY.isoformat()}"' in chip


def test_the_modal_names_the_day_and_then_states_the_same_block() -> None:
    html = to_xml(create_item_details_modal(_expanded_chip(TimeOfDay.MORNING, 20)))
    assert "Thursday, August 6, 2026 \u00b7 Morning \u00b7 20m" in html


def test_an_unstamped_habit_modal_states_the_block_and_no_clock_range() -> None:
    """The stub's date is a placeholder, so it must not read as an appointment.

    A NIGHT habit long enough to cross midnight would otherwise print
    "Aug 03, 10:00 PM - Aug 04, 01:00 AM" — a next-day hour for a block the
    habit never pinned to a day at all.
    """
    stub = _habit_base("habit_1", "Wind down", TimeOfDay.NIGHT, 180)
    html = to_xml(create_item_details_modal(stub))
    assert "Night · 3h" in html
    assert "PM" not in html
    assert "Aug" not in html


def test_completed_expansion_still_flips_the_chip() -> None:
    """The C3 tick's rendering hook survives re-dating."""
    base = _habit_base("habit_1", "Meditate", TimeOfDay.MORNING, 20)
    chip_item = _items_by_date(
        _data([base], {"habit_1": _daily("habit_1", [NON_TODAY], CompletionStatus.DONE)})
    )[NON_TODAY][0]
    assert 'data-completed="true"' in to_xml(_event_chip(chip_item, large=True))
