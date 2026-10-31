"""SubstanceBand — the Substance Scale's four bands over a personal substance score.

One banding for every surface: the Life Path alignment page's steps and the weekly
knowledge metrics both band through ``from_score``, so its edges are pinned here,
each from both sides.
"""

import pytest

from core.models.enums import AlignmentLevel, SubstanceBand


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (0.0, SubstanceBand.THEORETICAL),
        (0.2999, SubstanceBand.THEORETICAL),
        (0.3, SubstanceBand.APPLIED),
        (0.5999, SubstanceBand.APPLIED),
        (0.6, SubstanceBand.PRACTICED),
        (0.7999, SubstanceBand.PRACTICED),
        (0.8, SubstanceBand.EMBODIED),
        (1.0, SubstanceBand.EMBODIED),
    ],
)
def test_each_edge_belongs_to_the_band_above_it(score: float, band: SubstanceBand) -> None:
    assert SubstanceBand.from_score(score) is band


def test_every_band_has_a_label_and_a_description() -> None:
    for band in SubstanceBand:
        assert band.get_label() == band.value.title()
        assert band.get_description()


def test_an_alignment_level_label_reads_as_words() -> None:
    assert AlignmentLevel.MOSTLY_ALIGNED.get_label() == "Mostly aligned"
    assert AlignmentLevel.FLOURISHING.get_label() == "Flourishing"
