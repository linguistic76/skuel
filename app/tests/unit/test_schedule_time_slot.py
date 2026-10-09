"""
Unit Tests — the slot schedule-aware recommendations are scored for
====================================================================

``ScheduleIntelligenceMixin._get_current_time_slot`` answers with the user's preferred
slot, else the clock's. ``TimeOfDay.ANYTIME`` is the default preference and means "no
preference", so it falls through to the clock — through ``TimeOfDay.from_hour``, the one
hour↔slot mapping. The scorer then has a verdict for every slot ``TimeOfDay`` has.
"""

from datetime import date, datetime, time

import pytest
import time_machine

from core.models.enums.scheduling_enums import TimeOfDay
from core.services.user.intelligence.schedule_intelligence import ScheduleIntelligenceMixin
from core.services.user.unified_user_context import RichUserContext
from core.utils.zone_context import current_zone

DAY = date(2026, 10, 8)


class _Schedule(ScheduleIntelligenceMixin):
    """The schedule mixin over a context — it reads nothing else."""

    def __init__(self, context: RichUserContext) -> None:
        self.context = context


def _at(hour: int) -> time_machine.travel:
    """Freeze the process clock at ``hour`` o'clock in the current zone."""
    instant = datetime.combine(DAY, time(hour=hour), tzinfo=current_zone())
    return time_machine.travel(instant.timestamp(), tick=False)


def _schedule(preferred: TimeOfDay = TimeOfDay.ANYTIME) -> _Schedule:
    context = RichUserContext(user_uid="user_test")
    context.preferred_time = preferred
    return _Schedule(context)


class TestTheSlot:
    def test_the_default_preference_falls_through_to_the_clock(self) -> None:
        with _at(9):
            assert _schedule()._get_current_time_slot() is TimeOfDay.MORNING

    def test_a_stated_preference_wins_over_the_clock(self) -> None:
        with _at(9):
            assert _schedule(TimeOfDay.EVENING)._get_current_time_slot() is TimeOfDay.EVENING

    @pytest.mark.parametrize(
        ("hour", "slot"),
        [
            (6, TimeOfDay.EARLY_MORNING),
            (14, TimeOfDay.AFTERNOON),
            (22, TimeOfDay.NIGHT),
            (2, TimeOfDay.LATE_NIGHT),
        ],
    )
    def test_the_clock_maps_through_the_one_hour_slot_mapping(
        self, hour: int, slot: TimeOfDay
    ) -> None:
        with _at(hour):
            assert _schedule()._get_current_time_slot() is slot


def _fit(entity_type: str, slot: TimeOfDay) -> float:
    score = _schedule()._calculate_schedule_score(
        entity_type=entity_type,
        priority=0.5,
        energy_required="medium",
        current_energy="medium",
        time_slot=slot,
        respect_energy=True,
    )
    return score["schedule_fit"]


class TestEverySlotHasAVerdict:
    @pytest.mark.parametrize(
        ("entity_type", "slot", "fit"),
        [
            ("task", TimeOfDay.MORNING, 0.9),
            ("task", TimeOfDay.EARLY_MORNING, 0.9),
            ("task", TimeOfDay.AFTERNOON, 0.9),
            ("task", TimeOfDay.EVENING, 0.7),
            ("task", TimeOfDay.LATE_NIGHT, 0.5),
            ("knowledge", TimeOfDay.EARLY_MORNING, 0.95),
            ("knowledge", TimeOfDay.MORNING, 0.95),
            ("knowledge", TimeOfDay.AFTERNOON, 0.7),
            ("knowledge", TimeOfDay.LATE_NIGHT, 0.5),
            ("habit", TimeOfDay.LATE_NIGHT, 0.85),
            ("goal", TimeOfDay.MORNING, 0.75),
            ("goal", TimeOfDay.LATE_NIGHT, 0.5),
        ],
    )
    def test_fit(self, entity_type: str, slot: TimeOfDay, fit: float) -> None:
        assert _fit(entity_type, slot) == fit


class TestTheRecommendationCarriesTheSlot:
    @pytest.mark.asyncio
    async def test_a_task_at_nine_with_no_preference_fits_the_morning(self) -> None:
        schedule = _schedule()
        schedule.context.today_task_uids = ["task.test.today"]

        with _at(9):
            recommendations = await schedule.get_schedule_aware_recommendations()

        (task,) = [r for r in recommendations if r.uid == "task.test.today"]
        assert task.schedule_fit_score == 0.9
        assert task.suggested_time_slot == TimeOfDay.MORNING.value
