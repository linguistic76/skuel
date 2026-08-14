"""
Integration test: a new mutually-referencing wave links on ONE sync.

Regression guard for the "edge-ordering sync wart". A first vault sync of a wave
of NEW, mutually-referencing entities used to warn "relationship target … does
not exist — edge not created" and (historically) prompted a needless second
``--force`` pass. The two-phase ingest (PR #499) already persists ALL nodes
before ANY relationships, so the edges were in fact created on the first pass —
the warning was cosmetic: the ``validate_targets`` pre-check ran against the
graph only and false-alarmed on same-sync forward references.

This test ingests such a wave EXACTLY ONCE with ``validate_targets=True`` and
asserts BOTH properties that make the pre-check truthful:

- every expected edge exists after the single sync (inline USES_KU + inline
  ENABLES_KNOWLEDGE + a standalone ``type: Edge`` file), and
- ZERO spurious warnings are emitted (the payload-aware pre-check recognizes
  same-sync targets as valid).

It also proves the signal is preserved: a genuinely-missing target (a typo /
cross-vault reference) still warns.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.ingestion.types import IncrementalStats

# Graph stores DOT-normalized UIDs (vault authors colons).
_KU_ALPHA = "ku.zzzitest.alpha"
_KU_BETA = "ku.zzzitest.beta"
_PS_ONE = "ps.zzzitest.one"
_PS_TWO = "ps.zzzitest.two"
_ALL_UIDS = [_KU_ALPHA, _KU_BETA, _PS_ONE, _PS_TWO]

_KU_ALPHA_FIXTURE = """---
version: 1.0
type: Ku
uid: ku.zzzitest.alpha
title: ZZZ Integration Test Alpha
nous:
  - zzzitest
sel_category: self_awareness
description: Same-sync forward-reference test Ku alpha.
tags:
  - zzzitest
---

Body alpha.
"""

_KU_BETA_FIXTURE = """---
version: 1.0
type: Ku
uid: ku.zzzitest.beta
title: ZZZ Integration Test Beta
nous:
  - zzzitest
sel_category: self_awareness
description: Same-sync forward-reference test Ku beta.
tags:
  - zzzitest
---

Body beta.
"""

# PathStep one forward-references a same-sync Ku (uses_kus) AND a same-sync
# PathStep (connections.enables) — both defined in later type batches.
_PS_ONE_FIXTURE = """---
type: PathStep
uid: ps.zzzitest.one
title: ZZZ Integration Test PathStep One
sel_category: self_awareness
learning_level: beginner
nous:
  - zzzitest
uses_kus:
  - ku.zzzitest.alpha
connections:
  enables:
    - ps.zzzitest.two
tags:
  - zzzitest
---

Body one.
"""

_PS_TWO_FIXTURE = """---
type: PathStep
uid: ps.zzzitest.two
title: ZZZ Integration Test PathStep Two
sel_category: self_awareness
learning_level: beginner
nous:
  - zzzitest
tags:
  - zzzitest
---

Body two.
"""

# Standalone edge file between two same-sync Kus (a DIFFERENT ingestion path
# from the inline pre-check).
_EDGE_FIXTURE = """---
type: Edge
from: ku.zzzitest.alpha
to: ku.zzzitest.beta
relationship: ENABLES_KNOWLEDGE
---
"""


@pytest_asyncio.fixture
async def forward_ref_service(neo4j_driver):
    """UnifiedIngestionService with tracker wired (smart mode + pre-check)."""
    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
    )
    yield service
    # Session-scoped container — clean up this test's nodes + tracker rows.
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", {"uids": _ALL_UIDS})
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid IN $uids DELETE s",
            {"uids": _ALL_UIDS},
        )


async def _edge_exists(neo4j_driver, from_uid: str, rel: str, to_uid: str) -> bool:
    async with neo4j_driver.session() as session:
        res = await session.run(
            f"MATCH (a {{uid: $f}})-[r:{rel}]->(b {{uid: $t}}) RETURN count(r) AS c",
            {"f": from_uid, "t": to_uid},
        )
        record = await res.single()
        return bool(record and record["c"] > 0)


@pytest.mark.asyncio
async def test_mutually_referencing_wave_links_on_one_sync_without_warnings(
    neo4j_driver, forward_ref_service, tmp_path: Path
) -> None:
    vault = tmp_path / "wave_vault"
    vault.mkdir()
    (vault / "ku_alpha.md").write_text(_KU_ALPHA_FIXTURE, encoding="utf-8")
    (vault / "ku_beta.md").write_text(_KU_BETA_FIXTURE, encoding="utf-8")
    (vault / "ps_one.md").write_text(_PS_ONE_FIXTURE, encoding="utf-8")
    (vault / "ps_two.md").write_text(_PS_TWO_FIXTURE, encoding="utf-8")
    (vault / "edge_alpha_enables_beta.md").write_text(_EDGE_FIXTURE, encoding="utf-8")

    result = await forward_ref_service.ingest_directory(
        vault, ingestion_mode="smart", validate_targets=True
    )
    assert result.is_ok, f"ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert stats.files_ingested == 5

    # 1. Zero spurious warnings: same-sync forward references must not warn.
    assert stats.warnings == [], f"unexpected pre-check warnings: {stats.warnings}"

    # 2. Every expected edge exists after the SINGLE sync — no --force needed.
    assert await _edge_exists(neo4j_driver, _PS_ONE, "USES_KU", _KU_ALPHA), (
        "inline uses_kus edge missing"
    )
    assert await _edge_exists(neo4j_driver, _PS_ONE, "ENABLES_KNOWLEDGE", _PS_TWO), (
        "inline connections.enables edge missing"
    )
    assert await _edge_exists(neo4j_driver, _KU_ALPHA, "ENABLES_KNOWLEDGE", _KU_BETA), (
        "standalone edge-file edge missing"
    )


@pytest.mark.asyncio
async def test_genuinely_missing_target_still_warns(
    neo4j_driver, forward_ref_service, tmp_path: Path
) -> None:
    """The valuable signal is preserved: a target that is neither in the graph
    nor in the payload (typo / cross-vault ref) still produces a warning."""
    vault = tmp_path / "typo_vault"
    vault.mkdir()
    # A PathStep whose uses_kus points at a Ku that is NOT in this sync.
    typo_ps = _PS_ONE_FIXTURE.replace(
        "  - ku.zzzitest.alpha", "  - ku.zzzitest.does-not-exist"
    ).replace("  enables:\n    - ps.zzzitest.two", "  enables: []")
    (vault / "ps_typo.md").write_text(typo_ps, encoding="utf-8")

    result = await forward_ref_service.ingest_directory(
        vault, ingestion_mode="smart", validate_targets=True
    )
    assert result.is_ok, f"ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert any("does-not-exist" in w for w in stats.warnings), (
        f"a genuinely-missing target must still warn; got: {stats.warnings}"
    )


@pytest.mark.asyncio
async def test_same_sync_target_with_wrong_label_still_warns(
    neo4j_driver, forward_ref_service, tmp_path: Path
) -> None:
    """Payload membership is label-scoped: a same-sync UID that carries the WRONG
    label for the relationship still warns.

    ``uses_kus`` expects a ``:Ku`` target, but here it points at a same-sync
    PathStep. Phase 2's ``MATCH (target:Ku {uid})`` would find nothing and drop
    the edge — so a flat payload-UID check would hide a genuine break. The
    pre-check must still warn (and the edge must genuinely be absent)."""
    vault = tmp_path / "wrong_label_vault"
    vault.mkdir()
    # PathStep one's uses_kus points at ps.zzzitest.two (a PathStep, not a Ku),
    # and that PathStep IS in this same sync.
    mislabelled = _PS_ONE_FIXTURE.replace("  - ku.zzzitest.alpha", "  - ps.zzzitest.two").replace(
        "  enables:\n    - ps.zzzitest.two", "  enables: []"
    )
    (vault / "ps_one.md").write_text(mislabelled, encoding="utf-8")
    (vault / "ps_two.md").write_text(_PS_TWO_FIXTURE, encoding="utf-8")

    result = await forward_ref_service.ingest_directory(
        vault, ingestion_mode="smart", validate_targets=True
    )
    assert result.is_ok, f"ingest failed: {result}"
    stats = cast("IncrementalStats", result.value)
    # The mis-labelled target is in the payload (as a PathStep) but NOT under the
    # :Ku label the edge needs — it must still warn.
    assert any("ps.zzzitest.two" in w for w in stats.warnings), (
        f"a same-sync target with the wrong label must still warn; got: {stats.warnings}"
    )
    # And the edge genuinely does not exist (the warning is truthful, not noise).
    assert not await _edge_exists(neo4j_driver, _PS_ONE, "USES_KU", _PS_TWO), (
        "a wrong-label USES_KU edge must not be created"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
