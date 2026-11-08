"""A task's knowledge scores are read from the Kus it links, and span 0.0 to 1.0.

``Task.calculate_knowledge_complexity`` and ``calculate_learning_impact`` take the Kus a
task links (its knowledge edges, read by the caller). Complexity is breadth (up to 0.7
for 7+ Kus) plus opportunity (up to 0.3 for 2+), so the ``> 0.7`` "high complexity"
cut the task analytics read is reachable.
"""

from __future__ import annotations

import pytest

from core.models.task.task import Task


def _task() -> Task:
    return Task(uid="task_0000000000000001", title="Scores", user_uid="user_0000000000000001")


def _kus(count: int) -> set[str]:
    return {f"ku.scores.k{index}" for index in range(count)}


@pytest.mark.parametrize(
    ("count", "complexity"),
    [(0, 0.0), (1, 0.3), (2, 0.5), (4, 0.7), (5, 0.8), (7, 1.0), (12, 1.0)],
)
def test_complexity_is_breadth_plus_opportunity(count: int, complexity: float) -> None:
    assert _task().calculate_knowledge_complexity(_kus(count)) == pytest.approx(complexity)


def test_high_complexity_is_reachable() -> None:
    assert _task().calculate_knowledge_complexity(_kus(5)) > 0.7


def test_a_ku_named_twice_counts_once() -> None:
    task = _task()
    assert task.calculate_knowledge_complexity(["ku.scores.a", "ku.scores.a"]) == pytest.approx(
        task.calculate_knowledge_complexity(["ku.scores.a"])
    )


def test_learning_impact_counts_the_linked_kus() -> None:
    task = _task()
    assert task.calculate_learning_impact(set()) == pytest.approx(0.0)
    assert task.calculate_learning_impact(_kus(2)) == pytest.approx(0.08)
    assert task.calculate_learning_impact(_kus(9)) == pytest.approx(0.20)
