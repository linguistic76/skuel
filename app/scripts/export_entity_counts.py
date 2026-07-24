#!/usr/bin/env python3
"""Export Neo4j per-label / per-relationship-type counts as JSON (pure Cypher).

Migration integrity check for the local → AuraDB move: run once against the
local instance, once against Aura, and compare. Pure Cypher — no APOC — so it
runs identically on both. Connection comes from the ambient env/settings
(``NEO4J_URI`` etc.), so pointing it at a different instance is just an env
change. The initial connect tolerates a paused/waking AuraDB Free instance
(same bounded backoff as bootstrap, ADR-080 H0).

The migration guide prescribes prune-then-export ordering (``./dev
telemetry-retention`` BEFORE the "before" export), so counts need no
exclusion logic — what you export is exactly what the dump carries.

JSON to stdout (status/report to stderr): ``labels``, ``relationships``,
``totals``, ``uri``, ``timestamp``.

Usage:
    uv run python scripts/export_entity_counts.py > before.json
    uv run python scripts/export_entity_counts.py --compare before.json

``--compare FILE`` diffs the live counts against a previous export and exits
1 on any mismatch (0 when identical).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

# App logging attaches a console handler to sys.stdout on first import
# (core/utils/logging.py — the right default for containers), which would
# interleave log lines into `> before.json`. Keep the JSON channel pure:
# reserve the real stdout for the payload, give the app's logging stderr.
_PAYLOAD_OUT = sys.stdout
sys.stdout = sys.stderr


class CountTotals(TypedDict):
    nodes: int
    relationships: int


class EntityCounts(TypedDict):
    """Shape of one export payload — also what --compare reads back."""

    uri: str
    timestamp: str
    labels: dict[str, int]
    relationships: dict[str, int]
    totals: CountTotals


async def collect_counts() -> EntityCounts:
    """Connect (retry-tolerant) and gather label/reltype counts plus totals."""
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection, connect_with_retry
    from core.constants import Neo4jConnectRetry

    connection = Neo4jConnection()
    print(f"Connecting to {connection.uri} ...", file=sys.stderr)
    await connect_with_retry(
        connection,
        max_attempts=Neo4jConnectRetry.MAX_ATTEMPTS,
        base_delay_seconds=Neo4jConnectRetry.BASE_DELAY_SECONDS,
        max_delay_seconds=Neo4jConnectRetry.MAX_DELAY_SECONDS,
    )
    try:

        async def query_pairs(query: str) -> dict[str, int]:
            records = await connection.execute_query(query)
            if records is None:
                raise RuntimeError(f"Count query failed (see log above): {query}")
            return {record[0]: record[1] for record in records}

        async def query_scalar(query: str) -> int:
            records = await connection.execute_query(query)
            if records is None or not records:
                raise RuntimeError(f"Count query failed (see log above): {query}")
            return int(records[0][0])

        # A multi-label node (:Entity:Task) counts once under EACH label —
        # deterministic on both sides of a migration, which is all a diff needs.
        labels = await query_pairs(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count ORDER BY label"
        )
        relationships = await query_pairs(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(*) AS count ORDER BY rel_type"
        )
        total_nodes = await query_scalar("MATCH (n) RETURN count(n)")
        total_relationships = await query_scalar("MATCH ()-[r]->() RETURN count(r)")
    finally:
        await connection.close()

    return EntityCounts(
        uri=str(connection.uri),
        timestamp=datetime.now(UTC).isoformat(),
        labels=labels,
        relationships=relationships,
        totals=CountTotals(nodes=total_nodes, relationships=total_relationships),
    )


def diff_counts(before: EntityCounts, live: EntityCounts) -> list[str]:
    """Return human-readable mismatch lines (empty = identical counts)."""
    mismatches: list[str] = []
    sections: list[tuple[str, dict[str, int], dict[str, int]]] = [
        ("labels", before["labels"], live["labels"]),
        ("relationships", before["relationships"], live["relationships"]),
    ]
    for section, before_section, live_section in sections:
        for name in sorted(set(before_section) | set(live_section)):
            before_count = before_section.get(name, 0)
            live_count = live_section.get(name, 0)
            if before_count != live_count:
                mismatches.append(f"{section}.{name}: before={before_count} live={live_count}")
    totals: list[tuple[str, int, int]] = [
        ("nodes", before["totals"]["nodes"], live["totals"]["nodes"]),
        ("relationships", before["totals"]["relationships"], live["totals"]["relationships"]),
    ]
    for total, before_total, live_total in totals:
        if before_total != live_total:
            mismatches.append(f"totals.{total}: before={before_total} live={live_total}")
    return mismatches


async def run(before: EntityCounts | None, compare_path: str | None) -> int:
    live = await collect_counts()
    print(json.dumps(live, indent=2), file=_PAYLOAD_OUT)

    if before is None:
        return 0

    mismatches = diff_counts(before, live)
    if mismatches:
        print(f"\nMISMATCH — {len(mismatches)} count(s) differ:", file=sys.stderr)
        for line in mismatches:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(
        f"\nMatch — {live['totals']['nodes']:,} nodes / "
        f"{live['totals']['relationships']:,} relationships identical to {compare_path}.",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Neo4j label/relationship counts as JSON (pure Cypher, "
        "no APOC). Honors ambient NEO4J_* env — run once local, once against Aura."
    )
    parser.add_argument(
        "--compare",
        metavar="BEFORE_JSON",
        default=None,
        help="diff live counts against a previous export; exit 1 on any mismatch",
    )
    args = parser.parse_args()

    before: EntityCounts | None = None
    if args.compare is not None:
        # boundary: JSON from a prior run of this same script — trusted shape.
        before = cast("EntityCounts", json.loads(Path(args.compare).read_text(encoding="utf-8")))

    sys.exit(asyncio.run(run(before, args.compare)))


if __name__ == "__main__":
    main()
