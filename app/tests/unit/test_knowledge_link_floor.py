"""The knowledge-link floor: one constant the rich user context reads and grounding obeys.

The rich user context keeps an ``APPLIES_KNOWLEDGE`` edge when its confidence is at
least the context's ``min_confidence``; grounding stores the vector similarity as an
inferred link's confidence. ``KnowledgeLinkConfidence.FLOOR`` is both numbers: every
signature on the rich context's path defaults to it, and ``GroundingConfig`` refuses a
threshold below it — at the config, and at ``scripts/ground_knowledge.py --threshold``
before the script connects to the graph.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.persistence.neo4j.user_context_queries import (
    UserContextQueryExecutor,
    build_mega_query_params,
)
from core.constants import KnowledgeLinkConfidence
from core.ports.user_context_protocols import UserContextQueryOperations
from core.services.knowledge_grounding_service import GroundingConfig
from core.services.user._context_planning_mixin import _ContextPlanningMixin
from core.services.user.user_context_builder import UserContextBuilder

if TYPE_CHECKING:
    from collections.abc import Callable

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ground_knowledge  # type: ignore[import-not-found]

FLOOR = KnowledgeLinkConfidence.FLOOR
BELOW = round(FLOOR - 0.02, 2)

# Every signature a rich context's ``min_confidence`` passes through, from the
# service a caller reaches to the parameter map the statements run with.
RICH_CONTEXT_PATH: list[Callable[..., object]] = [
    _ContextPlanningMixin.get_rich_unified_context,
    UserContextBuilder.build_rich,
    UserContextBuilder.build_rich_user_context,
    UserContextQueryOperations.execute_mega_query,
    UserContextQueryOperations.fetch_entry_knowledge_applied,
    UserContextQueryExecutor.execute_mega_query,
    UserContextQueryExecutor.fetch_entry_knowledge_applied,
    build_mega_query_params,
]


def _qualname(function: Callable[..., object]) -> str:
    return function.__qualname__


@pytest.mark.parametrize("function", RICH_CONTEXT_PATH, ids=_qualname)
def test_the_rich_context_defaults_to_the_floor(function: Callable[..., object]) -> None:
    default = inspect.signature(function).parameters["min_confidence"].default
    assert default == FLOOR, f"{function.__qualname__} defaults min_confidence to {default}"


def test_the_default_threshold_is_at_or_above_the_floor() -> None:
    assert GroundingConfig().threshold >= FLOOR


def test_a_threshold_at_the_floor_is_accepted() -> None:
    assert GroundingConfig(threshold=FLOOR).threshold == FLOOR


def test_a_threshold_below_the_floor_is_refused() -> None:
    with pytest.raises(ValueError, match="below the knowledge-link floor"):
        GroundingConfig(threshold=BELOW)


def test_a_replace_below_the_floor_is_refused() -> None:
    """The script's override is a ``replace`` of the composed config."""
    with pytest.raises(ValueError, match="below the knowledge-link floor"):
        replace(GroundingConfig(), threshold=BELOW)


def _run_main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[object, list[float | None]]:
    """Run the script's ``main`` with ``argv``, the pass stood in.

    Returns the exit code and the threshold of each pass that ran.
    """
    ran: list[float | None] = []

    async def run_grounding(
        source: str, user_uid: str | None, apply: bool, force: bool, threshold: float | None
    ) -> int:
        ran.append(threshold)
        return 0

    monkeypatch.setattr(ground_knowledge, "run_grounding", run_grounding)
    monkeypatch.setattr(sys, "argv", ["ground_knowledge.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        ground_knowledge.main()
    return exit_info.value.code, ran


def test_the_script_refuses_a_threshold_below_the_floor_before_it_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, ran = _run_main(monkeypatch, "--source", "tasks", "--threshold", str(BELOW))

    assert (code, ran) == (2, []), "argparse refuses; the pass never runs"
    err = capsys.readouterr().err
    assert "argument --threshold" in err
    assert f"grounding threshold {BELOW} is below the knowledge-link floor {FLOOR}" in err


def test_control_the_script_runs_with_a_threshold_at_the_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _run_main(monkeypatch, "--threshold", str(FLOOR)) == (0, [FLOOR])
