"""``PrincipleChoiceOutcomes`` derives every figure from the rated choices only.

An unrated choice has no satisfaction, not a low one: it counts toward
``choices_guided`` and nowhere else, and with nothing rated each derived figure is
``None``. Every recommendation branch is reached here with ratings on the real scale
(``SatisfactionScale``), so a threshold that moved past what a rating can produce
would leave a branch unreached and fail.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.query.cypher.choice_fragments import build_choice_outcome_tally
from core.constants import SatisfactionScale
from core.models.principle.choice_outcomes import PrincipleChoiceOutcomes


def _tally(guided: int, *ratings: int) -> PrincipleChoiceOutcomes:
    """The tally the Cypher fragment builds for ``guided`` choices, ``ratings`` of them rated."""
    return PrincipleChoiceOutcomes(
        choices_guided=guided,
        choices_rated=len(ratings),
        rating_total=sum(ratings),
        choices_rated_good=sum(1 for rating in ratings if rating >= SatisfactionScale.GOOD),
    )


def test_an_unrated_choice_counts_as_guided_and_nowhere_else() -> None:
    outcomes = _tally(12, 5, 3, 4)

    assert outcomes.choices_guided == 12
    assert outcomes.mean_rating == pytest.approx(4.0)
    assert outcomes.satisfaction == pytest.approx(4.0 / SatisfactionScale.HIGHEST)
    assert outcomes.good_outcome_rate == pytest.approx(2 / 3)


def test_with_nothing_rated_every_derived_figure_is_none() -> None:
    outcomes = _tally(3)

    assert outcomes.mean_rating is None
    assert outcomes.satisfaction is None
    assert outcomes.good_outcome_rate is None
    assert outcomes.alignment_strength is None
    assert outcomes.recommendation == "Rate how the choices this principle guided turned out"


def test_the_payload_carries_none_not_zero_for_an_unrated_principle() -> None:
    payload = _tally(3).as_payload()

    assert payload == {
        "total_choices_guided": 3,
        "choices_rated": 0,
        "avg_satisfaction_score": None,
        "positive_outcome_rate": None,
        "alignment_strength": None,
        "recommendation": "Rate how the choices this principle guided turned out",
    }


@pytest.mark.parametrize(
    ("outcomes", "recommendation"),
    [
        (_tally(0), "Start linking choices to this principle"),
        (_tally(3, 1, 2, 5), "Review how this principle is being applied to choices"),
        (_tally(2, 4, 1), "Consider if principle interpretation needs refinement"),
        (_tally(2, 4, 5), "Excellent guidance - continue using this principle for decisions"),
        (_tally(3, 4, 4, 3), "Continue using this principle for decision guidance"),
    ],
)
def test_each_recommendation_is_reached_by_real_ratings(
    outcomes: PrincipleChoiceOutcomes, recommendation: str
) -> None:
    assert outcomes.recommendation == recommendation


def test_a_row_reads_the_tally_keys_the_fragment_writes() -> None:
    fragment = build_choice_outcome_tally("guided")
    keys = {entry.split(":", 1)[0].strip() for entry in fragment.split(", ") if ":" in entry}
    row = dict.fromkeys(keys, 2)

    outcomes = PrincipleChoiceOutcomes.from_row(row)

    assert keys == {"choices_guided", "choices_rated", "rating_total", "choices_rated_good"}
    assert outcomes == PrincipleChoiceOutcomes(2, 2, 2, 2)
