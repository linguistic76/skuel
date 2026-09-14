#!/usr/bin/env python3
"""Give every undated Task the due date the creation rule would have given it.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds.

The rule: a task created with neither ``due_date`` nor ``scheduled_date`` is due
the day it is created (``Task.with_creation_due_date``). The service create
primitive and the template spawn apply it now; the vault frontmatter bulk-upsert
does not (see the method's docstring), so this script is also the remedy for a
``type: task`` file authored without dates. Before the rule, most captured
tasks — daily-note extractions, quick entries — carried no date at all, and the
day lens and calendar, which place a task by exactly those two fields, showed
none of them on any day (measured 2026-09-14 on AuraDB ``d2d160c4``: 60 of 77
Tasks, every open one among them). This script applies the rule to that history,
once — and again whenever the frontmatter door has let an undated task in.

**The written value is the rule, not an approximation of it.** Per undated node:
``due_date`` = the ``created_at`` calendar day, or the ``completion_date`` when
that is *earlier* — a historical ``✅`` line was lived on the day it was done,
not the day it was ingested (the same branch the model method takes). A task
completed on or after its creation day keeps the creation day: it was due then
and finished later.

**Storage shape matches the writers.** ``due_date`` round-trips through
``to_neo4j_node``/``from_neo4j_node`` as an ISO ``YYYY-MM-DD`` **string**;
``created_at`` and ``completion_date`` are ISO strings on the live graph too, but
the projection goes through ``toString()`` regardless so a native temporal on
either source flattens to the one shape every app writer stores.

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

from core.models.enums.neo_labels import NeoLabel

TASK_LABEL = NeoLabel.TASK.value

#: The two fields the day lens and the calendar place a task by. A node is
#: "undated" when BOTH are NULL — the exact predicate ``Task.with_creation_due_date``
#: fills on, so the backfill and the live rule cannot disagree on who qualifies.
DUE_FIELD = "due_date"
SCHEDULED_FIELD = "scheduled_date"

#: The rule as a Cypher expression over an undated node ``n``: the creation day,
#: or the completion day when that came first. ``substring(toString(…), 0, 10)``
#: is the ``YYYY-MM-DD`` prefix whatever the source's storage type; ISO date
#: strings compare correctly as strings.
CREATED_DAY = "substring(toString(n.created_at), 0, 10)"
DONE_DAY = "substring(toString(n.completion_date), 0, 10)"
RULE_PROJECTION = (
    f"CASE WHEN n.completion_date IS NOT NULL AND {DONE_DAY} < {CREATED_DAY} "
    f"THEN {DONE_DAY} ELSE {CREATED_DAY} END"
)

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
