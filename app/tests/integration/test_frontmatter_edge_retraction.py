"""
Integration: a target dropped from a registered frontmatter field loses its edge.

Drives the production path against a real Neo4j: both ingest doors, a vault
whose PathStep declares ``uses_kus: [a, b]``, then declares ``[a]``. The edge
to ``b`` must be gone after the next sync while the edge to ``a`` remains —
the per-file authored-edge fingerprint on the file's ``IngestionMetadata`` row
is diffed against the new declaration and exactly the dropped edges are deleted.

The interaction cases the fix must hold:

- (a) ``--force`` on an unchanged file produces an empty diff — nothing deleted.
- (b) a pure rename carries the fingerprint to the new path's row.
- (c) a target in BOTH ``organizes:`` frontmatter and MOC body links, dropped
      from the frontmatter only, is still present after the sync (the MOC pass
      re-MERGEs it inside the same sync).
- (d) an edge of a registered type the file never authored survives.
- (e) an ``order_property`` field (LP ``connections.contains_steps``): the
      dropped edge goes, survivors' ``sequence`` refreshes.
- (f) Edge YAML rows (``edge:`` identity) are untouched.
- an ``incoming`` field drop retracts the incoming edge, not an outgoing one.
- the single-file door retracts too and stamps its own tracker row.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.ingestion_backend import IngestionBackend
from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.services.ingestion.types import IncrementalStats

_MARK = "zzzretract"
_KU_A = f"ku.{_MARK}.a"
_KU_B = f"ku.{_MARK}.b"
_KU_C = f"ku.{_MARK}.c"
_PS_X = f"ps.{_MARK}.x"
_PS_ONE = f"ps.{_MARK}.one"
_PS_TWO = f"ps.{_MARK}.two"
_PS_THREE = f"ps.{_MARK}.three"
_LP_PATH = f"lp.{_MARK}.path"


def _ku_file(vault: Path, name: str, uid: str) -> Path:
    path = vault / f"{name}.md"
    path.write_text(f"---\ntype: ku\nuid: {uid}\ntitle: Retract {name}\n---\nBody {name}.\n")
    return path


def _ps_file(
    vault: Path,
    name: str,
    uid: str,
    *,
    uses_kus: list[str] | None = None,
    organizes: list[str] | None = None,
    learning_path_uids: list[str] | None = None,
    moc: bool = False,
    body: str = "Body.",
) -> Path:
    lines = ["type: ps", f"uid: {uid}", f"title: Retract {name}"]
    if moc:
        lines.append("moc: true")
    for field, values in (
        ("uses_kus", uses_kus),
        ("organizes", organizes),
        ("learning_path_uids", learning_path_uids),
    ):
        if values is not None:
            lines.append(f"{field}:")
            lines.extend(f"  - {value}" for value in values)
    path = vault / f"{name}.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body + "\n")
    return path


def _lp_file(vault: Path, name: str, uid: str, steps: list[str]) -> Path:
    lines = [
        "type: lp",
        f"uid: {uid}",
        f"title: Retract {name}",
        "connections:",
        "  contains_steps:",
    ]
    lines.extend(f"    - {step}" for step in steps)
    path = vault / f"{name}.md"
    path.write_text("---\n" + "\n".join(lines) + "\n---\nBody.\n")
    return path


async def _edge_exists(neo4j_driver, from_uid: str, rel: str, to_uid: str) -> bool:
    async with neo4j_driver.session() as session:
        res = await session.run(
            f"MATCH (a {{uid: $f}})-[r:{rel}]->(b {{uid: $t}}) RETURN count(r) AS c",
            {"f": from_uid, "t": to_uid},
        )
        record = await res.single()
        return bool(record and record["c"] > 0)


async def _edge_property(neo4j_driver, from_uid: str, rel: str, to_uid: str, prop: str) -> Any:
    async with neo4j_driver.session() as session:
        res = await session.run(
            f"MATCH (a {{uid: $f}})-[r:{rel}]->(b {{uid: $t}}) RETURN r[$p] AS v",
            {"f": from_uid, "t": to_uid, "p": prop},
        )
        record = await res.single()
        return record["v"] if record else None


async def _tracker_rows(neo4j_driver, entity_uid: str) -> list[dict[str, Any]]:
    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (s:IngestionMetadata {entity_uid: $uid}) "
            "RETURN s.file_path AS file_path, s.authored_edges AS authored_edges",
            {"uid": entity_uid},
        )
        return [dict(record) async for record in res]


async def _sync(service, vault: Path, **kwargs: Any) -> IncrementalStats:
    result = await service.ingest_directory(vault, ingestion_mode="smart", **kwargs)
    assert result.is_ok, f"sync failed: {result}"
    stats = cast("IncrementalStats", result.value)
    assert not stats.errors, f"sync errors: {stats.errors}"
    return stats


@pytest_asyncio.fixture
async def retraction_service(neo4j_driver):
    """UnifiedIngestionService with the tracker wired (smart mode, both doors)."""
    executor = Neo4jQueryExecutor(neo4j_driver)
    service = make_unified_ingestion_service(
        driver=neo4j_driver,
        ingestion_backend=IngestionBackend(executor=executor),
    )
    yield service
    # Session-scoped container — remove this module's nodes + tracker rows
    # (entity rows by uid, Edge YAML rows by the uids inside their identity).
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity) WHERE n.uid CONTAINS $mark DETACH DELETE n", {"mark": _MARK}
        )
        await session.run(
            "MATCH (s:IngestionMetadata) WHERE s.entity_uid CONTAINS $mark DELETE s",
            {"mark": _MARK},
        )


@pytest.mark.integration
class TestFrontmatterEdgeRetraction:
    async def test_dropped_uses_kus_target_loses_its_edge_on_next_sync(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])

        await _sync(retraction_service, vault)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)

        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A])
        await _sync(retraction_service, vault)

        assert not await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B), (
            "a target dropped from uses_kus must lose its edge on the next sync"
        )
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A), (
            "the target still declared must keep its edge"
        )

    async def test_force_on_unchanged_file_deletes_nothing(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(a) force re-processes the file; the diff is empty, both edges stay."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])
        await _sync(retraction_service, vault)

        stats = await _sync(retraction_service, vault, force=True)
        assert stats.files_ingested == 3

        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        rows = await _tracker_rows(neo4j_driver, _PS_X)
        assert len(rows) == 1
        assert sorted(rows[0]["authored_edges"]) == [
            f"USES_KU|outgoing|{_KU_A}",
            f"USES_KU|outgoing|{_KU_B}",
        ]

    async def test_rename_carries_fingerprint_then_drop_retracts(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(b) a pure rename re-keys the row with its fingerprint; the edges
        survive the rename and a later drop at the NEW path still retracts."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        old = _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])
        await _sync(retraction_service, vault)

        new = vault / "renamed x.md"
        old.rename(new)
        stats = await _sync(retraction_service, vault)
        assert stats.entities_deleted == 0
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        rows = await _tracker_rows(neo4j_driver, _PS_X)
        assert [row["file_path"] for row in rows] == [str(new.resolve())]
        assert sorted(rows[0]["authored_edges"]) == [
            f"USES_KU|outgoing|{_KU_A}",
            f"USES_KU|outgoing|{_KU_B}",
        ]

        _ps_file(vault, "renamed x", _PS_X, uses_kus=[_KU_A])
        await _sync(retraction_service, vault)
        assert not await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)

    async def test_target_in_frontmatter_and_moc_body_survives_frontmatter_drop(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(c) dropped from ``organizes:`` but still body-linked: the retraction
        deletes the frontmatter edge, the end-of-sync MOC pass re-MERGEs it —
        the final state is present."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        _ps_file(vault, "x", _PS_X, organizes=[_KU_A, _KU_B], moc=True, body="[[a]]\n")
        await _sync(retraction_service, vault)
        assert await _edge_exists(neo4j_driver, _PS_X, "ORGANIZES", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "ORGANIZES", _KU_B)

        _ps_file(vault, "x", _PS_X, organizes=[], moc=True, body="[[a]]\n")
        await _sync(retraction_service, vault)

        assert await _edge_exists(neo4j_driver, _PS_X, "ORGANIZES", _KU_A), (
            "still body-linked — the MOC pass restores the edge within the sync"
        )
        assert await _edge_property(neo4j_driver, _PS_X, "ORGANIZES", _KU_A, "order") == 0
        assert not await _edge_exists(neo4j_driver, _PS_X, "ORGANIZES", _KU_B), (
            "dropped from frontmatter and not body-linked — gone"
        )

    async def test_edge_the_file_never_authored_survives(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(d) an app-door edge of a registered type is not the file's to retract."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        _ku_file(vault, "c", _KU_C)
        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])
        await _sync(retraction_service, vault)

        # Written by something other than the file (an app door) — same type.
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (x:Entity {uid: $x}), (c:Entity {uid: $c}) MERGE (x)-[:USES_KU]->(c)",
                {"x": _PS_X, "c": _KU_C},
            )

        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A])
        await _sync(retraction_service, vault)

        assert not await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_C), (
            "an edge the file never authored must survive its retraction"
        )

    async def test_ordered_field_drop_and_reorder(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(e) LP ``contains_steps``: the dropped step's HAS_STEP goes, the
        survivors' ``sequence`` refreshes from the new list position."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ps_file(vault, "one", _PS_ONE)
        _ps_file(vault, "two", _PS_TWO)
        _ps_file(vault, "three", _PS_THREE)
        _lp_file(vault, "path", _LP_PATH, [_PS_ONE, _PS_TWO, _PS_THREE])
        await _sync(retraction_service, vault)
        assert await _edge_property(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_TWO, "sequence") == 1

        _lp_file(vault, "path", _LP_PATH, [_PS_THREE, _PS_ONE])
        await _sync(retraction_service, vault)

        assert not await _edge_exists(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_TWO)
        assert await _edge_property(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_THREE, "sequence") == 0
        assert await _edge_property(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_ONE, "sequence") == 1

    async def test_edge_yaml_rows_are_untouched(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """(f) an Edge YAML's relationship and its ``edge:`` tracker row are not
        the fingerprint's business — they survive a neighbouring retraction."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _ku_file(vault, "a", _KU_A)
        _ku_file(vault, "b", _KU_B)
        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])
        (vault / "a_enables_b.md").write_text(
            f"---\ntype: Edge\nfrom: {_KU_A}\nto: {_KU_B}\nrelationship: ENABLES_KNOWLEDGE\n---\n"
        )
        await _sync(retraction_service, vault)
        assert await _edge_exists(neo4j_driver, _KU_A, "ENABLES_KNOWLEDGE", _KU_B)

        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A])
        await _sync(retraction_service, vault)

        assert await _edge_exists(neo4j_driver, _KU_A, "ENABLES_KNOWLEDGE", _KU_B)
        edge_rows = await _tracker_rows(neo4j_driver, f"edge:{_KU_A}|ENABLES_KNOWLEDGE|{_KU_B}")
        assert len(edge_rows) == 1
        assert not edge_rows[0]["authored_edges"]
        assert not await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)

    async def test_incoming_field_drop_retracts_the_incoming_edge(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """``learning_path_uids`` authors ``(ps)<-[:HAS_STEP]-(lp)``; dropping it
        deletes that incoming edge and nothing pointing the other way."""
        vault = tmp_path / "vault"
        vault.mkdir()
        _lp_file(vault, "path", _LP_PATH, [])
        _ps_file(vault, "x", _PS_X, learning_path_uids=[_LP_PATH])
        await _sync(retraction_service, vault)
        assert await _edge_exists(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_X)
        rows = await _tracker_rows(neo4j_driver, _PS_X)
        assert rows[0]["authored_edges"] == [f"HAS_STEP|incoming|{_LP_PATH}"]

        _ps_file(vault, "x", _PS_X, learning_path_uids=[])
        await _sync(retraction_service, vault)
        assert not await _edge_exists(neo4j_driver, _LP_PATH, "HAS_STEP", _PS_X)

    async def test_single_file_door_retracts_and_stamps_its_row(
        self, retraction_service, neo4j_driver, tmp_path: Path
    ):
        """``ingest_file`` (POST /api/ingest/file) shares the file's one identity:
        it stamps the tracker row and diffs against it on the next call."""
        vault = tmp_path / "vault"
        vault.mkdir()
        a = _ku_file(vault, "a", _KU_A)
        b = _ku_file(vault, "b", _KU_B)
        x = _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A, _KU_B])
        for path in (a, b, x):
            result = await retraction_service.ingest_file(path)
            assert result.is_ok, f"ingest_file failed: {result}"
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        rows = await _tracker_rows(neo4j_driver, _PS_X)
        assert [row["file_path"] for row in rows] == [str(x.resolve())]
        assert sorted(rows[0]["authored_edges"]) == [
            f"USES_KU|outgoing|{_KU_A}",
            f"USES_KU|outgoing|{_KU_B}",
        ]

        _ps_file(vault, "x", _PS_X, uses_kus=[_KU_A])
        result = await retraction_service.ingest_file(x)
        assert result.is_ok, f"ingest_file failed: {result}"

        assert not await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_B)
        assert await _edge_exists(neo4j_driver, _PS_X, "USES_KU", _KU_A)
        rows = await _tracker_rows(neo4j_driver, _PS_X)
        assert rows[0]["authored_edges"] == [f"USES_KU|outgoing|{_KU_A}"]

        # The batch door then sees the file as already ingested (one identity).
        stats = await _sync(retraction_service, vault)
        assert stats.files_ingested == 0
