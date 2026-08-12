"""
Rounding boundaries in Life Path alignment: display rounds, decisions do not.
============================================================================

Both defects guarded here are the same shape — **a threshold tested against a
value that had already been rounded for display** — and both were raised by Codex
on #1034. Neither is reachable from the integration suite's fixtures, because
producing them needs a score with more than two decimals (a step teaching several
Kus) or a channel worth under 0.5% of a path's total. They live here, as unit
tests over the two pure methods, where the boundary can be hit exactly.

The rule they pin is the one ``user_substance.py`` already states for the scorer
and this service re-broke one layer up: **rounding belongs at the presentation
edge.** A value that is rounded and then compared has silently moved.

1. ``_analyze_knowledge_substance`` emitted ``round(score, 2)`` and then filtered
   gaps on that. A step at 0.4967 rounds to 0.50, so ``< 0.5`` excluded it — while
   the bands, which read the raw score, still called it under-substantiated. The
   step vanished from ``gaps`` and from the gap-driven recommendations.

2. ``_analyze_domain_contributions`` rounded its proportions, and
   ``_generate_recommendations`` read ``<= 0.0`` off them as "never used". A
   channel contributing under 0.5% of the total rounds to 0.0, so a learner was
   told to create a task they had already created.
"""

import pytest

from core.ports.query_types import LifePathStepRow, StepSubstance
from core.services.analytics.analytics_life_path_service import (
    GAP_THRESHOLD,
    AnalyticsLifePathService,
)
from core.services.knowledge.user_substance import USER_SUBSTANCE_CHANNELS

# 0.4967 — under the 0.5 review threshold, rounds to 0.50.
JUST_UNDER_THRESHOLD = (0.50 + 0.50 + 0.49) / 3


def _service() -> AnalyticsLifePathService:
    """The service with no collaborators — both methods under test are pure."""
    return AnalyticsLifePathService(ku_service=None)


def _step(uid: str) -> LifePathStepRow:
    return {"ps_uid": uid, "title": uid, "sequence": 0}


def _substance(score: float, breakdown: dict[str, float] | None = None) -> StepSubstance:
    zeroed = {channel.name: 0.0 for channel in USER_SUBSTANCE_CHANNELS}
    return StepSubstance(score=score, breakdown={**zeroed, **(breakdown or {})})


class TestGapThresholdUsesTheRawScore:
    """A step under the review threshold must be reported, however it displays."""

    def test_the_fixture_actually_straddles_the_boundary(self):
        """Guard the guard: if this stops being true the test below proves nothing."""
        assert JUST_UNDER_THRESHOLD < GAP_THRESHOLD, "fixture is not under the threshold"
        assert round(JUST_UNDER_THRESHOLD, 2) == pytest.approx(GAP_THRESHOLD), (
            "fixture no longer rounds ONTO the threshold, so it cannot detect the defect"
        )

    def test_a_step_that_rounds_onto_the_threshold_is_still_a_gap(self):
        """0.4967 displays as 0.5 and is under 0.5. It is a gap."""
        steps = [_step("ps_borderline")]
        substance = {"ps_borderline": _substance(JUST_UNDER_THRESHOLD)}

        analysis = _service()._analyze_knowledge_substance(steps, substance)

        assert [gap["ku_uid"] for gap in analysis["gaps"]] == ["ps_borderline"], (
            "the step was dropped from gaps because round(0.4967, 2) == 0.50 is "
            "not < 0.50 — the threshold was tested against the DISPLAY value"
        )
        assert analysis["applied_count"] == 1, (
            "the bands read the raw score, so they and the gap filter must agree "
            "that this step is under-substantiated"
        )

    def test_the_emitted_value_is_still_rounded_for_display(self):
        """Fixing the comparison must not push raw floats into the payload."""
        steps = [_step("ps_borderline")]
        substance = {"ps_borderline": _substance(JUST_UNDER_THRESHOLD)}

        gaps = _service()._analyze_knowledge_substance(steps, substance)["gaps"]

        assert gaps[0]["substance"] == pytest.approx(0.5), (
            "0.4966666… reached the payload — rounding was removed rather than "
            "moved off the comparison"
        )

    def test_gaps_rank_on_the_raw_score_not_the_rounded_one(self):
        """Two steps that display identically still order by what they are."""
        steps = [_step("ps_higher"), _step("ps_lower")]
        substance = {
            "ps_higher": _substance(0.494),  # both display as 0.49
            "ps_lower": _substance(0.486),
        }

        gaps = _service()._analyze_knowledge_substance(steps, substance)["gaps"]

        assert [gap["ku_uid"] for gap in gaps] == ["ps_lower", "ps_higher"], (
            "ranking on the rounded value makes these two ties, so the 10-gap cap "
            "would keep an arbitrary one rather than the one that most needs work"
        )

    def test_a_step_at_the_threshold_exactly_is_not_a_gap(self):
        """The boundary is strict — 0.5 is the review threshold, not below it."""
        steps = [_step("ps_exactly_half")]
        substance = {"ps_exactly_half": _substance(GAP_THRESHOLD)}

        analysis = _service()._analyze_knowledge_substance(steps, substance)

        assert analysis["gaps"] == []


class TestChannelPromptsUseTheRawTotals:
    """Never-used-this-channel is a fact about the totals, not the percentages."""

    # A 34-step path, every step habit-substantiated, ONE task anywhere on it:
    # 0.05 / (34 * 0.30 + 0.05) = 0.0049, which rounds to 0.0. Below 34 steps the
    # share rounds to 0.01 and the defect is not reachable — the "guard the guard"
    # test below is what caught a 12-step first draft that proved nothing.
    _STEPS_NEEDED_TO_ROUND_TO_ZERO = 34

    @classmethod
    def _path_with_a_tiny_task_share(
        cls,
    ) -> tuple[list[LifePathStepRow], dict[str, StepSubstance]]:
        """One task's worth of substance against a large habit total: ~0.49%."""
        count = cls._STEPS_NEEDED_TO_ROUND_TO_ZERO
        steps = [_step(f"ps_{i}") for i in range(count)]
        substance = {"ps_0": _substance(0.30, {"habits": 0.30, "tasks": 0.05})}
        for i in range(1, count):
            substance[f"ps_{i}"] = _substance(0.30, {"habits": 0.30})
        return steps, substance

    def test_the_fixture_actually_rounds_a_used_channel_to_zero(self):
        """Guard the guard."""
        steps, substance = self._path_with_a_tiny_task_share()
        totals = AnalyticsLifePathService._sum_channel_substance(steps, substance)
        contributions = AnalyticsLifePathService._analyze_domain_contributions(totals)

        assert totals["tasks"] > 0.0, "fixture has no task substance at all"
        assert contributions["tasks"] == 0.0, (
            "fixture no longer rounds the task share to 0.0, so it cannot detect the defect"
        )

    def test_a_channel_used_but_rounding_to_zero_is_not_prompted(self):
        """The learner created a task; do not tell them to create a task."""
        steps, substance = self._path_with_a_tiny_task_share()
        totals = AnalyticsLifePathService._sum_channel_substance(steps, substance)

        recommendations = AnalyticsLifePathService._generate_recommendations(
            {"avg_substance": 0.30}, totals, []
        )

        tasks_prompt = next(c for c in USER_SUBSTANCE_CHANNELS if c.name == "tasks").recommendation
        assert tasks_prompt.format(title="your Life Path") not in recommendations, (
            "the prompt fired off the ROUNDED share (0.0) rather than the raw "
            "total — it tells a learner to do what they have already done"
        )

    def test_a_channel_genuinely_unused_is_still_prompted(self):
        """The complement — the fix must not silence the real prompts."""
        steps, substance = self._path_with_a_tiny_task_share()
        totals = AnalyticsLifePathService._sum_channel_substance(steps, substance)

        recommendations = AnalyticsLifePathService._generate_recommendations(
            {"avg_substance": 0.30}, totals, []
        )

        for name in ("events", "entries", "choices", "principles"):
            prompt = next(c for c in USER_SUBSTANCE_CHANNELS if c.name == name).recommendation
            assert prompt.format(title="your Life Path") in recommendations, (
                f"the {name} channel is genuinely at 0.0 and must still be prompted"
            )

    def test_displayed_contributions_stay_rounded(self):
        """The payload the dashboard renders is still two decimals."""
        steps, substance = self._path_with_a_tiny_task_share()
        totals = AnalyticsLifePathService._sum_channel_substance(steps, substance)

        contributions = AnalyticsLifePathService._analyze_domain_contributions(totals)

        assert all(value == round(value, 2) for value in contributions.values()), (
            "raw proportions reached the payload — rounding was removed rather "
            "than kept on the display path"
        )

    def test_a_learner_with_no_activity_gets_six_zeroes_not_a_division_error(self):
        """The all-zero path still returns all six keys."""
        steps = [_step("ps_untouched")]
        substance = {"ps_untouched": _substance(0.0)}

        totals = AnalyticsLifePathService._sum_channel_substance(steps, substance)
        contributions = AnalyticsLifePathService._analyze_domain_contributions(totals)

        assert set(contributions) == {channel.name for channel in USER_SUBSTANCE_CHANNELS}
        assert all(value == 0.0 for value in contributions.values())
