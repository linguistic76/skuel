"""The sentence that tells a learner which step in progress Askesis could not open."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.models.askesis.step_choice import ChosenStep, StepChoice


def _chosen(title: str) -> ChosenStep:
    path_step = MagicMock()
    path_step.title = title
    return ChosenStep(item={"step": {}, "graph_context": {}}, path_step=path_step)


@pytest.mark.parametrize(
    ("choice", "notice"),
    [
        (StepChoice(), ""),
        (StepChoice(chosen=_chosen("Naming")), ""),
        (
            StepChoice(unopened_titles=(None,)),
            "I couldn't open one of your steps just now, so this answer isn't drawn from its "
            "material.",
        ),
        (
            StepChoice(chosen=_chosen("Naming"), unopened_titles=("Noticing", "Pausing")),
            'I couldn\'t open 2 of your steps ("Noticing" and "Pausing") just now, so I\'m '
            'working from "Naming".',
        ),
        (
            StepChoice(unopened_titles=("Noticing", None, "Pausing", "Waiting")),
            'I couldn\'t open 4 of your steps ("Noticing", "Pausing" and "Waiting") just now, '
            "so this answer isn't drawn from their material.",
        ),
        (
            StepChoice(unopened_titles=(None, None)),
            "I couldn't open 2 of your steps just now, so this answer isn't drawn from their "
            "material.",
        ),
    ],
)
def test_the_notice_names_the_steps_passed_over(choice: StepChoice, notice: str) -> None:
    assert choice.unopened_notice() == notice
