"""One-time cleanup: delete uid-less vault UserEntry orphans.

Contract: /plans/uidless-vault-entry-identity-upsert.md

Before the path-keyed-upsert door fix, a knowledge note without ``uid:``
frontmatter minted a fresh random ``ue_`` uid on every re-ingest while the
ingestion tracker's ``path → uid`` row was simply overwritten — orphaning the
old node forever. 276 such orphans accumulated (measured 2026-07-12): they
hold ZERO chunks (retrieval is clean today) but carry ~660 edges, including
380 of 502 ``APPLIES_KNOWLEDGE`` grounding edges (76%), so the ZPD 4th signal
counts the same note 3–4×. Deduped baseline ≈ 122 edges / 37 Kus.

Criterion (surgical, verified on the live graph): a ``:UserEntry`` whose
``metadata`` JSON carries a ``vault_file_path`` key AND whose uid is claimed
by NO ``IngestionMetadata`` row AND which has no outgoing ``FULFILLS_EXERCISE``
edge (belt-and-braces — frozen submission copies never carry
``vault_file_path``). Matched entries are ``DETACH DELETE``d.

``metadata`` is persisted as a JSON string, so the ``vault_file_path`` check is
a real structured parse in Python (``json.loads`` → key membership), not a
Cypher ``CONTAINS`` substring heuristic.

Dry-run by default: prints per-pipeline counts + the edge-type breakdown and
deletes nothing. ``--apply`` executes only after the dry-run has been reviewed
(destructive-migration sign-off, per the contract).

Usage:
    uv run python scripts/cleanup_untracked_vault_entries.py           # dry-run
    uv run python scripts/cleanup_untracked_vault_entries.py --apply   # execute
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))


def select_orphans(
    user_entry_rows: list[dict[str, Any]],
    tracked_uids: set[str],
) -> list[dict[str, Any]]:
    """Filter UserEntry rows to the uid-less vault orphans (pure — unit-tested).

    A row qualifies when ALL hold:
      - its ``metadata`` JSON parses to a mapping carrying a ``vault_file_path``
        key (structured parse, not a substring match);
      - its uid is NOT in ``tracked_uids`` (no live ``IngestionMetadata`` row);
      - it has no outgoing ``FULFILLS_EXERCISE`` edge (``has_fulfills`` False).

    Each input row must carry ``uid``, ``metadata`` (JSON string or None),
    ``pipeline``, and ``has_fulfills`` (bool). Returns the qualifying rows with
    the resolved ``vault_file_path`` attached for the report.
    """
    orphans: list[dict[str, Any]] = []
    for row in user_entry_rows:
        if row.get("has_fulfills"):
            continue
        if str(row["uid"]) in tracked_uids:
            continue
        # metadata is a JSON-string Neo4j property; anything else (None, a
        # non-string) can't carry a vault_file_path key. The isinstance guard
        # also lets us catch only JSONDecodeError below — no multi-exception
        # tuple (which this repo's ruff-format version mis-rewrites into
        # invalid `except A, B:`).
        raw = row.get("metadata")
        if not isinstance(raw, str):
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or "vault_file_path" not in parsed:
            continue
        orphans.append({**row, "vault_file_path": parsed["vault_file_path"]})
    return orphans


async def _fetch_tracked_uids(driver: Any) -> set[str]:
    result = await driver.execute_query(
        "MATCH (im:IngestionMetadata) RETURN im.entity_uid AS entity_uid"
    )
    return {str(r["entity_uid"]) for r in result.records if r["entity_uid"] is not None}


async def _fetch_user_entry_rows(driver: Any) -> list[dict[str, Any]]:
    # Deliberately does NOT return `content` — the metadata JSON, uid, pipeline,
    # and the turn-in flag are all the filter needs.
    result = await driver.execute_query(
        """
        MATCH (u:UserEntry)
        RETURN u.uid AS uid,
               u.metadata AS metadata,
               u.pipeline AS pipeline,
               EXISTS { (u)-[:FULFILLS_EXERCISE]->() } AS has_fulfills
        """
    )
    return [dict(r) for r in result.records]


async def _fetch_edge_breakdown(driver: Any, uids: list[str]) -> Counter[str]:
    """Count edges (both directions) touching the orphan set, by relationship type."""
    if not uids:
        return Counter()
    result = await driver.execute_query(
        """
        MATCH (u:UserEntry)-[r]-()
        WHERE u.uid IN $uids
        RETURN type(r) AS rel_type, count(r) AS cnt
        """,
        uids=uids,
    )
    return Counter({str(r["rel_type"]): int(r["cnt"]) for r in result.records})


async def _delete_orphans(driver: Any, uids: list[str]) -> int:
    result = await driver.execute_query(
        """
        MATCH (u:UserEntry)
        WHERE u.uid IN $uids
        DETACH DELETE u
        RETURN count(u) AS deleted
        """,
        uids=uids,
    )
    return int(result.records[0]["deleted"]) if result.records else 0


def _print_report(orphans: list[dict[str, Any]], edge_breakdown: Counter[str]) -> None:
    print(f"\nUntracked vault UserEntry orphans: {len(orphans)}\n")

    by_pipeline: Counter[str] = Counter(str(o.get("pipeline")) for o in orphans)
    print("Per-pipeline counts:")
    for pipeline, count in sorted(by_pipeline.items()):
        print(f"  {pipeline:<24} {count}")

    total_edges = sum(edge_breakdown.values())
    print(f"\nEdge-type breakdown ({total_edges} edges total):")
    for rel_type, count in sorted(edge_breakdown.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {rel_type:<24} {count}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="DETACH DELETE the matched orphans. Run the dry-run and get sign-off first.",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = await conn.connect()
    try:
        tracked_uids = await _fetch_tracked_uids(driver)
        user_entry_rows = await _fetch_user_entry_rows(driver)
        orphans = select_orphans(user_entry_rows, tracked_uids)
        uids = [str(o["uid"]) for o in orphans]
        edge_breakdown = await _fetch_edge_breakdown(driver, uids)

        _print_report(orphans, edge_breakdown)

        if not orphans:
            print("\nNothing to clean up — graph is already free of vault orphans.")
            return 0

        if not args.apply:
            print("\n[DRY-RUN] No changes made. Re-run with --apply to DETACH DELETE.")
            return 0

        deleted = await _delete_orphans(driver, uids)
        print(f"\n[APPLIED] DETACH DELETEd {deleted} orphan UserEntry node(s).")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
