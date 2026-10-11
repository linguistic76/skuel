"""Curriculum readers read fields their writers populate.

- The learner's step progress on an active path counts the steps the path's
  read composed (``metadata["steps"]``) — the goal progress tracker, the
  learning-aligned suggestions and both principle embodiment scorers.
- Askesis skips a step the learner has mastered by their own MASTERED edge
  (``UserContext.mastered_ps_uids``), never by a property of the shared node.
- The LP completion strategy names the path's own learning level.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain
from core.models.enums.learning_enums import LearningLevel
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.lp_position import LpPosition
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.services.askesis.context_retriever import ContextRetriever
from core.services.goals.goals_learning_service import GoalsLearningService
from core.services.lp.lp_ai_service import LpAIService
from core.services.principles.principles_learning_service import (
    PrinciplesLearningService,
    _calculate_virtue_embodiment_score,
)
from core.services.tasks.tasks_learning_service import TasksLearningService
from core.services.user import UserContext
from core.utils.result_simplified import Result

_USER = "user_curriculum_readers"


def _step(uid: str) -> PathStep:
    return PathStep(uid=uid, title=f"Step {uid}", intent="Learn it")


def _position(completed: set[str]) -> LpPosition:
    """One active path of four composed steps; ``completed`` of them done."""
    steps = [_step(f"ps.readers.s{i}") for i in range(4)]
    path = LearningPath(
        uid="lp.readers.python",
        title="Python Mastery",
        description="Master Python",
        domain=Domain.TECH,
        metadata={"steps": steps},
    )
    return LpPosition(
        user_uid=_USER,
        active_paths=[path],
        current_steps={},
        completed_step_uids=completed,
        next_recommended=[],
        generated_at=datetime.now(),
        readiness_scores={},
    )


def test_step_progress_counts_the_composed_steps() -> None:
    position = _position({"ps.readers.s0", "ps.readers.s1", "ps.elsewhere"})
    assert position.step_progress(position.active_paths[0]) == (2, 4)


def test_step_progress_of_a_path_read_without_steps_is_zero_of_zero() -> None:
    path = LearningPath(uid="lp.readers.bare", title="Bare", domain=Domain.TECH)
    assert _position(set()).step_progress(path) == (0, 0)


@pytest.mark.anyio
async def test_goal_learning_progress_reports_the_paths_steps() -> None:
    backend = Mock()
    backend.get_goal = AsyncMock(
        return_value=Result.ok(
            {
                "uid": "goal_readers_1",
                "user_uid": _USER,
                "title": "Finish Python Mastery",
                "entity_type": "goal",
            }
        )
    )
    service = GoalsLearningService(backend=backend)

    result = await service.track_goal_learning_progress(
        "goal_readers_1", _position({"ps.readers.s0"})
    )

    assert result.is_ok, result
    [path_data] = result.value.supporting_paths_progress
    assert (path_data.completed_steps, path_data.total_steps) == (1, 4)
    assert path_data.progress == 0.25


@pytest.mark.anyio
async def test_learning_aligned_suggestions_name_the_remaining_steps() -> None:
    backend = Mock()
    service = TasksLearningService(backend=backend)

    result = await service.suggest_learning_aligned_tasks(_position({"ps.readers.s0"}), limit=10)

    assert result.is_ok, result
    completion = [s for s in result.value if s["title"] == "Complete Python Mastery Learning Path"]
    assert len(completion) == 1
    assert "3 remaining steps" in completion[0]["description"]


@pytest.mark.anyio
async def test_learning_aligned_suggestions_omit_completion_for_a_finished_path() -> None:
    """Control: every composed step completed → no completion suggestion."""
    service = TasksLearningService(backend=Mock())
    done = {f"ps.readers.s{i}" for i in range(4)}

    result = await service.suggest_learning_aligned_tasks(_position(done), limit=10)

    assert result.is_ok, result
    assert not [s for s in result.value if s["title"].startswith("Complete ")]


def test_virtue_embodiment_score_follows_step_progress() -> None:
    principle = Principle(uid="principle_readers_1", user_uid=_USER, title="Steadiness")
    half = _calculate_virtue_embodiment_score(
        principle, _position({"ps.readers.s0", "ps.readers.s1"})
    )
    assert half == pytest.approx(0.5 * 0.7)
    assert _calculate_virtue_embodiment_score(principle, _position(set())) == 0.0


@pytest.mark.anyio
async def test_principle_learning_development_reads_the_paths_steps() -> None:
    backend = Mock()
    backend.get = AsyncMock(
        return_value=Result.ok(
            Principle(uid="principle_readers_2", user_uid=_USER, title="Discipline")
        )
    )
    service = PrinciplesLearningService(backend=backend)
    done = {f"ps.readers.s{i}" for i in range(4)}

    result = await service.track_principle_learning_development(
        "principle_readers_2", _position(done)
    )

    assert result.is_ok, result
    [embodiment] = result.value["learning_path_embodiment"]
    assert embodiment["progress"] == 1.0
    assert result.value["learning_development_score"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Askesis — a mastered step is the learner's MASTERED edge
# ---------------------------------------------------------------------------


def _ps_item(uid: str) -> dict[str, Any]:
    return {
        "entity": {"uid": uid, "title": f"Step {uid}", "mastery_threshold": 0.7},
        "graph_context": {},
    }


@pytest.mark.anyio
async def test_askesis_skips_a_step_the_learner_has_mastered() -> None:
    context = UserContext(user_uid=_USER)
    context.active_path_steps_rich = [_ps_item("ps.readers.done"), _ps_item("ps.readers.next")]  # type: ignore[list-item]
    context.mastered_ps_uids = {"ps.readers.done"}

    chosen, _ = await ContextRetriever()._find_active_ps(_USER, context)

    assert chosen is not None
    assert chosen["entity"]["uid"] == "ps.readers.next"  # type: ignore[typeddict-item]


@pytest.mark.anyio
async def test_askesis_chooses_a_step_the_learner_has_not_mastered() -> None:
    """Control: the same step, with no MASTERED edge from this learner, is chosen."""
    context = UserContext(user_uid=_USER)
    context.active_path_steps_rich = [_ps_item("ps.readers.done")]  # type: ignore[list-item]

    chosen, _ = await ContextRetriever()._find_active_ps(_USER, context)

    assert chosen is not None
    assert chosen["entity"]["uid"] == "ps.readers.done"  # type: ignore[typeddict-item]


# ---------------------------------------------------------------------------
# LP completion strategy — the path's own level
# ---------------------------------------------------------------------------


class _CapturingLpAI(LpAIService):
    """Records the context the strategy prompt is built from; sends nothing."""

    captured: dict[str, object]

    async def _generate_insight(
        self,
        prompt: str,
        context: Mapping[str, object] | None = None,
        max_tokens: int = 500,
    ) -> Result[str]:
        self.captured = dict(context or {})
        return Result.ok("PACE: steady")


@pytest.mark.anyio
@pytest.mark.parametrize("level", [LearningLevel.ADVANCED, LearningLevel.BEGINNER])
async def test_completion_strategy_names_the_paths_learning_level(level: LearningLevel) -> None:
    path = LearningPath(
        uid="lp.readers.levelled", title="Levelled", domain=Domain.TECH, learning_level=level
    )
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(path))
    service = _CapturingLpAI(
        backend=backend, llm_service=Mock(), embeddings_service=Mock(), vector_search=Mock()
    )

    result = await service.suggest_completion_strategy(path.uid)

    assert result.is_ok, result
    assert service.captured["learning_level"] == level.value
    assert "difficulty" not in service.captured
