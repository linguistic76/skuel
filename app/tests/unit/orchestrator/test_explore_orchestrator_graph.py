"""Regression: `generate_learning_graph` must survive a dangling in-progress edge.

``PsService.get_steps_batch`` is **positional** — it delegates to
``UniversalNeo4jBackend.get_many``, which returns ``None`` in the slot of any UID
that no longer resolves. A user's IN_PROGRESS edge outlives the PathStep it
points at (deleted content, a re-ingest that changed a UID), so the batch can
hand back ``None`` and the node-building comprehension read ``ps.uid`` off it.
That is an `AttributeError` inside a route handler — a 500 on /api/explore/graph.

MyPy did not report it while the facade method returned ``Result[list[Any]]``,
which is why the stubs below mirror the real return types exactly: a double that
widens the contract it stands in for reproduces the very erasure that hid this
bug.
"""

from typing import Any, NoReturn

import pytest

from core.models.pathways.path_step import PathStep
from core.orchestrator.explore_orchestrator import ExploreOrchestrator
from core.utils.result_simplified import Result


class _KuStub:
    async def get_user_learning_states(self, user_uid: str) -> Result[list[dict[str, Any]]]:
        # Mirrors KuService.get_user_learning_states — the inner Any is the
        # production signature's, not a new one.
        return Result.ok([])


class _MasteryStub:
    def __init__(self, uids: list[str]) -> None:
        self._uids = uids

    async def get_in_progress_step_uids(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(list(self._uids))


class _PsStub:
    def __init__(self, uids: list[str], steps: list[PathStep | None]) -> None:
        self.mastery = _MasteryStub(uids)
        self._steps = steps

    async def get_steps_batch(self, uids: list[str]) -> Result[list[PathStep | None]]:
        return Result.ok(self._steps)


class _RelationshipsStub:
    async def get_pinned_entities(self, user_uid: str) -> Result[list[str]]:
        return Result.ok([])

    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        return Result.ok([])


class _UnusedDependency:
    """A constructor slot this test never exercises; touching it is a failure."""

    def __getattr__(self, name: str) -> NoReturn:
        raise AssertionError(f"unexpected call to an unused dependency: .{name}")


def _build(ps: _PsStub) -> ExploreOrchestrator:
    unused = _UnusedDependency()
    return ExploreOrchestrator(
        ku_service=_KuStub(),  # type: ignore[arg-type]  # structural stubs, see module docstring
        ps_service=ps,  # type: ignore[arg-type]
        user_relationship_service=_RelationshipsStub(),  # type: ignore[arg-type]
        exercises_service=unused,  # type: ignore[arg-type]
        learning_loop_query_service=unused,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_learning_graph_skips_a_dangling_in_progress_path_step() -> None:
    ps = _PsStub(
        uids=["ps.alive", "ps.deleted"],
        steps=[PathStep(uid="ps.alive", title="Alive step"), None],
    )

    graph = await _build(ps).generate_learning_graph("user_1")

    # The graph always carries a synthetic "__you__" centre node; assert on the
    # PathStep nodes only, or the centre node hides what is being measured.
    assert [n["id"] for n in graph["nodes"] if n["type"] == "ps"] == ["ps.alive"]


@pytest.mark.asyncio
async def test_learning_graph_still_builds_every_resolvable_step() -> None:
    ps = _PsStub(
        uids=["ps.a", "ps.b"],
        steps=[PathStep(uid="ps.a", title="A"), PathStep(uid="ps.b", title="")],
    )

    graph = await _build(ps).generate_learning_graph("user_1")

    assert [(n["id"], n["label"]) for n in graph["nodes"] if n["type"] == "ps"] == [
        ("ps.a", "A"),
        ("ps.b", "ps.b"),  # empty title falls back to the UID
    ]
