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
before and after, and requires the drop to equal exactly the number of literals
it set out to remove.

**Census, removal and verification share ONE transaction — for atomicity, not
isolation.** What that buys is precise: a guard that does not hold raises, and
the ``REMOVE`` rolls back with it, so the graph is never left half-migrated and
the check is a precondition for committing rather than a report filed over an
irreversible write.

What it does **not** buy is a stable read view. Neo4j's default isolation is
read-committed, so the before and after censuses do not observe one snapshot:
an unrelated writer committing a ``created_at`` change between them can still
skew the totals — tripping a false failure (safe: it rolls back) or offsetting
a real discrepancy (not safe: a bad removal could pass). The comparison is
global, so it is only sound when nothing else is writing.

**Therefore: run this against a quiet graph.** That is an operational
requirement, not a guarantee this script can make for itself. It is a one-shot
admin migration, so a write-free window is a reasonable thing to ask for — but
it has to be asked for out loud rather than implied by a guard that looks
race-proof and is not.

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


class GuardFailedError(RuntimeError):
    """The post-removal census disagreed with the pre-removal one.

    Raised *inside* the write transaction so the driver rolls the REMOVE back —
    the guard is a precondition for committing, not a report filed after an
    irreversible write.

    A concurrent writer can also cause this without anything being wrong, since
    the census totals are global and Neo4j is read-committed. That direction is
    safe (nothing is removed), and re-running against a quiet graph resolves it.
    """


async def _scalar(driver, query: str, **params: str) -> int:
    records, _, _ = await driver.execute_query(query, **params)
    return int(records[0]["n"]) if records else 0


async def _count_literal(driver) -> int:
    """Total edges carrying the literal, summed across relationship types."""
    records, _, _ = await driver.execute_query(_COUNT_LITERAL_BY_TYPE, literal=LITERAL)
    return sum(int(row["n"]) for row in records)


def guard_holds(
    *, total_before: int, literal_before: int, total_after: int, literal_after: int
) -> bool:
    """True when the REMOVE hit exactly the set that was counted.

    Split out from the transaction so the decision itself is testable without
    having to manufacture a concurrent writer.
    """
    return literal_after == 0 and total_after == total_before - literal_before


async def _tx_scalar(tx, query: str, **params: str) -> int:
    result = await tx.run(query, **params)
    record = await result.single()
    return int(record["n"]) if record else 0


async def _tx_count_literal(tx) -> int:
    result = await tx.run(_COUNT_LITERAL_BY_TYPE, literal=LITERAL)
    # Async comprehension, not a bare generator: sum() cannot consume the latter.
    return sum([int(row["n"]) async for row in result])


async def _remove_literals_guarded(tx) -> dict[str, int]:
    """Census, remove, and re-census inside ONE transaction.

    The transaction provides **atomicity, not isolation**: raising here rolls the
    REMOVE back, so a failed guard leaves the graph untouched. It does not give
    these reads a common snapshot — Neo4j is read-committed, so a concurrent
    writer changing some other edge's ``created_at`` mid-run can still skew the
    totals in either direction. Run against a quiet graph; see the module
    docstring.
    """
    total_before = await _tx_scalar(tx, _COUNT_ALL_WITH_CREATED_AT)
    literal_before = await _tx_count_literal(tx)

    removed = await _tx_scalar(tx, _REMOVE_LITERAL, literal=LITERAL)

    literal_after = await _tx_count_literal(tx)
    total_after = await _tx_scalar(tx, _COUNT_ALL_WITH_CREATED_AT)

    if not guard_holds(
        total_before=total_before,
        literal_before=literal_before,
        total_after=total_after,
        literal_after=literal_after,
    ):
        raise GuardFailedError(
            f"census mismatch — rolled back. before={total_before} "
            f"literal={literal_before} after={total_after} "
            f"(expected {total_before - literal_before}) literal_after={literal_after}"
        )

    return {
        "removed": removed,
        "total_before": total_before,
        "literal_before": literal_before,
        "total_after": total_after,
    }


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

        # The counts above are a preview only. The numbers the guard acts on are
        # re-read inside the write transaction, so nothing here can go stale
        # between the census and the removal.
        async with driver.session() as session:
            try:
                outcome = await session.execute_write(_remove_literals_guarded)
            except GuardFailedError as failure:
                print(
                    f"\nFAILED: {failure}\nThe REMOVE affected a different set than the "
                    "one counted, so the transaction was rolled back and the graph is "
                    "unchanged. Investigate before re-running.",
                    file=sys.stderr,
                )
                return 1

        print(f"\nRemoved the property from {outcome['removed']} edge(s).")
        print(
            f"Edges carrying created_at in any shape: {outcome['total_after']} "
            f"(was {outcome['total_before']}, less {outcome['literal_before']} literals)"
        )
        print("\nVerified in-transaction: only the literal-stamped edges lost the property.")
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
