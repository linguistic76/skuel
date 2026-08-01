#!/usr/bin/env python3
"""Converge EntryReport visibility on student ``OWNS``; retire ``ASSESSMENT_OF``.

A ONE-SHOT migration (feedback-loop UX arc, choice C1 — see
``docs/roadmap/feedback-loop-ux-arc.md``) — no background loop, so the CORE
"no background workers" guarantee holds.

``ASSESSMENT_OF`` was one of two parallel edges meaning "this report is about
this student": the teacher-review path wrote ``(student)-[:OWNS]->(report)``
(via ``create_report_node``), while the assessment path wrote
``(report)-[:ASSESSMENT_OF]->(student)`` *in addition to* the OWNS edge the
generic ``create()`` derives from ``user_uid``. The ``/entry-reports`` listing
read only ``ASSESSMENT_OF``, so teacher-review reports were invisible to the
student. Ownership is now THE visibility anchor and the code no longer writes
or reads ``ASSESSMENT_OF``, so any surviving edge is unreachable data.

For every ``(report)-[:ASSESSMENT_OF]->(u:User)`` this script MERGEs the
missing ``(u)-[:OWNS]->(report)`` first, then deletes ALL ``ASSESSMENT_OF``
edges — in that order, inside ONE transaction, so an edge is never deleted
before the ownership anchor that replaces it exists. ``MERGE`` makes the
backfill idempotent: reports that already carry OWNS (the common case — both
write paths create it) gain nothing and lose nothing.

**Abort, don't guess:** an ``ASSESSMENT_OF`` edge whose target is not a
``:User`` has no derivable owner. If any exist the run stops before writing
and surfaces them (the arc's C1 guard) — forcing the convergence would delete
the only record of who the report was for.

The delete is self-scoping — ``MATCH ()-[a:ASSESSMENT_OF]->()`` can touch no
other relationship type — so no census guard beyond the in-transaction
verification is needed. Neo4j is read-committed, so as with any global
migration: run against a quiet graph.

Also reported (read-only, both modes): reports with NO owner and no
``ASSESSMENT_OF`` to derive one from. This script cannot repair those — they
indicate a third write path and need investigation, not a forced edge.

Usage:
    uv run scripts/backfill_entry_report_owns.py              # census only (default)
    uv run scripts/backfill_entry_report_owns.py --confirm    # backfill OWNS + delete edges
"""

from __future__ import annotations

import argparse
import asyncio
import sys

_COUNT_EDGES_BY_ENDPOINTS = """
MATCH (r)-[a:ASSESSMENT_OF]->(t)
RETURN labels(r) AS report_labels, labels(t) AS target_labels, count(*) AS n
ORDER BY n DESC
"""

# Edges whose OWNS anchor is missing — the set the MERGE will create.
_COUNT_OWNS_GAPS = """
MATCH (r)-[:ASSESSMENT_OF]->(u:User)
WHERE NOT (u)-[:OWNS]->(r)
RETURN count(*) AS n
"""

# The C1 guard: a target we cannot derive an owner from.
_COUNT_NON_USER_TARGETS = """
MATCH (r)-[:ASSESSMENT_OF]->(t)
WHERE NOT t:User
RETURN count(*) AS n
"""

# Report-only: ownerless reports this migration cannot repair.
_COUNT_ORPHAN_REPORTS = """
MATCH (r:Entity {entity_type: 'entry_report'})
WHERE NOT (:User)-[:OWNS]->(r)
  AND NOT (r)-[:ASSESSMENT_OF]->(:User)
RETURN count(*) AS n
"""

_BACKFILL_OWNS = """
MATCH (r)-[:ASSESSMENT_OF]->(u:User)
WHERE NOT (u)-[:OWNS]->(r)
MERGE (u)-[:OWNS]->(r)
RETURN count(*) AS n
"""

_DELETE_EDGES = """
MATCH ()-[a:ASSESSMENT_OF]->()
DELETE a
RETURN count(*) AS n
"""


class GuardFailedError(RuntimeError):
    """In-transaction verification failed; the migration rolled back.

    Raised *inside* the write transaction so the driver rolls back both the
    MERGEs and the DELETEs — the graph is never left half-migrated.
    """


async def _tx_scalar(tx, query: str) -> int:
    result = await tx.run(query)
    record = await result.single()
    return int(record["n"]) if record else 0


async def _scalar(driver, query: str) -> int:
    records, _, _ = await driver.execute_query(query)
    return int(records[0]["n"]) if records else 0


async def _migrate_guarded(tx) -> dict[str, int]:
    """Backfill OWNS, verify zero gaps remain, then delete the edges.

    Order is the invariant: no ASSESSMENT_OF edge is deleted until every
    User-targeted edge has its OWNS anchor in place, and a non-User target
    aborts the whole transaction (C1 guard).
    """
    non_user = await _tx_scalar(tx, _COUNT_NON_USER_TARGETS)
    if non_user:
        raise GuardFailedError(
            f"{non_user} ASSESSMENT_OF edge(s) target a non-User node — no owner "
            "is derivable. Investigate before re-running; nothing was changed."
        )

    owns_created = await _tx_scalar(tx, _BACKFILL_OWNS)

    gaps_after = await _tx_scalar(tx, _COUNT_OWNS_GAPS)
    if gaps_after:
        raise GuardFailedError(
            f"{gaps_after} report(s) still lack OWNS after the backfill — rolled back."
        )

    deleted = await _tx_scalar(tx, _DELETE_EDGES)
    return {"owns_created": owns_created, "deleted": deleted}


async def run_migration(*, confirm: bool) -> int:
    """Census the ASSESSMENT_OF edges and, with --confirm, converge on OWNS."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()

        by_endpoints, _, _ = await driver.execute_query(_COUNT_EDGES_BY_ENDPOINTS)
        edge_total = sum(int(row["n"]) for row in by_endpoints)
        owns_gaps = await _scalar(driver, _COUNT_OWNS_GAPS)
        non_user = await _scalar(driver, _COUNT_NON_USER_TARGETS)
        orphans = await _scalar(driver, _COUNT_ORPHAN_REPORTS)

        print(f"\nASSESSMENT_OF edges                    : {edge_total}")
        for row in by_endpoints:
            labels = ":".join(row["report_labels"]) or "(no label)"
            targets = ":".join(row["target_labels"]) or "(no label)"
            print(f"    ({labels}) -> ({targets})  {row['n']}")
        print(f"Edges whose report lacks student OWNS  : {owns_gaps}")
        if non_user:
            print(
                f"\n  STOP: {non_user} edge(s) target a non-User node — no owner is "
                "derivable. The migration refuses to run (C1 guard).",
                file=sys.stderr,
            )
        if orphans:
            print(
                f"\n  NOTE: {orphans} entry_report node(s) have NO owner and no "
                "ASSESSMENT_OF to derive one from. This script cannot repair them — "
                "they indicate a separate write path; investigate independently.",
                file=sys.stderr,
            )

        if edge_total == 0:
            print("\nNothing to migrate — no ASSESSMENT_OF edge exists.")
            return 0

        if not confirm:
            print("\nCensus only. Re-run with --confirm to backfill OWNS and delete the edges.")
            return 0

        # The counts above are a preview; the guard re-reads inside the write
        # transaction, so nothing can go stale between census and migration.
        async with driver.session() as session:
            try:
                outcome = await session.execute_write(_migrate_guarded)
            except GuardFailedError as failure:
                print(f"\nFAILED: {failure}", file=sys.stderr)
                return 1

        print(f"\nCreated {outcome['owns_created']} OWNS edge(s).")
        print(f"Deleted {outcome['deleted']} ASSESSMENT_OF edge(s).")
        print("Verified in-transaction: every affected report is student-owned.")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write: MERGE the missing OWNS edges, then delete all "
            "ASSESSMENT_OF edges. Without it the run is a read-only census."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_migration(confirm=args.confirm)))


if __name__ == "__main__":
    main()
