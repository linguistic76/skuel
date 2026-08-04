"""
Tests for the HabitCompletion Domain Model
===========================================

Direct unit tests for the pure business-logic methods on the HabitCompletion
frozen dataclass (core/models/habit/completion.py).

Testing-gap roadmap item 4: the streak/completion math had no direct tests —
this model's methods were entirely uncovered. Existing coverage in
tests/unit/test_habits_completion_service.py exercises the service layer with
mocked backends; these tests are mock-free and target the model itself.

Notes on actual-vs-documented behavior (asserted as-is, production untouched):
- is_streak_eligible's docstring claims a "within 36 hours" recency window,
  but the implementation gates on days_since_completion() > 1 — pure
  calendar-day arithmetic, so a completion at 00:01 yesterday stays eligible
  for nearly 48 hours.
- duration_actual == 0 is treated as absent (falsy) by was_extended_session,
  was_shortened_session, and completion_score.
"""

from datetime import date, datetime, timedelta

import pytest

from core.models.enums.scheduling_enums import TimeOfDay
from core.models.habit.completion import HabitCompletion

# Fixed reference moment for the pure (wall-clock-independent) methods.
FIXED_COMPLETED_AT = datetime(2026, 7, 10, 9, 30, 0)
FIXED_CREATED_AT = datetime(2026, 7, 10, 9, 31, 0)


def make_completion(
    completed_at: datetime = FIXED_COMPLETED_AT,
    notes: str | None = None,
    quality: int | None = None,
    duration_actual: int | None = None,
) -> HabitCompletion:
    """Build a HabitCompletion with sensible defaults (fixture style copied
    from the sample_completion fixture in tests/unit/test_habits_completion_service.py)."""
    return HabitCompletion(
        uid="hc.user.mike.habit.test.1.1729000000",
        habit_uid="habit.test.1",
        completed_at=completed_at,
        notes=notes,
        quality=quality,
        duration_actual=duration_actual,
        created_at=FIXED_CREATED_AT,
        updated_at=FIXED_CREATED_AT,
    )


class TestPostInitValidation:
    """__post_init__ bounds checking for quality and duration_actual."""

    def test_quality_zero_raises(self):
        with pytest.raises(ValueError, match="Quality must be between 1 and 5"):
            make_completion(quality=0)

    def test_quality_six_raises(self):
        with pytest.raises(ValueError, match="Quality must be between 1 and 5"):
            make_completion(quality=6)

    def test_quality_lower_bound_passes(self):
        assert make_completion(quality=1).quality == 1

    def test_quality_upper_bound_passes(self):
        assert make_completion(quality=5).quality == 5

    def test_quality_none_passes(self):
        assert make_completion(quality=None).quality is None

    def test_negative_duration_raises(self):
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            make_completion(duration_actual=-1)

    def test_zero_duration_passes_validation(self):
        assert make_completion(duration_actual=0).duration_actual == 0


class TestQualityPredicates:
    """is_high_quality, is_excellent_quality, and satisfaction_level buckets."""

    def test_is_high_quality_at_four(self):
        assert make_completion(quality=4).is_high_quality() is True

    def test_is_high_quality_at_five(self):
        assert make_completion(quality=5).is_high_quality() is True

    def test_is_high_quality_below_threshold(self):
        assert make_completion(quality=3).is_high_quality() is False

    def test_is_high_quality_none(self):
        assert make_completion(quality=None).is_high_quality() is False

    def test_is_excellent_quality_five_only(self):
        assert make_completion(quality=5).is_excellent_quality() is True
        assert make_completion(quality=4).is_excellent_quality() is False
        assert make_completion(quality=None).is_excellent_quality() is False

    def test_satisfaction_level_buckets(self):
        assert make_completion(quality=None).satisfaction_level() == "neutral"
        assert make_completion(quality=5).satisfaction_level() == "excellent"
        assert make_completion(quality=4).satisfaction_level() == "good"
        assert make_completion(quality=3).satisfaction_level() == "satisfactory"
        assert make_completion(quality=2).satisfaction_level() == "below_average"
        # The "poor" branch (quality < 2) is only reachable at quality == 1
        # because __post_init__ rejects anything below 1.
        assert make_completion(quality=1).satisfaction_level() == "poor"


class TestMeaningfulNotes:
    """has_meaningful_notes: length > 10 AND more than 2 words."""

    def test_none_notes(self):
        assert make_completion(notes=None).has_meaningful_notes() is False

    def test_empty_notes(self):
        assert make_completion(notes="").has_meaningful_notes() is False

    def test_whitespace_only_notes(self):
        assert make_completion(notes="   ").has_meaningful_notes() is False

    def test_short_notes(self):
        assert make_completion(notes="hi").has_meaningful_notes() is False

    def test_long_but_two_words_fails_word_count_gate(self):
        # 11 characters after strip, but only 2 words -> word-count gate rejects.
        notes = "abcdefgh ij"
        assert len(notes) > 10
        assert len(notes.split()) == 2
        assert make_completion(notes=notes).has_meaningful_notes() is False

    def test_long_multi_word_notes_pass(self):
        assert make_completion(notes="Felt great after the session").has_meaningful_notes() is True


class TestSessionDuration:
    """was_extended_session and was_shortened_session against a target."""

    def test_extended_when_over_target(self):
        assert make_completion(duration_actual=35).was_extended_session(30) is True

    def test_not_extended_at_exact_target(self):
        assert make_completion(duration_actual=30).was_extended_session(30) is False

    def test_extended_none_inputs(self):
        assert make_completion(duration_actual=None).was_extended_session(30) is False
        assert make_completion(duration_actual=35).was_extended_session(None) is False

    def test_shortened_below_75_percent(self):
        # 75% of 40 is 30 -> 29 is shortened.
        assert make_completion(duration_actual=29).was_shortened_session(40) is True

    def test_not_shortened_at_exactly_75_percent(self):
        # Strict less-than: exactly 75% of target is NOT shortened.
        assert make_completion(duration_actual=30).was_shortened_session(40) is False

    def test_shortened_none_inputs(self):
        assert make_completion(duration_actual=None).was_shortened_session(40) is False
        assert make_completion(duration_actual=20).was_shortened_session(None) is False

    def test_zero_duration_treated_as_absent(self):
        # Actual behavior: duration_actual == 0 is falsy, so both predicates
        # return False even though 0 < 75% of any positive target.
        assert make_completion(duration_actual=0).was_shortened_session(40) is False
        assert make_completion(duration_actual=0).was_extended_session(40) is False


class TestCompletionScore:
    """completion_score weight matrix: base 0.5 + quality 0.3 + duration 0.15 + notes 0.05."""

    def test_base_score_no_optionals(self):
        assert make_completion().completion_score() == pytest.approx(0.5)

    def test_quality_five_alone(self):
        # 0.5 + ((5-1)/4) * 0.3 = 0.8
        assert make_completion(quality=5).completion_score() == pytest.approx(0.8)

    def test_quality_one_alone_adds_nothing(self):
        # (1-1)/4 == 0, so quality 1 contributes zero.
        assert make_completion(quality=1).completion_score() == pytest.approx(0.5)

    def test_quality_three_alone(self):
        # 0.5 + ((3-1)/4) * 0.3 = 0.65
        assert make_completion(quality=3).completion_score() == pytest.approx(0.65)

    def test_duration_exactly_at_target(self):
        # ratio 1.0 -> full 0.15 duration component.
        score = make_completion(duration_actual=30).completion_score(target_duration=30)
        assert score == pytest.approx(0.65)

    def test_duration_over_target_capped(self):
        # ratio min(60/30, 1.5) = 1.5, then min(1.5, 1.0) = 1.0 -> same 0.15 as at-target.
        score = make_completion(duration_actual=60).completion_score(target_duration=30)
        assert score == pytest.approx(0.65)

    def test_duration_half_of_target(self):
        # ratio 0.5 -> 0.5 * 0.15 = 0.075.
        score = make_completion(duration_actual=15).completion_score(target_duration=30)
        assert score == pytest.approx(0.575)

    def test_duration_ignored_without_target(self):
        assert make_completion(duration_actual=30).completion_score() == pytest.approx(0.5)

    def test_meaningful_notes_alone(self):
        score = make_completion(notes="Felt great after the session").completion_score()
        assert score == pytest.approx(0.55)

    def test_all_components_reach_exactly_one(self):
        # 0.5 + 0.3 (quality 5) + 0.15 (duration >= target) + 0.05 (notes) = 1.0,
        # so the min(score, 1.0) clamp is hit exactly at the maximum.
        completion = make_completion(
            quality=5, duration_actual=35, notes="Felt great after the session"
        )
        assert completion.completion_score(target_duration=30) == pytest.approx(1.0)


class TestDateMethods:
    """was_completed_on and completion_time_of_day (pure, fixed dates)."""

    def test_was_completed_on_matching_date(self):
        assert make_completion().was_completed_on(date(2026, 7, 10)) is True

    def test_was_completed_on_other_date(self):
        assert make_completion().was_completed_on(date(2026, 7, 11)) is False

    def test_time_of_day_boundaries(self):
        # The TimeOfDay slots, at every boundary: [0,5) late_night, [5,7) early_morning,
        # [7,12) morning, [12,17) afternoon, [17,21) evening, [21,24) night.
        expected_by_hour = {
            0: TimeOfDay.LATE_NIGHT,
            4: TimeOfDay.LATE_NIGHT,
            5: TimeOfDay.EARLY_MORNING,
            6: TimeOfDay.EARLY_MORNING,
            7: TimeOfDay.MORNING,
            11: TimeOfDay.MORNING,
            12: TimeOfDay.AFTERNOON,
            16: TimeOfDay.AFTERNOON,
            17: TimeOfDay.EVENING,
            20: TimeOfDay.EVENING,
            21: TimeOfDay.NIGHT,
            23: TimeOfDay.NIGHT,
        }
        for hour, expected in expected_by_hour.items():
            completion = make_completion(completed_at=datetime(2026, 7, 10, hour, 0, 0))
            got = completion.completion_time_of_day()
            # `==` alone passes for a bare str: TimeOfDay is a StrEnum.
            assert got is expected, f"hour {hour}: got {got!r}"

    def test_time_of_day_covers_every_hour_with_a_real_slot(self):
        """No hour falls through to a stringly-typed default."""
        for hour in range(24):
            completion = make_completion(completed_at=datetime(2026, 7, 10, hour, 0, 0))
            assert isinstance(completion.completion_time_of_day(), TimeOfDay)


FROZEN_NOW = datetime(2026, 7, 15, 10, 30, 0)  # a Wednesday, mid-week and mid-day


class TestTimeDependentMethods:
    """Methods that compare against the wall clock — clock frozen at FROZEN_NOW.

    The model calls datetime.now()/date.today() internally (no injection
    point), so the module-level names in core.models.habit.completion are
    monkeypatched with frozen subclasses and every completion is built
    relative to FROZEN_NOW. Without this, a test computing "3 days ago" from
    one now() call and the model calling now() again could straddle midnight
    and flake (codex review finding on PR #704).
    """

    @pytest.fixture(autouse=True)
    def frozen_clock(self, monkeypatch):
        import core.models.habit.completion as completion_module

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ARG003 -- mirrors datetime.now signature
                return FROZEN_NOW

        class _FrozenDate(date):
            @classmethod
            def today(cls):
                return FROZEN_NOW.date()

        monkeypatch.setattr(completion_module, "datetime", _FrozenDatetime)
        monkeypatch.setattr(completion_module, "date", _FrozenDate)

    def test_was_completed_today(self):
        assert make_completion(completed_at=FROZEN_NOW).was_completed_today() is True

    def test_was_not_completed_today(self):
        yesterday = FROZEN_NOW - timedelta(days=1)
        assert make_completion(completed_at=yesterday).was_completed_today() is False

    def test_days_since_completion_now(self):
        assert make_completion(completed_at=FROZEN_NOW).days_since_completion() == 0

    def test_days_since_completion_three_days(self):
        three_days_ago = FROZEN_NOW - timedelta(days=3)
        assert make_completion(completed_at=three_days_ago).days_since_completion() == 3

    def test_streak_eligible_valid_completion_no_previous(self):
        assert make_completion(completed_at=FROZEN_NOW, quality=3).is_streak_eligible() is True

    def test_streak_eligible_quality_none_passes_gate(self):
        assert make_completion(completed_at=FROZEN_NOW, quality=None).is_streak_eligible() is True

    def test_streak_ineligible_low_quality(self):
        # Quality gate: quality < 2 disqualifies.
        assert make_completion(completed_at=FROZEN_NOW, quality=1).is_streak_eligible() is False

    def test_streak_ineligible_too_old(self):
        # Recency gate. Docstring says "within 36 hours" but the implementation
        # is calendar-day based: days_since_completion() > 1 disqualifies.
        three_days_ago = FROZEN_NOW - timedelta(days=3)
        assert make_completion(completed_at=three_days_ago).is_streak_eligible() is False

    def test_streak_eligible_yesterday_passes_recency(self):
        # days_since == 1 is still eligible (calendar-day gate, not 36 wall-clock hours).
        yesterday = FROZEN_NOW - timedelta(days=1)
        assert make_completion(completed_at=yesterday).is_streak_eligible() is True

    def test_streak_ineligible_duplicate_day(self):
        current = make_completion(completed_at=FROZEN_NOW, quality=4)
        previous = make_completion(completed_at=FROZEN_NOW - timedelta(hours=1), quality=4)
        assert current.is_streak_eligible(previous_completion=previous) is False

    def test_streak_eligible_consecutive_days(self):
        current = make_completion(completed_at=FROZEN_NOW, quality=4)
        previous = make_completion(completed_at=FROZEN_NOW - timedelta(days=1), quality=4)
        assert current.is_streak_eligible(previous_completion=previous) is True

    def test_consistency_daily_always_counts(self):
        # Daily habits accept any completion regardless of age.
        old = make_completion(completed_at=FROZEN_NOW - timedelta(days=30))
        assert old.contributes_to_consistency("daily") is True

    def test_consistency_weekly_within_current_week(self):
        today_completion = make_completion(completed_at=FROZEN_NOW)
        assert today_completion.contributes_to_consistency("weekly") is True

    def test_consistency_frequency_is_case_insensitive(self):
        today_completion = make_completion(completed_at=FROZEN_NOW)
        assert today_completion.contributes_to_consistency("WEEKLY") is True

    def test_consistency_weekly_outside_current_week(self):
        # FROZEN_NOW is Wednesday the 15th; week starts Monday the 13th.
        # 7 days earlier (the 8th) is before the week start.
        last_week = make_completion(completed_at=FROZEN_NOW - timedelta(days=7))
        assert last_week.contributes_to_consistency("weekly") is False

    def test_consistency_unknown_frequency_defaults_true(self):
        completion = make_completion(completed_at=FROZEN_NOW - timedelta(days=30))
        assert completion.contributes_to_consistency("biweekly") is True


class TestIsBetterThan:
    """is_better_than: strict completion_score comparison."""

    def test_higher_score_wins(self):
        better = make_completion(quality=5)
        worse = make_completion(quality=3)
        assert better.is_better_than(worse) is True
        assert worse.is_better_than(better) is False

    def test_equal_scores_are_not_better(self):
        first = make_completion(quality=4)
        second = make_completion(quality=4)
        assert first.is_better_than(second) is False
        assert second.is_better_than(first) is False

    def test_target_duration_influences_comparison(self):
        # With a target, the longer session earns the duration component.
        longer = make_completion(quality=3, duration_actual=30)
        shorter = make_completion(quality=3, duration_actual=15)
        assert longer.is_better_than(shorter, target_duration=30) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
