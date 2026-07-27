"""Tests for the LibraryOrchestrator's batch reads.

The property under test is a seam, not a behaviour: the orchestrator sits above
the hexagonal boundary, so its batch reads must go through the domain facade's
own batch method and must never reach ``UniversalNeo4jBackend`` through
``<facade>.core.backend``.

Two deliberate choices in the doubles:

* **Not ``MagicMock``.** ``MagicMock`` auto-vivifies, so
  ``facade.core.backend.get_many`` silently exists on any mock and a test built
  on one passes whichever path the orchestrator takes — it would prove nothing.
  ``_BackendTrap`` raises on the first attribute read instead, so the old path
  fails loudly and the assertion has something to catch.
* **Real ``Ku`` / ``PathStep`` rows, and the facades' real return types.** Both
  models construct from ``uid`` + ``title`` alone, so there is no reason to fake
  them — and typing the stubs' returns as ``Result[list[Ku | None]]`` /
  ``Result[list[PathStep | None]]`` pins them to the production signatures. If
  either facade's contract changes, MyPy fails here rather than the doubles
  quietly drifting behind an ``Any``.
"""

from typing import NoReturn

import pytest

from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.orchestrator.library_orchestrator import LibraryOrchestrator
from core.utils.result_simplified import Result


class _BackendTrap:
    """Stands in for ``<facade>.core``; any attribute read is a boundary crossing."""

    def __getattr__(self, name: str) -> NoReturn:
        raise AssertionError(
            f"LibraryOrchestrator reached the persistence layer via .core.{name} — "
            "batch reads must go through the facade's own batch method"
        )


class _KuFacadeStub:
    def __init__(self, kus: list[Ku | None]) -> None:
        self.core = _BackendTrap()
        self._kus = kus
        self.seen: list[list[str]] = []

    async def get_kus_batch(self, uids: list[str]) -> Result[list[Ku | None]]:
        self.seen.append(list(uids))
        return Result.ok(self._kus)


class _PsFacadeStub:
    def __init__(self, steps: list[PathStep | None]) -> None:
        self.core = _BackendTrap()
        self.mastery = self
        self._steps = steps
        self.seen: list[list[str]] = []

    async def get_in_progress_step_uids(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(["ps.a", "ps.b", "ps.c"])

    async def get_steps_batch(self, uids: list[str]) -> Result[list[PathStep | None]]:
        self.seen.append(list(uids))
        return Result.ok(self._steps)


class _UserRelationshipsStub:
    async def get_pinned_entities(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(["ku.a", "ku.b", "ku.c"])


class _UnusedDependency:
    """A constructor slot this test never exercises; touching it is a failure."""

    def __getattr__(self, name: str) -> NoReturn:
        raise AssertionError(f"unexpected call to an unused dependency: .{name}")


def _build(ku: _KuFacadeStub, ps: _PsFacadeStub) -> LibraryOrchestrator:
    unused = _UnusedDependency()
    return LibraryOrchestrator(
        exercises_service=unused,  # type: ignore[arg-type]  # structural stubs, see module docstring
        resource_service=unused,  # type: ignore[arg-type]
        ku_service=ku,  # type: ignore[arg-type]
        ps_service=ps,  # type: ignore[arg-type]
        user_entry_service=unused,  # type: ignore[arg-type]
        user_relationship_service=_UserRelationshipsStub(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_get_bookmarked_kus_uses_the_facade_batch_method() -> None:
    ku = _KuFacadeStub(kus=[Ku(uid="ku.a", title="A"), Ku(uid="ku.b", title="B"), None])
    ps = _PsFacadeStub(steps=[])

    result = await _build(ku, ps).get_bookmarked_kus("user_1")

    assert not result.is_error
    assert [k.uid for k in result.value] == ["ku.a", "ku.b"], "None rows must still be dropped"
    assert ku.seen == [["ku.a", "ku.b", "ku.c"]]


@pytest.mark.asyncio
async def test_get_bookmarked_kus_applies_the_limit_before_fetching() -> None:
    ku = _KuFacadeStub(kus=[Ku(uid="ku.a", title="A")])
    ps = _PsFacadeStub(steps=[])

    await _build(ku, ps).get_bookmarked_kus("user_1", limit=2)

    assert ku.seen == [["ku.a", "ku.b"]]


@pytest.mark.asyncio
async def test_get_enrolled_path_steps_uses_the_facade_batch_method() -> None:
    ku = _KuFacadeStub(kus=[])
    ps = _PsFacadeStub(
        steps=[PathStep(uid="ps.a", title="A"), None, PathStep(uid="ps.b", title="B")]
    )

    result = await _build(ku, ps).get_enrolled_path_steps("user_1")

    assert not result.is_error
    assert [s.uid for s in result.value] == ["ps.a", "ps.b"]
    assert ps.seen == [["ps.a", "ps.b", "ps.c"]]


@pytest.mark.asyncio
async def test_get_enrolled_path_steps_applies_the_limit_before_fetching() -> None:
    ku = _KuFacadeStub(kus=[])
    ps = _PsFacadeStub(steps=[PathStep(uid="ps.a", title="A")])

    await _build(ku, ps).get_enrolled_path_steps("user_1", limit=1)

    assert ps.seen == [["ps.a"]]
