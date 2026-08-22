#!/usr/bin/env python3
"""Freeze the mutable ``updated_at`` completion proxy onto the canonical stamp.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds.

Until the completion-stamping arc (PRs #1122–#1124), only the explicit complete
paths recorded *when* an Activity was completed. Everything else — the
per-domain status route, generic CRUD updates, vault sync, ingestion — moved an
entity to ``completed`` and left the canonical field unset, so
``get_recent_activities`` approximated the completion moment with ``updated_at``.
That property is mutable: editing a long-completed task re-dated its
"completion" and bounced it to the top of recent activity.

The chokepoint stamp closes that for every *future* transition. This script
closes it for history, once: for each Activity label whose domain records a
completion moment, every ``status='completed'`` node with a NULL canonical field
gets ``field = updated_at``, projected to the field's shape.

**This is an approximation, and it is deliberately a one-time one.** ``updated_at``
is the last touch, not the completion — for a node edited after completion it is
late, and the true moment is not recoverable from the graph. Freezing it now is
strictly better than continuing to read it live, because after this run the value
stops moving: a later edit re-dates ``updated_at`` and no longer re-dates the
completion. Nodes already carrying a stamp are never touched (the real value
always wins), and a node with no ``updated_at`` at all is left unstamped rather
than given a fabricated date — the read excludes it (truth over coverage).

**Storage shape matches the writers, not the source property.** Every completion
field round-trips through ``to_neo4j_node``/``from_neo4j_node``, which persist
``date``/``datetime`` as ISO **strings**. ``updated_at`` on the live graph is a
mix (measured 2026-08-22 on AuraDB ``d2d160c4``: 89 STRING / 2 ZONED DATETIME on
Task), so the projection goes through ``toString()``, then truncates to
``YYYY-MM-DD`` for the two date-typed fields. Writing a native Neo4j DATE here
would read back fine but diverge from every stamp the app itself writes.

Idempotent: the second run finds no NULL canonical field and changes nothing.

Related: ``scripts/migrate_activity_completion_aliases.py`` retires the legacy
Goal ``completion_date`` alias. Run it first — a Goal whose completion lives
under the old name should be migrated, not overwritten with ``updated_at``.

Usage:
    uv run scripts/backfill_activity_completion_stamps.py             # census only (default)
    uv run scripts/backfill_activity_completion_stamps.py --confirm   # write the stamps
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.services.completion_stamp import COMPLETION_FIELDS

COMPLETED = EntityStatus.COMPLETED.value


@dataclass(frozen=True)
class StampSpec:
    """One label's backfill: where the stamp goes and what shape it takes.

    ``field`` is not declared here — it is read from ``COMPLETION_FIELDS`` so the
    backfill and the live chokepoint stamp cannot name different properties.
    ``is_date`` is this script's own concern: how to project ``updated_at`` onto
    that field (calendar date vs. full moment).
    """

    entity_type: EntityType
    is_date: bool

    @property
    def label(self) -> str:
        return NeoLabel.from_entity_type(self.entity_type).value

    @property
    def field(self) -> str:
        return COMPLETION_FIELDS[self.entity_type]

    @property
    def projection(self) -> str:
        """Cypher that turns ``updated_at`` into this field's stored shape."""
        source = "toString(n.updated_at)"
        return f"substring({source}, 0, 10)" if self.is_date else source


SPECS: tuple[StampSpec, ...] = (
    StampSpec(EntityType.TASK, is_date=True),  # completion_date: date
    StampSpec(EntityType.GOAL, is_date=True),  # achieved_date: date
    StampSpec(EntityType.HABIT, is_date=False),  # completed_at: datetime
    StampSpec(EntityType.EVENT, is_date=False),  # completed_at: datetime
    StampSpec(EntityType.CHOICE, is_date=False),  # completed_at: datetime
)

# Principle is deliberately absent from SPECS: COMPLETED is not one of its valid
# statuses, so it has no completion field to fill. Any completed Principle on the
# graph is an illegal row written before the chokepoint validation landed — the
# census reports it rather than inventing a stamp for it.
ILLEGAL_COMPLETED = f"""
MATCH (n:{NeoLabel.PRINCIPLE.value} {{status: $completed}})
RETURN count(*) AS n
"""


def census_query(spec: StampSpec) -> str:
    """Completed rows for one label, split by whether they carry a stamp."""
    return f"""
    MATCH (n:{spec.label} {{status: $completed}})
    RETURN count(*) AS completed,
           count(CASE WHEN n.{spec.field} IS NOT NULL THEN 1 END) AS stamped,
           count(CASE WHEN n.{spec.field} IS NULL AND n.updated_at IS NOT NULL THEN 1 END)
               AS fillable,
           count(CASE WHEN n.{spec.field} IS NULL AND n.updated_at IS NULL THEN 1 END)
               AS unstampable
    """


def backfill_query(spec: StampSpec) -> str:
    """Set the canonical field from ``updated_at`` where — and only where — it is NULL.

    The NULL guard is what makes the script idempotent and non-destructive: a
    stamp written by a real completion path is never overwritten by the proxy.

    Both interpolations are Cypher *structure*, not values, and neither can be a
    driver parameter: a property name and an expression over ``n.updated_at``.
    Both come from closed, code-owned sets — ``COMPLETION_FIELDS`` (keyed by
    ``EntityType``) and ``NeoLabel`` — so no request data reaches the string.
    """
    return f"""
    MATCH (n:{spec.label} {{status: $completed}})
    WHERE n.{spec.field} IS NULL AND n.updated_at IS NOT NULL
    SET n.{spec.field} = {spec.projection} // noqa: CYP003 - property name + expression, not a value; see docstring
    RETURN count(*) AS n
    """


def spec_coverage_gap() -> set[EntityType]:
    """Domains the stamp helper records but this script would silently skip.

    Guards the drift the shared ``COMPLETION_FIELDS`` mapping cannot: adding a
    domain to the helper without adding it here would leave that domain's history
    unfrozen with no error.
    """
    return set(COMPLETION_FIELDS) - {spec.entity_type for spec in SPECS}


async def run_backfill(*, confirm: bool) -> int:
    """Census the unstamped completions and, with --confirm, freeze the proxy."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    gap = spec_coverage_gap()
    if gap:
        print(
            "FAILED: these domains stamp a completion field but have no backfill "
            f"spec: {sorted(t.value for t in gap)}. Add them to SPECS.",
            file=sys.stderr,
        )
        return 1

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()

        total_fillable = 0
        print(f"\n{'label':<12} {'completed':>10} {'stamped':>8} {'fillable':>9} {'no source':>10}")
        for spec in SPECS:
            records, _, _ = await driver.execute_query(census_query(spec), completed=COMPLETED)
            row = records[0]
            total_fillable += int(row["fillable"])
            print(
                f"{spec.label:<12} {row['completed']:>10} {row['stamped']:>8} "
                f"{row['fillable']:>9} {row['unstampable']:>10}"
            )

        illegal, _, _ = await driver.execute_query(ILLEGAL_COMPLETED, completed=COMPLETED)
        if illegal and int(illegal[0]["n"]):
            print(
                f"\n  NOTE: {illegal[0]['n']} Principle node(s) carry status='completed', which "
                "is not a valid Principle status. Nothing to stamp — these predate the "
                "chokepoint validation and need their own decision.",
                file=sys.stderr,
            )

        print(
            "\n'fillable' = completed, no stamp, has updated_at to freeze.\n"
            "'no source' = completed with neither — left unstamped, excluded from the "
            "recent-activities read."
        )

        if total_fillable == 0:
            print("\nNothing to backfill — every completed Activity already carries its stamp.")
            return 0

        if not confirm:
            print(f"\nCensus only. Re-run with --confirm to freeze {total_fillable} stamp(s).")
            return 0

        written = 0
        for spec in SPECS:
            records, _, _ = await driver.execute_query(backfill_query(spec), completed=COMPLETED)
            count = int(records[0]["n"]) if records else 0
            written += count
            if count:
                print(f"✓ {spec.label}: froze {count} × {spec.field} from updated_at")

        print(f"\nStamped {written} node(s). The completion moment no longer moves on edit.")

        remaining = 0
        for spec in SPECS:
            records, _, _ = await driver.execute_query(census_query(spec), completed=COMPLETED)
            remaining += int(records[0]["fillable"])
        if remaining:
            print(
                f"\nFAILED: {remaining} completed node(s) still fillable after the write. "
                "Investigate before re-running.",
                file=sys.stderr,
            )
            return 1
        print("Verified: no completed Activity with an updated_at is left unstamped.")
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write the stamps. Without it the run is a read-only census. "
            "The write is a one-time approximation from updated_at and is not "
            "reversed by re-running."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_backfill(confirm=args.confirm)))


if __name__ == "__main__":
    main()
