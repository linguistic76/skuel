"""Sync honesty — the reconciler's optional retrievability probe.

``VaultReconciler.sync`` probes embedding coverage before and after ingest
(when the gauge is wired) so ``VaultSyncStats`` can say how much of the synced
content is not yet vector-searchable. The hard ruling under test: the probe is
fail-soft — a probe failure sets ``coverage_probe_failed`` and NOTHING else.
It never lands in ``warnings``/``errors``, so it can never flip ``is_clean``
or turn a perfect sync's banner red.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.type_hints import UserUID
from core.ports.vault_bridge_protocol import VaultBridgePort
from core.services.embeddings.retrievability import EmbeddingCoverage, LabelCoverage
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry
from core.services.vault.vault_reconciler import VaultReconciler
from core.utils.result_simplified import Errors, Result

OWNER = UserUID("user_owner")
ADMIN = UserUID("user_admin")


# =========================================================================
# Fixtures / builders
# =========================================================================


def _coverage(missing_chunks: int, missing_entities: int) -> EmbeddingCoverage:
    """A two-label coverage snapshot: one chunk label, one entity label."""
    return EmbeddingCoverage.from_label_counts(
        (
            LabelCoverage(
                label="ContentChunk", total=100, missing=missing_chunks, backfill="./dev x"
            ),
            LabelCoverage(label="Task", total=100, missing=missing_entities, backfill="./dev x"),
        )
    )


class _CoverageProbe:
    """Scripted ``measure_embedding_coverage`` — pops one result per call."""

    def __init__(self, results: list[Result[EmbeddingCoverage]]) -> None:
        self._results = list(results)
        self.calls = 0

    async def measure_embedding_coverage(self) -> Result[EmbeddingCoverage]:
        self.calls += 1
        return self._results.pop(0)


def _registry(tmp_path: Path) -> VaultRegistry:
    def _descriptor(kind: VaultKind, root: Path, owner: str) -> VaultDescriptor:
        return VaultDescriptor(
            kind=kind,
            root=root,
            owner_uid=UserUID(owner),
            allowlist=SyncAllowlist(governed_root=root.resolve(), allowed_dirs=frozenset()),
            bridge=cast("VaultBridgePort", object()),
            supports_task_round_trip=kind is VaultKind.PERSONAL,
        )

    return VaultRegistry(
        content=_descriptor(VaultKind.CONTENT, tmp_path / "content", str(ADMIN)),
        personal=_descriptor(VaultKind.PERSONAL, tmp_path / "personal", str(OWNER)),
    )


def _reconciler(tmp_path: Path, probe: _CoverageProbe | None) -> VaultReconciler:
    user = Mock()
    user.preferences.vault_write_consent = True
    user_service = Mock()
    user_service.get_user = AsyncMock(return_value=Result.ok(user))

    user_entry = Mock()
    user_entry.list_for_user = AsyncMock(return_value=Result.ok([]))

    ingestion = Mock()
    ingestion.ingest_directory = AsyncMock(
        return_value=Result.ok(IncrementalStats(nodes_created=1))
    )

    return VaultReconciler(
        registry=_registry(tmp_path),
        unified_ingestion=ingestion,
        user_entry_service=user_entry,
        tasks_service=Mock(),
        user_service=user_service,
        embedding_coverage=probe,
    )


# =========================================================================
# Tests
# =========================================================================


@pytest.mark.asyncio
async def test_delta_and_absolutes_filled_from_both_probes(tmp_path: Path) -> None:
    """before missing=2, after missing=5 → delta 3; absolutes from the after-probe."""
    probe = _CoverageProbe([Result.ok(_coverage(1, 1)), Result.ok(_coverage(3, 2))])
    reconciler = _reconciler(tmp_path, probe)
    assert reconciler.embedding_coverage is probe  # script door reads the same gauge
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    stats = result.value
    assert probe.calls == 2
    assert stats.chunks_awaiting_embedding == 3
    assert stats.entities_awaiting_embedding == 2
    assert stats.retrievability_delta == 3
    assert stats.coverage_probe_failed is False
    assert stats.is_clean


@pytest.mark.asyncio
async def test_probe_failure_sets_flag_and_nothing_else(tmp_path: Path) -> None:
    """The hard ruling: a failed probe never reaches warnings/errors/is_clean."""
    fail: Result[EmbeddingCoverage] = Result.fail(
        Errors.database("coverage_probe", "neo4j timeout")
    )
    probe = _CoverageProbe([fail, fail])
    result = await _reconciler(tmp_path, probe).sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    stats = result.value
    assert stats.coverage_probe_failed is True
    assert stats.warnings == []
    assert stats.errors == []
    assert stats.retrievability_delta == 0
    assert stats.is_clean


@pytest.mark.asyncio
async def test_after_probe_alone_fills_absolutes_without_delta(tmp_path: Path) -> None:
    """Before-probe fails, after succeeds: absolutes land, delta stays 0, flag set."""
    probe = _CoverageProbe(
        [Result.fail(Errors.database("coverage_probe", "hiccup")), Result.ok(_coverage(4, 1))]
    )
    result = await _reconciler(tmp_path, probe).sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    stats = result.value
    assert stats.coverage_probe_failed is True
    assert stats.chunks_awaiting_embedding == 4
    assert stats.entities_awaiting_embedding == 1
    assert stats.retrievability_delta == 0
    assert stats.is_clean


@pytest.mark.asyncio
async def test_concurrent_embedding_never_reports_negative_delta(tmp_path: Path) -> None:
    """FULL tier: the worker can embed mid-sync, shrinking the missing count —
    the delta clamps at zero instead of crediting the sync."""
    probe = _CoverageProbe([Result.ok(_coverage(4, 1)), Result.ok(_coverage(1, 1))])
    result = await _reconciler(tmp_path, probe).sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    assert result.value.retrievability_delta == 0
    assert result.value.coverage_probe_failed is False


@pytest.mark.asyncio
async def test_no_gauge_wired_leaves_all_defaults(tmp_path: Path) -> None:
    """Optional means optional: an unwired gauge probes nothing and flags nothing."""
    reconciler = _reconciler(tmp_path, None)
    assert reconciler.embedding_coverage is None
    result = await reconciler.sync(VaultKind.PERSONAL, OWNER)

    assert result.is_ok
    stats = result.value
    assert stats.chunks_awaiting_embedding == 0
    assert stats.entities_awaiting_embedding == 0
    assert stats.retrievability_delta == 0
    assert stats.coverage_probe_failed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
