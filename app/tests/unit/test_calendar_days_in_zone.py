"""Calendar sites in ``core/`` ask the zone, never the host's day (UTC arc, PR 2b).

A process at TZ=UTC with the clock at 02:00Z on 2026-09-28 is 19:00 on the 27th
in Vancouver: for a user on the default zone, "today" is the 27th, a task due
that day is not overdue, a habit done the evening before is one calendar day
ago, and a task completed now is stamped the 27th. At 18:00Z on the 27th a user
on Asia/Bangkok is already at 01:00 on the 28th.

Each test forces the host zone (CI runs UTC, where a host-day read passes by
accident only when the two days agree) and freezes the clock the zone helpers
read (``core.utils.timestamp_helpers``). Red on the host-day code: run under
``faketime '2026-09-28 02:00:00'`` with the changed file restored from main.

See: /docs/roadmap/utc-instants-arc.md § PR 2b
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.services.completion_stamp import completion_moment, status_transition_guard
from core.services.habits.habits_planning_service import HabitsPlanningService
from core.utils import timestamp_helpers
from core.utils.zone_context import current_zone, today_in_current_zone, zone_scope
from tests.helpers.forced_zone import forced_zone

VANCOUVER = ZoneInfo("America/Vancouver")
BANGKOK = ZoneInfo("Asia/Bangkok")

EVENING_IN_VANCOUVER = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)  # 19:00 on the 27th
EVENING_IN_UTC = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)  # 01:00 on the 28th in Bangkok


def _freeze(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is None:
                return moment.astimezone().replace(tzinfo=None)
            return moment.astimezone(tz)

    monkeypatch.setattr(timestamp_helpers, "datetime", _Frozen)


@pytest.fixture
def utc_host(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A UTC process (CI, the cloud, the pinned app) with users on the default zone."""
    monkeypatch.delenv("SKUEL_TIMEZONE", raising=False)
    with forced_zone("UTC"):
        yield


def _task(due: date) -> Task:
    return Task(
        uid="task_due",
        title="Due",
        user_uid="user_zone",
        entity_type=EntityType.TASK,
        status=EntityStatus.ACTIVE,
        due_date=due,
    )


def _daily_habit(last_completed: datetime) -> Habit:
    return Habit(
        uid="habit_daily",
        title="Daily",
        user_uid="user_zone",
        entity_type=EntityType.HABIT,
        status=EntityStatus.ACTIVE,
        target_days_per_week=7,
        last_completed=last_completed,
    )


@pytest.mark.usefixtures("utc_host")
class TestADefaultUserInTheVancouverEvening:
    """02:00Z on the 28th — the UTC day has turned; Vancouver's has not."""

    @pytest.fixture(autouse=True)
    def _clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, EVENING_IN_VANCOUVER)

    def test_today_is_the_vancouver_day(self) -> None:
        assert current_zone() == VANCOUVER
        assert today_in_current_zone() == date(2026, 9, 27)

    def test_a_task_due_that_day_is_not_overdue(self) -> None:
        task = _task(date(2026, 9, 27))
        assert not task.is_overdue()
        assert task.get_days_remaining() == 0

    def test_a_habit_done_yesterday_evening_is_one_calendar_day_ago(self) -> None:
        # 22:00 on the 26th in Vancouver, stamped naive on the UTC host clock:
        # 21 hours ago, but on the previous calendar day — so it is due today.
        last = datetime(2026, 9, 27, 5, 0)
        habit = _daily_habit(last)
        assert HabitsPlanningService._days_since_last_completion(habit) == 1
        assert habit.should_do_today()
        completion = HabitCompletion(
            uid="hc.user_zone.habit_daily.1",
            habit_uid="habit_daily",
            user_uid="user_zone",
            completed_at=last,
            created_at=last,
            updated_at=last,
        )
        assert completion.days_since_completion() == 1

    def test_a_task_completed_now_is_stamped_the_vancouver_day(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"}, zone=VANCOUVER)
        assert guard.is_ok
        _completed, patch = guard.value.patch_if_prior_not_in
        assert patch == {"completion_date": date(2026, 9, 27)}

    def test_a_completion_date_widens_to_its_first_instant_in_the_zone(self) -> None:
        # Midnight on the 27th in Vancouver is 07:00Z — on a UTC host clock, 07:00.
        assert completion_moment(date(2026, 9, 27), VANCOUVER) == datetime(2026, 9, 27, 7, 0)


@pytest.mark.usefixtures("utc_host")
class TestABangkokUserInTheUtcEvening:
    """18:00Z on the 27th — Vancouver's afternoon, already the 28th in Bangkok."""

    @pytest.fixture(autouse=True)
    def _clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _freeze(monkeypatch, EVENING_IN_UTC)

    def test_today_is_the_next_day(self) -> None:
        assert today_in_current_zone() == date(2026, 9, 27)  # the default, Vancouver
        with zone_scope(BANGKOK):
            assert today_in_current_zone() == date(2026, 9, 28)

    def test_a_task_due_on_the_27th_is_overdue_in_bangkok_only(self) -> None:
        task = _task(date(2026, 9, 27))
        assert not task.is_overdue()
        with zone_scope(BANGKOK):
            assert task.is_overdue()

    def test_a_task_completed_now_is_stamped_the_bangkok_day(self) -> None:
        guard = status_transition_guard(EntityType.TASK, {"status": "completed"}, zone=BANGKOK)
        assert guard.is_ok
        _completed, patch = guard.value.patch_if_prior_not_in
        assert patch == {"completion_date": date(2026, 9, 28)}
