#!/usr/bin/env python3
"""
One-off graph purge — pre-ADR-073 journal-session residue
==========================================================

ADR-073 made journals a zero-persistence workshop, but the nodes written
BEFORE that decision are still in the graph: legacy ``pipeline: journal``
sessions plus the old upload/transcription outputs (``llm_summary``,
``transcribe``, ``transcribe_and_structure``). Mike ruled (2026-07-11,
entry-enrichment arc): purge them — completing zero-persistence
retroactively. ``pipeline: none`` entries are deliberately NOT targeted.

Targets: ``:UserEntry`` nodes whose pipeline is one of the four legacy values
AND whose ``created_at`` predates the ADR-073 merge (2026-07-01) — the date
filter is a safety net so nothing written after the decision is swept.
Nodes matching the pipeline filter but carrying NO ``created_at`` are
reported and left alone (honest count, no silent skip).

Deletes via the backend's ``delete(uid, cascade=True)`` (DETACH DELETE), so
every edge (OWNS, sharing, TRANSFORMS, ...) goes with the node.

Safety: DRY-RUN by default — prints every target (uid / pipeline /
created_at / title) for an eyeball check and changes nothing. Pass
``--apply`` to execute.

Usage:
    uv run scripts/purge_legacy_journal_entries.py            # dry run
    uv run scripts/purge_legacy_journal_entries.py --apply    # execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

LEGACY_PIPELINES = (
    "journal",
    "llm_summary",
    "transcribe",
    "transcribe_and_structure",
)
DEFAULT_CUTOFF = "2026-07-01"

# ``created_at`` storage type is writer-decided (ISO strings and native
# datetimes both exist in the live graph — the temporal storage bug class),
# so the comparison normalizes through toString() → datetime() for both.
_SELECT_QUERY = """
MATCH (e:UserEntry)
WHERE e.pipeline IN $pipelines
  AND e.created_at IS NOT NULL
  AND datetime(toString(e.created_at)) < datetime($cutoff)
RETURN e.uid AS uid,
       e.title AS title,
       e.pipeline AS pipeline,
       toString(e.created_at) AS created_at
ORDER BY e.pipeline, e.created_at
"""

_UNDATED_QUERY = """
MATCH (e:UserEntry)
WHERE e.pipeline IN $pipelines
  AND e.created_at IS NULL
RETURN e.uid AS uid, e.title AS title, e.pipeline AS pipeline
"""


async def _fetch(driver: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await driver.execute_query(query, params)
    return [dict(record) for record in result.records]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Purge pre-ADR-073 legacy journal UserEntry nodes")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the deletions (default is dry-run: print the plan, change nothing)",
    )
    parser.add_argument(
        "--cutoff",
        default=DEFAULT_CUTOFF,
        help=f"Only nodes created strictly before this date are targeted (default {DEFAULT_CUTOFF})",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    conn = Neo4jConnection()
    driver = await conn.connect()
    try:
        params = {"pipelines": list(LEGACY_PIPELINES), "cutoff": args.cutoff}
        targets = await _fetch(driver, _SELECT_QUERY, params)
        undated = await _fetch(driver, _UNDATED_QUERY, {"pipelines": list(LEGACY_PIPELINES)})

        by_pipeline: dict[str, int] = {}
        for row in targets:
            by_pipeline[row["pipeline"]] = by_pipeline.get(row["pipeline"], 0) + 1

        print(f"Legacy journal purge — cutoff: created_at < {args.cutoff}")
        print(f"Pipelines targeted: {', '.join(LEGACY_PIPELINES)}\n")
        for row in targets:
            print(f"  {row['uid']}  [{row['pipeline']}]  {row['created_at']}  {row['title']!r}")
        print(f"\nTotal: {len(targets)} node(s) " + str(by_pipeline))

        if undated:
            print(
                f"\nNOT targeted ({len(undated)} node(s) match the pipeline filter but have "
                "no created_at — inspect manually):"
            )
            for row in undated:
                print(f"  {row['uid']}  [{row['pipeline']}]  {row['title']!r}")

        if not args.apply:
            print("\nDRY RUN — nothing deleted. Re-run with --apply to execute.")
            return 0

        if not targets:
            print("\nNothing to delete.")
            return 0

        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.user_entry.user_entry import UserEntry

        backend = UniversalNeo4jBackend[UserEntry](driver, NeoLabel.USER_ENTRY, UserEntry)
        deleted = 0
        failures: list[str] = []
        for row in targets:
            result = await backend.delete(str(row["uid"]), cascade=True)
            if result.is_ok and result.value:
                deleted += 1
            else:
                detail = str(result.expect_error()) if result.is_error else "not found"
                failures.append(f"{row['uid']}: {detail}")

        print(f"\nDeleted {deleted}/{len(targets)} node(s).")
        if failures:
            print("Failures:")
            for line in failures:
                print(f"  {line}")
            return 1
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
