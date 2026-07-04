"""
Integration: MOC edge pass against real Neo4j (``moc: true`` → ORGANIZES).

Proves the whole arc through the batch door (``ingest_directory``, smart mode):

- One sync ingests a MOC file TOGETHER with its link targets and the edges
  land anyway (the end-of-sync pass runs after IngestionMetadata stamping,
  so same-sync targets resolve) — with ``order`` from document position.
- Unresolved links (never-ingested notes) are skipped without error.
- Second unchanged sync is a no-op (files skipped, edges untouched).
- Editing the MOC re-draws: a removed link's edge is DELETED, a link whose
  target file arrives in the same sync fills in.
- Deleting the MOC file propagates: entity + its ORGANIZES edges are gone.
- Content-vault posture: the SAME pass emits Arc E-style warnings for
  dangling targets when the governing vault is CONTENT.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from core.services.ingestion.config import SyncAllowlist
from core.services.ingestion.types import IncrementalStats
from core.services.vault.vault_descriptor import VaultDescriptor, VaultKind, VaultRegistry

_UID_PREFIX = "ku.test.mocpass"


def _ku_file(path: Path, slug: str, body: str = "plain body", moc: bool = False) -> None:
    moc_line = "moc: true\n" if moc else ""
    path.write_text(
        f"---\ntype: ku\nuid: ku:test:mocpass-{slug}\ntitle: MOC Pass {slug}\n"
        f"{moc_line}---\n{body}\n"
    )


async def _organized_targets(neo4j_driver, source_uid: str) -> list[tuple[str, int]]:
    """[(target_uid, order)] for the source's outgoing ORGANIZES edges, by order."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:Entity {uid: $uid})-[r:ORGANIZES]->(t:Entity)
            RETURN t.uid AS uid, r.order AS ord ORDER BY r.order
            """,
            {"uid": source_uid},
        )
        return [(record["uid"], record["ord"]) async for record in result]


@pytest_asyncio.fixture
async def moc_ingestion_service(neo4j_driver):
    """UnifiedIngestionService with tracker wired (smart mode)."""
    from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
    )
    yield service
    # Session-scoped container — remove this module's nodes + tracker rows.
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid STARTS WITH $p DETACH DELETE n", {"p": _UID_PREFIX}
        )
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid STARTS WITH $p DELETE s",
            {"p": _UID_PREFIX},
        )


@pytest.mark.integration
class TestMocEdgePass:
    async def test_full_moc_lifecycle(self, moc_ingestion_service, neo4j_driver, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        moc_uid = f"{_UID_PREFIX}-map"

        # --- Sync 1: MOC + its targets land in the SAME sync -----------------
        _ku_file(vault / "alpha.md", "alpha")
        _ku_file(vault / "beta.md", "beta")
        _ku_file(
            vault / "map.md",
            "map",
            body="[[alpha]]\n\n[beta link](beta.md)\n\n[[gamma never ingested]]\n",
            moc=True,
        )

        result = await moc_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result.is_ok, str(result)
        stats: IncrementalStats = result.value
        assert not stats.errors, f"sync 1 errors: {stats.errors}"

        # Edges with document-position order; the dangling link drew nothing
        # and raised nothing (personal posture — no registry wired).
        assert await _organized_targets(neo4j_driver, moc_uid) == [
            (f"{_UID_PREFIX}-alpha", 0),
            (f"{_UID_PREFIX}-beta", 1),
        ]
        assert stats.warnings == []

        # The moc flag flowed onto the node as an inert property.
        async with neo4j_driver.session() as session:
            res = await session.run("MATCH (n:Entity {uid: $uid}) RETURN n.moc", {"uid": moc_uid})
            record = await res.single()
            assert record["n.moc"] is True

        # --- Sync 2: unchanged — no-op ---------------------------------------
        result2 = await moc_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result2.is_ok
        stats2: IncrementalStats = result2.value
        assert stats2.files_ingested == 0
        assert stats2.files_skipped == 3
        assert await _organized_targets(neo4j_driver, moc_uid) == [
            (f"{_UID_PREFIX}-alpha", 0),
            (f"{_UID_PREFIX}-beta", 1),
        ]

        # --- Sync 3: edit — alpha link removed, gamma's file arrives ---------
        _ku_file(vault / "gamma never ingested.md", "gamma")
        _ku_file(
            vault / "map.md",
            "map",
            body="[beta link](beta.md)\n\n[[gamma never ingested]]\n",
            moc=True,
        )
        result3 = await moc_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result3.is_ok
        assert not result3.value.errors

        # Stale edge (alpha) deleted; beta reordered to 0; gamma resolved in
        # the same sync its target file was ingested (the fill-in ruling).
        assert await _organized_targets(neo4j_driver, moc_uid) == [
            (f"{_UID_PREFIX}-beta", 0),
            (f"{_UID_PREFIX}-gamma", 1),
        ]

        # --- Sync 4: delete the MOC file — deletion propagation --------------
        (vault / "map.md").unlink()
        result4 = await moc_ingestion_service.ingest_directory(vault, ingestion_mode="smart")
        assert result4.is_ok
        assert result4.value.entities_deleted >= 1

        async with neo4j_driver.session() as session:
            res = await session.run(
                "MATCH (n:Entity {uid: $uid}) RETURN count(n) AS c", {"uid": moc_uid}
            )
            record = await res.single()
            assert record["c"] == 0
            res = await session.run(
                "MATCH ()-[r:ORGANIZES]->(:Entity) WHERE r.order IS NOT NULL "
                "AND startNode(r).uid = $uid RETURN count(r) AS c",
                {"uid": moc_uid},
            )
            record = await res.single()
            assert record["c"] == 0

    async def test_content_vault_posture_warns_on_dangling(
        self, moc_ingestion_service, neo4j_driver, tmp_path: Path
    ):
        """The SAME pass, CONTENT posture: dangling MOC links get Arc E-style
        warnings in the sync stats (personal vaults stay silent)."""
        content_root = tmp_path / "0vault"
        content_root.mkdir()
        moc_ingestion_service.vault_registry = VaultRegistry(
            content=VaultDescriptor(
                kind=VaultKind.CONTENT,
                root=content_root,
                owner_uid="user_test_integration",  # type: ignore[arg-type]
                allowlist=SyncAllowlist(
                    governed_root=content_root, allowed_dirs=frozenset({content_root})
                ),
                bridge=_NullBridge(),  # type: ignore[arg-type]
                supports_task_round_trip=False,
            ),
            personal=None,
        )

        _ku_file(content_root / "known.md", "known")
        _ku_file(
            content_root / "cmap.md",
            "cmap",
            body="[[known]]\n\n[[phantom topic]]\n",
            moc=True,
        )

        result = await moc_ingestion_service.ingest_directory(content_root, ingestion_mode="smart")
        assert result.is_ok, str(result)
        stats: IncrementalStats = result.value
        assert not stats.errors, f"errors: {stats.errors}"

        assert await _organized_targets(neo4j_driver, f"{_UID_PREFIX}-cmap") == [
            (f"{_UID_PREFIX}-known", 0)
        ]
        assert any(
            "MOC link target '/phantom topic.md' does not resolve" in w for w in stats.warnings
        ), f"expected Arc E-style MOC warning, got: {stats.warnings}"


class _NullBridge:
    """Descriptor requires a bridge object; the content posture test never writes."""
