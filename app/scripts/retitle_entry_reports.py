#!/usr/bin/env python3
"""Retitle legacy machine-titled EntryReports from their subject.

A ONE-SHOT migration (feedback-loop UX arc, choice C3 — see
``docs/roadmap/feedback-loop-ux-arc.md``) — no background loop, so the CORE
"no background workers" guarantee holds.

Report titles used to be hardcoded at creation from raw UIDs
(``Feedback: ue_65688cb7…``), which is what Shared-With-Me and the report
listings rendered. All writers now compose the title from the report's
subject at creation (``Feedback on '{exercise.title}'``, falling back to the
entry title — never a raw UID). This script converges the already-created
nodes on the same rule.

For every EntryReport whose title still carries a legacy machine prefix, the
subject is re-derived exactly the way the writers now derive it:
``(report)-[:REPORT_FOR]->(entry)`` then the entry's fulfilled exercise's
title when the ``FULFILLS_EXERCISE`` edge exists, else the entry's own title.

**Surface, don't force:** a legacy-titled report whose subject cannot be
derived (no ``REPORT_FOR`` edge, or the chain yields no usable title) is left
untouched and reported — inventing a title would erase the only signal that
the node came from an unknown write path.

Embeddings are NOT refreshed here — the content-hash staleness backstop
(``scripts/generate_embeddings_batch.py --stale``) picks retitled nodes up on
its next run (ADR-074 §8).

Usage:
    uv run scripts/retitle_entry_reports.py              # census only (default)
    uv run scripts/retitle_entry_reports.py --confirm    # retitle
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.models.relationship_names import RelationshipName

# Legacy machine-title prefix → the composed-title lead-in the writers use now.
_PREFIX_MAP = {
    "Feedback: ": "Feedback on",
    "AI Feedback: ": "AI feedback on",
    "Revision request: ": "Revision requested on",
    "Reflection on: ": "Reflection on",
    "Reflection on entry ": "Reflection on",
}

# Census: legacy-titled reports, bucketed by prefix and by whether a subject
# title is derivable via REPORT_FOR (the retitle's own derivation, read-only).
_CENSUS = f"""
MATCH (r:Entity:EntryReport)
WHERE any(p IN keys($prefix_map) WHERE r.title STARTS WITH p)
OPTIONAL MATCH (r)-[:{RelationshipName.REPORT_FOR.value}]->(s:Entity)
WITH r, head([p IN keys($prefix_map) WHERE r.title STARTS WITH p]) AS legacy_prefix,
     coalesce(
         head([(s)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
               WHERE ex.title IS NOT NULL AND ex.title <> '' | ex.title]),
         s.title
     ) AS subject_title
RETURN legacy_prefix,
       subject_title IS NOT NULL AND subject_title <> '' AS derivable,
       count(*) AS n
ORDER BY legacy_prefix
"""

_RETITLE = f"""
MATCH (r:Entity:EntryReport)
WHERE any(p IN keys($prefix_map) WHERE r.title STARTS WITH p)
OPTIONAL MATCH (r)-[:{RelationshipName.REPORT_FOR.value}]->(s:Entity)
WITH r, head([p IN keys($prefix_map) WHERE r.title STARTS WITH p]) AS legacy_prefix,
     coalesce(
         head([(s)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
               WHERE ex.title IS NOT NULL AND ex.title <> '' | ex.title]),
         s.title
     ) AS subject_title
WHERE subject_title IS NOT NULL AND subject_title <> ''
SET r.title = $prefix_map[legacy_prefix] + " '" + subject_title + "'",
    r.updated_at = datetime()
RETURN count(*) AS n
"""


async def run_migration(*, confirm: bool) -> int:
    """Census legacy-titled reports and, with --confirm, retitle the derivable ones."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()
        params = {"prefix_map": _PREFIX_MAP}

        census, _, _ = await driver.execute_query(_CENSUS, params)
        derivable_total = sum(int(row["n"]) for row in census if row["derivable"])
        stuck_total = sum(int(row["n"]) for row in census if not row["derivable"])

        print(f"\nLegacy-titled EntryReports (retitleable) : {derivable_total}")
        for row in census:
            if row["derivable"]:
                print(f"    '{row['legacy_prefix']}…'  {row['n']}")
        if stuck_total:
            print(
                f"\n  NOTE: {stuck_total} legacy-titled report(s) have no derivable "
                "subject (no REPORT_FOR chain with a usable title). Left untouched — "
                "investigate their write path independently:",
                file=sys.stderr,
            )
            for row in census:
                if not row["derivable"]:
                    print(f"    '{row['legacy_prefix']}…'  {row['n']}", file=sys.stderr)

        if derivable_total == 0:
            print("\nNothing to retitle.")
            return 0

        if not confirm:
            print("\nCensus only. Re-run with --confirm to retitle.")
            return 0

        retitled, _, _ = await driver.execute_query(_RETITLE, params)
        n = int(retitled[0]["n"]) if retitled else 0
        print(f"\nRetitled {n} report(s).")

        remaining, _, _ = await driver.execute_query(_CENSUS, params)
        left = sum(int(row["n"]) for row in remaining if row["derivable"])
        if left:
            print(
                f"FAILED: {left} retitleable report(s) survived the retitle — "
                "investigate before re-running.",
                file=sys.stderr,
            )
            return 1
        return 0
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually retitle. Without it the run is a read-only census of "
            "legacy machine-titled reports."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_migration(confirm=args.confirm)))


if __name__ == "__main__":
    main()
