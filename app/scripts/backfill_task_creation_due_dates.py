#!/usr/bin/env python3
"""Give every undated Task the due date the creation rule would have given it.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds.

The rule: a task created with neither ``due_date`` nor ``scheduled_date`` is due
the day it is created (``Task.with_creation_due_date``). The day lens and the
calendar place a task by exactly those two fields, so an undated task renders on
no day. Every creator applies the rule to new tasks — the service create
primitive, the template spawn, and the vault door's post-persist pass — and this
script applies it to whatever the graph already holds: tasks that predate the
rule, or that reached the graph past it (a failed post-persist write, an
out-of-band load).

**The written value is the rule, not an approximation of it.** Per undated node:
``due_date`` = the ``created_at`` calendar day, or the ``completion_date`` when
that is *earlier* — a historical ``✅`` line was lived on the day it was done,
not the day it was ingested (the same branch the model method takes). A task
completed on or after its creation day keeps the creation day: it was due then
and finished later. The expression is IMPORTED from the vault door's write
backend (``TASK_CREATION_DUE_DATE_CYPHER``), never retyped, so the live rule
and this backfill cannot drift.

**Storage shape matches the writers.** ``due_date`` round-trips through
``to_neo4j_node``/``from_neo4j_node`` as an ISO ``YYYY-MM-DD`` **string**; the
projection goes through ``toString()`` on both sources so an ISO string and a
native temporal ``created_at``/``completion_date`` flatten to that one shape.

Non-destructive and idempotent: only nodes with BOTH date fields NULL are
matched, so a date set by any real path is never overwritten, and the second run
finds nothing to fill. A node with no ``created_at`` at all is reported, not
guessed at.

Usage:
    uv run scripts/backfill_task_creation_due_dates.py             # census only (default)
    uv run scripts/backfill_task_creation_due_dates.py --confirm   # write the dates
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from adapters.persistence.neo4j.ingestion_write_backend import TASK_CREATION_DUE_DATE_CYPHER
from core.models.enums.neo_labels import NeoLabel

TASK_LABEL = NeoLabel.TASK.value

#: The two fields the day lens and the calendar place a task by. A node is
#: "undated" when BOTH are NULL — the exact predicate ``Task.with_creation_due_date``
#: fills on, so the backfill and the live rule cannot disagree on who qualifies.
DUE_FIELD = "due_date"
SCHEDULED_FIELD = "scheduled_date"

#: The rule as a Cypher expression over an undated node ``n`` — the vault door's
#: own, imported so the two cannot drift.
RULE_PROJECTION = TASK_CREATION_DUE_DATE_CYPHER

UNDATED = f"n.{DUE_FIELD} IS NULL AND n.{SCHEDULED_FIELD} IS NULL"

CENSUS_QUERY = f"""
MATCH (n:{TASK_LABEL})
RETURN count(*) AS tasks,
       count(CASE WHEN {UNDATED} AND n.created_at IS NOT NULL THEN 1 END) AS fillable,
       count(CASE WHEN {UNDATED} AND n.created_at IS NULL THEN 1 END) AS no_source
"""

#: One row per node the write would touch, with the value it would receive —
#: the census prints these so a --confirm is a decision over a visible list.
PREVIEW_QUERY = f"""
MATCH (n:{TASK_LABEL})
WHERE {UNDATED} AND n.created_at IS NOT NULL
RETURN n.uid AS uid, n.status AS status, n.title AS title,
       {RULE_PROJECTION} AS due_date
ORDER BY due_date, n.title
"""

BACKFILL_QUERY = f"""
MATCH (n:{TASK_LABEL})
WHERE {UNDATED} AND n.created_at IS NOT NULL
SET n.{DUE_FIELD} = {RULE_PROJECTION} // noqa: CYP003 - property name + expression over the node's own properties, not a value
RETURN count(*) AS n
"""


async def run_backfill(*, confirm: bool) -> int:
    """Census the undated tasks and, with --confirm, apply the creation rule to them."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()

        records, _, _ = await driver.execute_query(CENSUS_QUERY)
        row = records[0]
        fillable = int(row["fillable"])
        no_source = int(row["no_source"])
        print(
            f"\nTasks: {row['tasks']}   undated & fillable: {fillable}   no created_at: {no_source}"
        )
        if no_source:
            print(
                f"  NOTE: {no_source} undated Task(s) carry no created_at — left as they are; "
                "there is no day to derive.",
                file=sys.stderr,
            )

        if fillable == 0:
            print("\nNothing to backfill — every Task already carries a due or scheduled date.")
            return 0

        preview, _, _ = await driver.execute_query(PREVIEW_QUERY)
        print(f"\n{'due_date':<10} {'status':<10} {'uid':<16} title")
        for item in preview:
            print(
                f"{item['due_date']:<10} {item['status'] or '':<10} {item['uid']:<16} "
                f"{item['title'] or ''}"
            )

        if not confirm:
            print(f"\nCensus only. Re-run with --confirm to write {fillable} due date(s).")
            return 0

        records, _, _ = await driver.execute_query(BACKFILL_QUERY)
        written = int(records[0]["n"]) if records else 0
        print(f"\n✓ Task: set {DUE_FIELD} on {written} node(s) by the creation rule")

        records, _, _ = await driver.execute_query(CENSUS_QUERY)
        remaining = int(records[0]["fillable"])
        if remaining:
            print(
                f"\nFAILED: {remaining} Task(s) still undated after the write. "
                "Investigate before re-running.",
                file=sys.stderr,
            )
            return 1
        print("Verified: no Task with a created_at is left without a due or scheduled date.")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write the due dates. Without it the run is a read-only census "
            "that lists every node the write would touch and the value it would get."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_backfill(confirm=args.confirm)))


if __name__ == "__main__":
    main()
