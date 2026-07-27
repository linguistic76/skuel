"""Regression: `generate_learning_graph` must survive a dangling in-progress edge.

``PsService.get_steps_batch`` is **positional** — it delegates to
``UniversalNeo4jBackend.get_many``, which returns ``None`` in the slot of any UID
that no longer resolves. A user's IN_PROGRESS edge outlives the PathStep it
points at (deleted content, a re-ingest that changed a UID), so the batch can
hand back ``None`` and the node-building comprehension read ``ps.uid`` off it.
That is an `AttributeError` inside a route handler — a 500 on /api/explore/graph.

MyPy did not report it while the facade method returned ``Result[list[Any]]``.
"""

from typing import Any

import pytest

from core.orchestrator.explore_orchestrator import ExploreOrchestrator
from core.utils.result_simplified import Result


class _KuStub:
    async def get_user_learning_states(self, user_uid: str) -> Result[list[Any]]:
        return Result.ok([])


class _MasteryStub:
    def __init__(self, uids: list[str]) -> None:
        self._uids = uids

    async def get_in_progress_step_uids(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(list(self._uids))


class _PsStub:
    def __init__(self, uids: list[str], steps: list[Any]) -> None:
        self.mastery = _MasteryStub(uids)
        self._steps = steps

    async def get_steps_batch(self, uids: list[str]) -> Result[list[Any]]:
        return Result.ok(self._steps)


class _RelationshipsStub:
    async def get_pinned_entities(self, user_uid: str) -> Result[list[str]]:
        return Result.ok([])

    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        return Result.ok([])


class _Step:
    def __init__(self, uid: str, title: str) -> None:
        self.uid = uid
        self.title = title


def _build(ps: _PsStub) -> ExploreOrchestrator:
    unused: Any = object()
    return ExploreOrchestrator(
        ku_service=_KuStub(),  # type: ignore[arg-type]  # structural stub
        ps_service=ps,  # type: ignore[arg-type]
        user_relationship_service=_RelationshipsStub(),  # type: ignore[arg-type]
        exercises_service=unused,
        learning_loop_query_service=unused,
    )


@pytest.mark.asyncio
async def test_learning_graph_skips_a_dangling_in_progress_path_step() -> None:
    ps = _PsStub(
        uids=["ps.alive", "ps.deleted"],
        steps=[_Step("ps.alive", "Alive step"), None],
    )

    graph = await _build(ps).generate_learning_graph("user_1")

    # The graph always carries a synthetic "__you__" centre node; assert on the
    # PathStep nodes only, or the centre node hides what is being measured.
    assert [n["id"] for n in graph["nodes"] if n["type"] == "ps"] == ["ps.alive"]


@pytest.mark.asyncio
async def test_learning_graph_still_builds_every_resolvable_step() -> None:
    ps = _PsStub(
        uids=["ps.a", "ps.b"],
        steps=[_Step("ps.a", "A"), _Step("ps.b", "")],
    )

    graph = await _build(ps).generate_learning_graph("user_1")

    assert [(n["id"], n["label"]) for n in graph["nodes"] if n["type"] == "ps"] == [
        ("ps.a", "A"),
        ("ps.b", "ps.b"),  # empty title falls back to the UID
    ]
