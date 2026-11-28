"""A task's learning relevance is its strongest knowledge match.

``LpPosition.assess_task_relevance`` scores a task by the Kus it applies alone:
a Ku of an active path's current step scores ``TaskLearningRelevance.CURRENT_STEP``,
a Ku of the path's next step to complete ``NEXT_STEP``, and the score is the
strongest match across the paths, so matching more never scores less. A task with
no match scores ``NO_MATCH``, whether its knowledge sits elsewhere or it applies none.

Positions come from ``create_lp_position``. Its current step is the first step
not completed that is ready, and the next step to complete is the first step not
completed, so the two are one step unless the readiness map holds that step back:
here the map holds back the first step, the current step is the second, and the
first is still the next to complete.
"""

from __future__ import annotations

import pytest

from core.constants import TaskLearningRelevance
from core.models.enums import Domain
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.lp_position import LpPosition, create_lp_position
from core.models.pathways.path_step import PathStep

_USER = "user_task_relevance"


def _path(name: str, domain: Domain = Domain.PERSONAL) -> LearningPath:
    """A path of two steps, ``ps.{name}.first`` and ``ps.{name}.second``, one Ku each."""
    steps = [
        PathStep(
            uid=f"ps.{name}.{place}",
            title=f"{name} {place}",
            intent="Learn it",
            knowledge_uids=(f"ku.{name}.{place}",),
        )
        for place in ("first", "second")
    ]
    return LearningPath(
        uid=f"lp.{name}",
        title=name,
        description=f"The {name} path",
        domain=domain,
        metadata={"steps": steps},
    )


def _first_held_back(*paths: LearningPath) -> LpPosition:
    """Each path's first step is not ready: current = its second, next to complete = its first."""
    return create_lp_position(
        _USER,
        list(paths),
        set(),
        readiness_map={f"ps.{path.title}.first": False for path in paths},
    )


def test_a_current_step_ku_scores_current() -> None:
    position = _first_held_back(_path("breath"))

    assert position.assess_task_relevance(["ku.breath.second"]) == pytest.approx(
        TaskLearningRelevance.CURRENT_STEP
    )


def test_a_next_step_ku_scores_next() -> None:
    position = _first_held_back(_path("breath"))

    assert position.assess_task_relevance(["ku.breath.first"]) == pytest.approx(
        TaskLearningRelevance.NEXT_STEP
    )


def test_a_current_and_a_next_step_ku_score_the_stronger() -> None:
    position = _first_held_back(_path("breath"))

    assert position.assess_task_relevance(["ku.breath.first", "ku.breath.second"]) == pytest.approx(
        TaskLearningRelevance.CURRENT_STEP
    )


def test_the_current_step_that_is_also_next_to_complete_scores_current() -> None:
    """No readiness map: the first step is both current and next to complete."""
    position = create_lp_position(_USER, [_path("breath")], set())

    assert position.assess_task_relevance(["ku.breath.first"]) == pytest.approx(
        TaskLearningRelevance.CURRENT_STEP
    )


def test_current_in_one_path_and_next_in_another_score_the_stronger() -> None:
    position = _first_held_back(_path("breath"), _path("journal"))

    assert position.assess_task_relevance(
        ["ku.breath.second", "ku.journal.first"]
    ) == pytest.approx(TaskLearningRelevance.CURRENT_STEP)


def test_knowledge_on_no_current_or_next_step_scores_what_no_knowledge_scores() -> None:
    """The second step's Ku is neither current nor next to complete with no readiness map."""
    position = create_lp_position(_USER, [_path("breath")], set())

    off_path = position.assess_task_relevance(["ku.breath.second", "ku.elsewhere.concept"])
    none = position.assess_task_relevance([])

    assert off_path == pytest.approx(TaskLearningRelevance.NO_MATCH)
    assert none == pytest.approx(TaskLearningRelevance.NO_MATCH)


def test_with_no_active_path_applied_knowledge_scores_no_match() -> None:
    position = create_lp_position(_USER, [], set())

    assert position.assess_task_relevance(["ku.breath.first"]) == pytest.approx(
        TaskLearningRelevance.NO_MATCH
    )


def test_a_next_step_ku_scores_next_on_a_path_with_no_current_step() -> None:
    """Both steps held back: the path has no current step, and its first is next to complete."""
    position = create_lp_position(
        _USER,
        [_path("breath")],
        set(),
        readiness_map={"ps.breath.first": False, "ps.breath.second": False},
    )

    assert position.current_steps == {}
    assert position.assess_task_relevance(["ku.breath.first"]) == pytest.approx(
        TaskLearningRelevance.NEXT_STEP
    )


def test_a_completed_path_scores_no_match() -> None:
    """Every step completed: the path has no current step and no next step to complete."""
    path = _path("breath")
    position = create_lp_position(_USER, [path], {"ps.breath.first", "ps.breath.second"})

    assert position.assess_task_relevance(["ku.breath.first"]) == pytest.approx(
        TaskLearningRelevance.NO_MATCH
    )


def test_the_scale_is_current_half_next_four_tenths_no_match_one_tenth() -> None:
    assert (
        TaskLearningRelevance.CURRENT_STEP,
        TaskLearningRelevance.NEXT_STEP,
        TaskLearningRelevance.NO_MATCH,
    ) == (0.5, 0.4, 0.1)
