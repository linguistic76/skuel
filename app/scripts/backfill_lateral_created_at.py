#!/usr/bin/env python3
"""Remove the literal string ``"timestamp()"`` left on lateral relationship edges.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds.

``LateralRelationshipService.create_lateral_relationship`` set
``rel_metadata["created_at"] = "timestamp()"`` and passed the dict to
``SET r += $metadata`` — a query *parameter*. Neo4j never evaluates parameter
values as expressions, so the property landed as the literal 11-character string
rather than a time. Every lateral type created through that path is affected
(BLOCKS, PREREQUISITE_FOR, ALTERNATIVE_TO, COMPLEMENTARY_TO, …), and the
auto-created inverse edge reused the same dict, so inverses carry it too.

**The property is removed, not corrected.** The real creation time is not
recoverable — nothing else on the edge records it, and the endpoints' own
``created_at`` bounds it only from below by however long the pair sat unlinked.
Stamping "now" would turn an obviously-broken value into a plausible-looking
wrong one, which is worse: a reader can detect a missing key, but not a
fabricated date. Removal is also strictly safer than leaving it, because the
string is *actively harmful* to a reader — ``properties(r)`` is projected
wholesale into the JSON response of all 9 domains' lateral GET routes, so any
consumer that parses the field crashes on it today.

Edges written after the fix carry a real ISO timestamp and are never touched:
the match is on the exact literal, not on "looks wrong".

**The write is guarded by a census, not by trust in the WHERE clause.** A
mis-scoped ``REMOVE`` would silently strip ``created_at`` from every edge in the
graph and report success. So the run counts edges carrying *any* ``created_at``
before and after, and refuses to report success unless the drop equals exactly
the number of literals it set out to remove.

Usage:
    uv run scripts/backfill_lateral_created_at.py              # census only (default)
    uv run scripts/backfill_lateral_created_at.py --confirm    # remove the literals
"""

from __future__ import annotations

import argparse
import asyncio
import sys

# The exact defect value. Matching the literal — rather than "any string that
# fails to parse as a date" — is what keeps a legitimately-stamped edge safe.
LITERAL = "timestamp()"

_COUNT_LITERAL_BY_TYPE = """
MATCH ()-[r]->()
WHERE r.created_at = $literal
RETURN type(r) AS rel_type, count(*) AS n
ORDER BY n DESC, rel_type
"""

# The census denominator: every edge carrying the property in ANY shape. The
# guard below is only meaningful against this total.
_COUNT_ALL_WITH_CREATED_AT = """
MATCH ()-[r]->()
WHERE r.created_at IS NOT NULL
RETURN count(*) AS n
"""

_REMOVE_LITERAL = """
MATCH ()-[r]->()
WHERE r.created_at = $literal
REMOVE r.created_at
RETURN count(*) AS n
"""

# Report-only. The defect was written through one service, but if the same
# literal reached a node property it would mean a second writer exists and this
# script is not the whole remedy.
_COUNT_LITERAL_ON_NODES = """
MATCH (n)
WHERE n.created_at = $literal
RETURN count(*) AS n
"""


async def _scalar(driver, query: str, **params: str) -> int:
    records, _, _ = await driver.execute_query(query, **params)
    return int(records[0]["n"]) if records else 0


async def _count_literal(driver) -> int:
    """Total edges carrying the literal, summed across relationship types."""
    records, _, _ = await driver.execute_query(_COUNT_LITERAL_BY_TYPE, literal=LITERAL)
    return sum(int(row["n"]) for row in records)


async def run_backfill(*, confirm: bool) -> int:
    """Census the literal-stamped edges and, with --confirm, strip the property."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()

        by_type, _, _ = await driver.execute_query(_COUNT_LITERAL_BY_TYPE, literal=LITERAL)
        literal_before = await _count_literal(driver)
        total_before = await _scalar(driver, _COUNT_ALL_WITH_CREATED_AT)
        on_nodes = await _scalar(driver, _COUNT_LITERAL_ON_NODES, literal=LITERAL)

        print(f"\nEdges carrying created_at in any shape : {total_before}")
        print(f'Edges carrying the literal "{LITERAL}"  : {literal_before}')
        if by_type:
            for row in by_type:
                print(f"    {row['rel_type']:<24} {row['n']}")
        if on_nodes:
            print(
                f"\n  NOTE: {on_nodes} NODE(s) also carry the literal. This script only "
                "touches relationships — a node-side writer would be a separate defect.",
                file=sys.stderr,
            )

        if literal_before == 0:
            print("\nNothing to backfill — no edge carries the literal.")
            return 0

        if not confirm:
            print("\nCensus only. Re-run with --confirm to remove the property.")
            return 0

        removed = await _scalar(driver, _REMOVE_LITERAL, literal=LITERAL)

        # Guard: prove the REMOVE hit exactly its intended set. A WHERE clause
        # that matched too widely would report a happy "removed N" above while
        # having stripped good stamps too.
        literal_after = await _count_literal(driver)
        total_after = await _scalar(driver, _COUNT_ALL_WITH_CREATED_AT)
        expected_total = total_before - literal_before

        print(f"\nRemoved the property from {removed} edge(s).")
        print(f"Edges still carrying the literal      : {literal_after} (expected 0)")
        print(f"Edges carrying created_at in any shape: {total_after} (expected {expected_total})")

        if literal_after != 0 or total_after != expected_total:
            print(
                "\nFAILED: the post-run census does not match. The REMOVE affected a "
                "different set than the one counted. Investigate before re-running.",
                file=sys.stderr,
            )
            return 1

        print("\nVerified: only the literal-stamped edges lost the property.")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually remove the property. Without it the run is a read-only "
            "census. Removal discards the (already meaningless) value, and the "
            "real creation time cannot be recovered afterwards."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_backfill(confirm=args.confirm)))


if __name__ == "__main__":
    main()
