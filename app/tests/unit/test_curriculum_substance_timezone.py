"""
Substance maths must survive the timestamps the graph actually stores.
=====================================================================

``increment_substance`` writes every substance timestamp as
``SET ps.{field} = datetime($timestamp)``, so Neo4j stores a ZONED datetime and
the driver hands it back tz-aware. The decay maths compared those against
``datetime.now()`` — naive — and Python refuses to subtract the two.

The failure mode is why this went unnoticed: ``substance_score()`` raised
``TypeError`` rather than returning a wrong number, and its only caller wrapped
the whole calculation in an exception handler that returned a generic failure.
Nothing ever displayed a suspicious value.

An entity is affected exactly when its substance has been incremented at least
once — the paying case. These tests use aware timestamps because that is what
production reads back; the naive cases guard the in-memory path (a freshly
constructed entity) so the normalisation cannot regress in the other direction.
"""

from datetime import UTC, datetime, timedelta

import pytest

from core.models.pathways.path_step import PathStep


def _step(**kwargs) -> PathStep:
    return PathStep(uid="ps.substance.probe", title="Probe", **kwargs)


class TestSubstanceScoreAcceptsZonedTimestamps:
    """The decay weight is read from a timestamp that came back from Neo4j."""

    @pytest.mark.parametrize(
        "field",
        [
            "last_applied_date",
            "last_practiced_date",
            "last_built_into_habit_date",
            "last_reflected_date",
            "last_choice_informed_date",
        ],
    )
    def test_each_substance_timestamp_may_be_aware(self, field):
        """All five decay inputs share the writer, so all five share the bug."""
        counter = {
            "last_applied_date": "times_applied_in_tasks",
            "last_practiced_date": "times_practiced_in_events",
            "last_built_into_habit_date": "times_built_into_habits",
            "last_reflected_date": "times_reflected_in_entries",
            "last_choice_informed_date": "choices_informed_count",
        }[field]

        step = _step(**{field: datetime.now(UTC) - timedelta(days=10), counter: 2})

        score = step.substance_score()  # pre-fix: TypeError
        assert score > 0.0, "a recent, twice-substantiated step must score above zero"

    def test_aware_and_naive_agree(self):
        """Normalisation must not shift the answer — same instant, same score."""
        ten_days = timedelta(days=10)
        aware = _step(last_applied_date=datetime.now(UTC) - ten_days, times_applied_in_tasks=2)
        naive = _step(last_applied_date=datetime.now() - ten_days, times_applied_in_tasks=2)

        assert aware.substance_score() == pytest.approx(naive.substance_score(), abs=1e-9)

    def test_decay_still_bites(self):
        """Guard the lazy fix: coercing every aware value to "now" would erase decay."""
        recent = _step(last_applied_date=datetime.now(UTC) - timedelta(days=1))
        stale = _step(last_applied_date=datetime.now(UTC) - timedelta(days=365))
        object.__setattr__(recent, "times_applied_in_tasks", 3)
        object.__setattr__(stale, "times_applied_in_tasks", 3)

        assert recent.substance_score() > stale.substance_score()


class TestDaysUntilReviewAcceptsZonedTimestamps:
    """The second arithmetic site, reached by the metric's decay-warning loop."""

    def test_mixed_awareness_across_fields(self):
        """``max()`` over a mixed list raises before any subtraction happens.

        Seeded past two guards that would otherwise return early and never
        reach the arithmetic: ``_was_once_substantiated`` (needs habits, or
        >2 tasks, or >1 event) and the ``< 0.5`` short circuit. 3 habits + 5
        events one day old scores ~0.53.
        """
        one_day = timedelta(days=1)
        step = _step(
            last_built_into_habit_date=datetime.now(UTC) - one_day,  # aware, from the graph
            last_practiced_date=datetime.now() - one_day,  # naive, in-memory
            times_built_into_habits=3,
            times_practiced_in_events=5,
        )
        assert step.substance_score() >= 0.5, "seed too weak — the 0-return short circuit fires"

        days = step.days_until_review_needed()  # pre-fix: TypeError on the comparison
        assert isinstance(days, int)
        # Threshold is ~21 days; most recent use was 1 day ago.
        assert 18 <= days <= 20, f"expected ~19 days of headroom, got {days}"

    def test_never_substantiated_returns_none(self):
        """None, not 0 — the analytics caller must not read it as "review today"."""
        assert _step().days_until_review_needed() is None
