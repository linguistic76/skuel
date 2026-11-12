"""
How the choices a principle guided turned out.

``PrincipleChoiceOutcomes`` is the one reading of a principle's guided choices: how many
it informs, how many of those carry an outcome rating, and what the ratings add up to.
Every derived figure is taken over the rated choices only. A choice whose outcome has
not been rated has no satisfaction, which is different from a low one, so it counts
toward ``choices_guided`` and nowhere else. With nothing rated, each derived figure is
``None``.

Two readers build it from the same Cypher tally
(``adapters/persistence/neo4j/query/cypher/choice_fragments.build_choice_outcome_tally``):
the principle's own read (``PrinciplesBackend.get_principle_choice_outcomes``: the
principle page's outcome section and ``GET /api/principles/choice-effectiveness``) and
the rich user context's statement over every owned principle
(``principle_guided_choice_counts`` / ``principle_choice_satisfaction_avg``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.constants import PrincipleGuidanceThresholds, SatisfactionScale
from core.utils.neo4j_props import coerce_int


@dataclass(frozen=True)
class PrincipleChoiceOutcomes:
    """The tally of one principle's guided choices, every one the learner owns, all time.

    ``rating_total`` is the sum of the rated choices' ``satisfaction_score``;
    ``choices_rated_good`` counts those rated at or above ``SatisfactionScale.GOOD``.
    """

    choices_guided: int = 0
    choices_rated: int = 0
    rating_total: int = 0
    choices_rated_good: int = 0

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, object],
    ) -> PrincipleChoiceOutcomes:
        """Read the tally's keys from a row, an absent key read as zero."""
        return cls(
            choices_guided=coerce_int(row.get("choices_guided")),
            choices_rated=coerce_int(row.get("choices_rated")),
            rating_total=coerce_int(row.get("rating_total")),
            choices_rated_good=coerce_int(row.get("choices_rated_good")),
        )

    @property
    def mean_rating(self) -> float | None:
        """The rated choices' mean rating on ``SatisfactionScale``; None with none rated."""
        if self.choices_rated == 0:
            return None
        return self.rating_total / self.choices_rated

    @property
    def satisfaction(self) -> float | None:
        """The mean rating as a share of the scale's top (``1/HIGHEST`` to 1.0)."""
        mean = self.mean_rating
        return None if mean is None else mean / SatisfactionScale.HIGHEST

    @property
    def good_outcome_rate(self) -> float | None:
        """The share of rated choices rated good; None with none rated."""
        if self.choices_rated == 0:
            return None
        return self.choices_rated_good / self.choices_rated

    @property
    def alignment_strength(self) -> float | None:
        """Satisfaction times the good-outcome rate; None with none rated."""
        satisfaction = self.satisfaction
        good_rate = self.good_outcome_rate
        if satisfaction is None or good_rate is None:
            return None
        return satisfaction * good_rate

    @property
    def recommendation(self) -> str:
        """What to do next with this principle's choices, from the tally."""
        satisfaction = self.satisfaction
        good_rate = self.good_outcome_rate
        if self.choices_guided == 0:
            return "Start linking choices to this principle"
        if satisfaction is None or good_rate is None:
            return "Rate how the choices this principle guided turned out"
        if good_rate < PrincipleGuidanceThresholds.GOOD_RATE_FLOOR:
            return "Review how this principle is being applied to choices"
        if satisfaction < PrincipleGuidanceThresholds.SATISFACTION_FLOOR:
            return "Consider if principle interpretation needs refinement"
        if (
            good_rate >= PrincipleGuidanceThresholds.EXCELLENT
            and satisfaction >= PrincipleGuidanceThresholds.EXCELLENT
        ):
            return "Excellent guidance - continue using this principle for decisions"
        return "Continue using this principle for decision guidance"

    def as_payload(self) -> dict[str, int | float | str | None]:
        """The JSON door's shape: counts, the derived figures rounded, the advice."""
        return {
            "total_choices_guided": self.choices_guided,
            "choices_rated": self.choices_rated,
            "avg_satisfaction_score": _rounded(self.satisfaction),
            "positive_outcome_rate": _rounded(self.good_outcome_rate),
            "alignment_strength": _rounded(self.alignment_strength),
            "recommendation": self.recommendation,
        }


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
