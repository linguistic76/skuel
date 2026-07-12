"""One-time cleanup: delete provably-superseded uid-less vault UserEntry orphans.

Contract: /plans/uidless-vault-entry-identity-upsert.md

Before the path-keyed-upsert door fix, a knowledge note without ``uid:``
frontmatter minted a fresh random ``ue_`` uid on every re-ingest while the
ingestion tracker's ``path → uid`` row was simply overwritten — orphaning the
old node forever. Orphans hold ZERO chunks (retrieval is clean) but carry
``APPLIES_KNOWLEDGE`` grounding edges, so the ZPD 4th signal counts the same
note 3–4×.

**Positive orphan signal (Codex #616 P1).** An untracked entry is only DELETED
when its ``vault_file_path`` is *also* tracked — i.e. a live ``IngestionMetadata``
row points a DIFFERENT (current) uid at the same file. That proves the untracked
copy is a superseded duplicate. An untracked entry whose path is NOT tracked is
**ambiguous** — it could be a legitimate single-file-ingested entry (the
``/api/ingest/file`` door reads but never writes the tracker) or an orphan of a
now-deleted file — so it is REPORT-ONLY and never auto-deleted.

Criterion for each candidate (untracked, has ``vault_file_path``, no
``FULFILLS_EXERCISE`` — frozen copies never carry ``vault_file_path``):
  - **DELETE**  → its ``vault_file_path`` ∈ tracked file paths (superseded).
  - **REVIEW**  → its ``vault_file_path`` ∉ tracked file paths (ambiguous).

``metadata`` is persisted as a JSON string, so ``vault_file_path`` is a real
structured parse in Python (``json.loads`` → key lookup), not a Cypher
``CONTAINS`` heuristic. Live-graph split on 2026-07-12: 276 candidates →
241 DELETE, 35 REVIEW.

Dry-run by default: prints both categories (+ per-pipeline / edge-type
breakdown for the DELETE set) and deletes nothing. ``--apply`` deletes ONLY the
DELETE set (entry + content subtree, leaf-first), after the dry-run has been
reviewed (destructive-migration sign-off, per the contract).

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
    live_ue_paths: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split uid-less vault UserEntry candidates into (deletable, ambiguous).

    A row is a *candidate* when ALL hold:
      - its ``metadata`` JSON parses to a mapping carrying a ``vault_file_path``
        key (structured parse, not a substring match);
      - its uid is NOT in ``tracked_uids`` (no live ``IngestionMetadata`` row);
      - it has no outgoing ``FULFILLS_EXERCISE`` edge (``has_fulfills`` False).

    A candidate is **deletable** only with the positive orphan signal (Codex
    #616 P1): its ``vault_file_path`` ∈ ``live_ue_paths`` — the file is tracked
    to a **live** ``:UserEntry`` with a different (current) uid, so this untracked
    copy is provably superseded. ``live_ue_paths`` is deliberately restricted to
    tracker rows whose ``entity_uid`` still resolves to a live UserEntry (Codex
    #616 P1 round 2): a stale row, a row pointing at a deleted node, or one
    pointing at a different entity type / edge for the same file is NOT a
    supersession signal. Otherwise the candidate is **ambiguous** (a possible
    legitimate single-file ingest or an orphan of a deleted file) and returned
    separately for report-only review — never auto-deleted.

    Each input row must carry ``uid``, ``metadata`` (JSON string or None),
    ``pipeline``, and ``has_fulfills`` (bool). Returns ``(deletable, ambiguous)``
    with the resolved ``vault_file_path`` attached to each row.
    """
    deletable: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
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
        candidate = {**row, "vault_file_path": parsed["vault_file_path"]}
        if parsed["vault_file_path"] in live_ue_paths:
            deletable.append(candidate)
        else:
            ambiguous.append(candidate)
    return deletable, ambiguous


async def _fetch_tracked(driver: Any) -> tuple[set[str], set[str]]:
    """Return ``(tracked_uids, live_ue_paths)`` from IngestionMetadata.

    ``tracked_uids`` — every tracked ``entity_uid`` (used to exclude a candidate
    that is itself the live tracked entry). ``live_ue_paths`` — only the file
    paths whose tracker row points at a **live** ``:UserEntry`` (a genuine
    supersession signal; a stale row / deleted node / other entity type does not
    qualify, Codex #616 P1).
    """
    result = await driver.execute_query(
        """
        MATCH (im:IngestionMetadata)
        OPTIONAL MATCH (u:UserEntry {uid: im.entity_uid})
        RETURN im.entity_uid AS entity_uid, im.file_path AS file_path,
               u IS NOT NULL AS is_live_ue
        """
    )
    uids: set[str] = set()
    live_ue_paths: set[str] = set()
    for r in result.records:
        if r["entity_uid"] is not None:
            uids.add(str(r["entity_uid"]))
        if r["is_live_ue"] and r["file_path"] is not None:
            live_ue_paths.add(str(r["file_path"]))
    return uids, live_ue_paths


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


async def _fetch_content_subtree_count(driver: Any, uids: list[str]) -> int:
    """Count :Content/:ContentChunk/:ContentMetadata nodes hanging off the orphans.

    The orphans hold 0 chunks today (retrieval is clean), but a blind
    ``DETACH DELETE`` of only the entry node would orphan any subtree in the
    vector index — the report surfaces the real count so the migration is honest.
    """
    if not uids:
        return 0
    result = await driver.execute_query(
        """
        MATCH (u:UserEntry)-[:HAS_CONTENT]->(content:Content)
        WHERE u.uid IN $uids
        OPTIONAL MATCH (content)-[:HAS_CHUNK]->(chunk:ContentChunk)
        OPTIONAL MATCH (content)-[:HAS_METADATA]->(meta:ContentMetadata)
        RETURN count(DISTINCT content) + count(DISTINCT chunk) + count(DISTINCT meta) AS n
        """,
        uids=uids,
    )
    return int(result.records[0]["n"]) if result.records else 0


async def _delete_orphans(driver: Any, uids: list[str]) -> tuple[int, int]:
    """Delete the orphans AND their content subtree, leaf-first.

    Mirrors ``Neo4jContentAdapter.delete_content_subtree`` /
    ``IngestionBackend.delete_entities_with_metadata``: deleting the entry alone
    would leave :Content/:ContentChunk orphaned in the vector index and the
    chunk-regeneration scans. The subtree is counted up front (single aggregate
    row, no per-entry grouping — Codex #616 P2) so the ``[APPLIED]`` audit total
    is exact regardless of per-entry subtree size; the delete then runs
    leaf-first (chunk/meta → content → entry) mirroring the adapter's proven
    pattern. Returns ``(entries_deleted, subtree_nodes_deleted)``.
    """
    subtree = await _fetch_content_subtree_count(driver, uids)
    result = await driver.execute_query(
        """
        MATCH (u:UserEntry)
        WHERE u.uid IN $uids
        OPTIONAL MATCH (u)-[:HAS_CONTENT]->(content:Content)
        OPTIONAL MATCH (content)-[:HAS_CHUNK]->(chunk:ContentChunk)
        OPTIONAL MATCH (content)-[:HAS_METADATA]->(meta:ContentMetadata)
        DETACH DELETE chunk, meta
        WITH DISTINCT u, content
        DETACH DELETE content
        WITH DISTINCT u
        DETACH DELETE u
        RETURN count(u) AS deleted
        """,
        uids=uids,
    )
    deleted = int(result.records[0]["deleted"]) if result.records else 0
    return deleted, subtree


def _print_report(
    deletable: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    edge_breakdown: Counter[str],
    subtree_nodes: int,
) -> None:
    print("\n" + "=" * 72)
    print(f"DELETE — provably-superseded orphans (path tracked to a live entry): {len(deletable)}")
    print("=" * 72)

    by_pipeline: Counter[str] = Counter(str(o.get("pipeline")) for o in deletable)
    print("Per-pipeline counts:")
    for pipeline, count in sorted(by_pipeline.items()):
        print(f"  {pipeline:<24} {count}")

    total_edges = sum(edge_breakdown.values())
    print(f"\nEdge-type breakdown ({total_edges} edges total):")
    for rel_type, count in sorted(edge_breakdown.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {rel_type:<24} {count}")
    print(f"\nContent subtree nodes (:Content/:ContentChunk/:ContentMetadata): {subtree_nodes}")

    print("\n" + "=" * 72)
    print(f"REVIEW — ambiguous, NOT auto-deleted (path not tracked): {len(ambiguous)}")
    print("=" * 72)
    print("Possible legitimate single-file ingests OR orphans of deleted files —")
    print("inspect before deciding. These are left untouched by --apply.")
    for o in sorted(ambiguous, key=lambda r: str(r.get("vault_file_path"))):
        print(f"  {o['uid']}  {o.get('vault_file_path')}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="DETACH DELETE the provably-superseded orphans (DELETE set only; "
        "REVIEW set is never touched). Run the dry-run and get sign-off first.",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = await conn.connect()
    try:
        tracked_uids, live_ue_paths = await _fetch_tracked(driver)
        user_entry_rows = await _fetch_user_entry_rows(driver)
        deletable, ambiguous = select_orphans(user_entry_rows, tracked_uids, live_ue_paths)
        uids = [str(o["uid"]) for o in deletable]
        edge_breakdown = await _fetch_edge_breakdown(driver, uids)
        subtree_nodes = await _fetch_content_subtree_count(driver, uids)

        _print_report(deletable, ambiguous, edge_breakdown, subtree_nodes)

        if not deletable:
            print("\nNothing to delete — no provably-superseded orphans found.")
            return 0

        if not args.apply:
            print(
                "\n[DRY-RUN] No changes made. Re-run with --apply to DETACH DELETE the DELETE set."
            )
            return 0

        deleted, subtree_deleted = await _delete_orphans(driver, uids)
        print(
            f"\n[APPLIED] DETACH DELETEd {deleted} superseded orphan UserEntry node(s) "
            f"+ {subtree_deleted} content subtree node(s). REVIEW set untouched."
        )
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
