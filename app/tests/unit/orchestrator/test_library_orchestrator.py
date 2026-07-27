"""Tests for the LibraryOrchestrator's batch reads.

The property under test is a seam, not a behaviour: the orchestrator sits
above the hexagonal boundary, so its batch reads must go through the domain
facade's own batch method and must never reach ``UniversalNeo4jBackend``
through ``<facade>.core.backend``.

The doubles are deliberately NOT ``MagicMock``. ``MagicMock`` auto-vivifies,
so ``facade.core.backend.get_many`` silently exists on any mock and a test
built on one passes whichever path the orchestrator takes — it would prove
nothing. ``_BackendTrap`` raises on the first attribute read instead, so the
old path fails loudly and the assertion has something to catch.
"""

from typing import Any

import pytest

from core.orchestrator.library_orchestrator import LibraryOrchestrator
from core.utils.result_simplified import Result


class _BackendTrap:
    """Stands in for ``<facade>.core``; any attribute read is a boundary crossing."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"LibraryOrchestrator reached the persistence layer via .core.{name} — "
            "batch reads must go through the facade's own batch method"
        )


class _KuFacadeStub:
    def __init__(self, kus: list[Any]) -> None:
        self.core = _BackendTrap()
        self._kus = kus
        self.seen: list[list[str]] = []

    async def get_kus_batch(self, uids: list[str]) -> Result[list[Any]]:
        self.seen.append(list(uids))
        return Result.ok(self._kus)


class _PsFacadeStub:
    def __init__(self, steps: list[Any]) -> None:
        self.core = _BackendTrap()
        self.mastery = self
        self._steps = steps
        self.seen: list[list[str]] = []

    async def get_in_progress_step_uids(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(["ps.a", "ps.b", "ps.c"])

    async def get_steps_batch(self, uids: list[str]) -> Result[list[Any]]:
        self.seen.append(list(uids))
        return Result.ok(self._steps)


class _UserRelationshipsStub:
    async def get_pinned_entities(self, user_uid: str) -> Result[list[str]]:
        return Result.ok(["ku.a", "ku.b", "ku.c"])


def _build(ku: _KuFacadeStub, ps: _PsFacadeStub) -> LibraryOrchestrator:
    unused: Any = object()
    return LibraryOrchestrator(
        exercises_service=unused,
        resource_service=unused,
        ku_service=ku,  # type: ignore[arg-type]  # structural stub, see module docstring
        ps_service=ps,  # type: ignore[arg-type]
        user_entry_service=unused,
        user_relationship_service=_UserRelationshipsStub(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_get_bookmarked_kus_uses_the_facade_batch_method() -> None:
    ku = _KuFacadeStub(kus=["KU-1", "KU-2", None])
    ps = _PsFacadeStub(steps=[])

    result = await _build(ku, ps).get_bookmarked_kus("user_1")

    assert not result.is_error
    assert result.value == ["KU-1", "KU-2"], "None rows must still be dropped"
    assert ku.seen == [["ku.a", "ku.b", "ku.c"]]


@pytest.mark.asyncio
async def test_get_bookmarked_kus_applies_the_limit_before_fetching() -> None:
    ku = _KuFacadeStub(kus=["KU-1"])
    ps = _PsFacadeStub(steps=[])

    await _build(ku, ps).get_bookmarked_kus("user_1", limit=2)

    assert ku.seen == [["ku.a", "ku.b"]]


@pytest.mark.asyncio
async def test_get_enrolled_path_steps_uses_the_facade_batch_method() -> None:
    ku = _KuFacadeStub(kus=[])
    ps = _PsFacadeStub(steps=["PS-1", None, "PS-2"])

    result = await _build(ku, ps).get_enrolled_path_steps("user_1")

    assert not result.is_error
    assert result.value == ["PS-1", "PS-2"]
    assert ps.seen == [["ps.a", "ps.b", "ps.c"]]


@pytest.mark.asyncio
async def test_get_enrolled_path_steps_applies_the_limit_before_fetching() -> None:
    ku = _KuFacadeStub(kus=[])
    ps = _PsFacadeStub(steps=["PS-1"])

    await _build(ku, ps).get_enrolled_path_steps("user_1", limit=1)

    assert ps.seen == [["ps.a"]]
