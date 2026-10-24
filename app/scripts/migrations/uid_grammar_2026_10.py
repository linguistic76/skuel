#!/usr/bin/env python3
"""
The uid grammar's record — stamped when the uid census passes
=============================================================

Writes the graph's ``:MigrationRecord`` named ``uid_grammar_2026_10`` (state
``applied``) once the uid census (``scripts/uid_census.py``, ``./dev
uid-census``) passes: every uid fits the grammar — a shape an exemption names
fails it like any other — and no uid is held by two nodes. The graph driver's
guard (``graph_driver.require_migration_records``, run by every
``Neo4jConnection.connect``) refuses a graph holding data without the record, so
code that reads uids in one grammar never boots on a graph holding another — an
Aura snapshot taken before the uid migrations, restored.

Uids say for themselves whether they moved, so the record keeps no manifest: the
census is its evidence, and the record holds what the census read (``uids``, the
count) beside the state.

The run STOPS (exit 2), writing nothing, while the census fails, or while the
graph holds the record more than once or in a state other than ``applied`` (no
script writes one — repair it by hand). A record already applied is left as it
is.

Run order — the arc's close sitting (the live graph is AuraDB; run under
``direnv exec .`` so the credentials resolve):

1. Stop the app. Merge and pull — the app now refuses the graph until step 3.
2. Census (no flag): the census, and what the run would write.
3. ``--confirm``: the record, then a read-back.
4. Boot the app.

A graph from before the uid migrations (a restored snapshot) is brought forward
by them first, in the order they ran — ``chunk_and_content_uids_2026_10.py``,
``periodic_note_uids_2026_10.py``, ``generated_uids_2026_10.py``,
``user_uids_2026_10.py`` — each of which ends by reading this census; the last,
the user uid migration, fails its run when the census does not pass.

Usage:
    uv run scripts/migrations/uid_grammar_2026_10.py            # census
    uv run scripts/migrations/uid_grammar_2026_10.py --confirm  # stamp
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.enums.migration_enums import MigrationState
from core.models.enums.neo_labels import NeoLabel
from scripts.uid_census import failures, read_census, render

if TYPE_CHECKING:
    from neo4j import AsyncDriver

#: Why the record is on the graph: the census passed when it was written.
STAMPED_BY_CENSUS = "uid census passed"

_RECORD = NeoLabel.MIGRATION_RECORD.value

# One entry per record, a missing state kept as null.
_RECORD_STATES = f"""
OPTIONAL MATCH (r:{_RECORD} {{name: $name}})
WITH collect(r) AS records
RETURN [r IN records | r.state] AS states
"""

_STAMP = f"""
MERGE (r:{_RECORD} {{name: $name}})
ON CREATE SET r.state = $applied, r.stamped = $stamped, r.uids = $uids,
              r.applied_at = datetime()
RETURN r.state AS state
"""


def record_refusal(name: str, states: list[str | None]) -> str | None:
    """Why the graph's record refuses a stamp, or None — for no record, or one applied."""
    if len(states) > 1:
        return f"the graph holds {len(states)} {_RECORD} nodes named {name!r}"
    if states and MigrationState.from_stored(states[0]) is not MigrationState.APPLIED:
        return f"the {_RECORD} {name!r} is in state {states[0]!r}, not 'applied'"
    return None


async def record_states(driver: AsyncDriver, name: str) -> list[str | None]:
    """The state of each record named ``name`` — None where one has no state."""
    records, _, _ = await driver.execute_query(_RECORD_STATES, name=name)
    states = records[0]["states"] if records else []
    return [None if state is None else str(state) for state in states]


async def stamp(driver: AsyncDriver, name: str, uids: int) -> list[str | None]:
    """Write the record, applied, unless it is already there; the states read back."""
    from adapters.persistence.neo4j.graph_driver import ensure_record_name_is_unique

    await ensure_record_name_is_unique(driver)
    await driver.execute_query(
        _STAMP,
        name=name,
        applied=MigrationState.APPLIED.value,
        stamped=STAMPED_BY_CENSUS,
        uids=uids,
    )
    return await record_states(driver, name)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stamp the graph with the uid grammar's record when the uid census passes"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the record (default is a census: print it and the verdict, change nothing)",
    )
    args = parser.parse_args(argv)

    from adapters.persistence.neo4j.graph_driver import UID_GRAMMAR_MIGRATION, UTC_INSTANTS
    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    # This run writes the uid grammar's record, so it opens before it exists.
    connection = Neo4jConnection(requires=(UTC_INSTANTS,))
    driver = await connection.connect()
    try:
        read = await read_census(driver)
        if read.is_error:
            print(f"ERROR reading the census: {read.expect_error()}", file=sys.stderr)
            return 1
        census, uidless = read.value
        print("=== UID census ===\n")
        print(render(census, uidless))
        uids = sum(tally.total for tally in census.by_label.values())

        reasons = failures(census)
        if reasons:
            print("\nSTOP: the census fails — " + "; ".join(reasons) + ". Nothing was written.")
            print("Move what it names (the uid migrations), then re-run.")
            return 2
        states = await record_states(driver, UID_GRAMMAR_MIGRATION)
        refusal = record_refusal(UID_GRAMMAR_MIGRATION, states)
        if refusal:
            print(f"\nSTOP: {refusal}. Nothing was written.")
            return 2
        if states:
            print(f"\nThe census passes; the {UID_GRAMMAR_MIGRATION!r} record is already applied.")
            return 0
        if not args.confirm:
            print(
                f"\nThe census passes ({uids} uids). CENSUS ONLY — nothing written. "
                f"Re-run with --confirm to stamp {UID_GRAMMAR_MIGRATION!r}."
            )
            return 0

        after = await stamp(driver, UID_GRAMMAR_MIGRATION, uids)
        if [MigrationState.from_stored(state) for state in after] != [MigrationState.APPLIED]:
            print(f"\nFAILED: the record reads back as {after}, not one applied record.")
            return 1
        print(f"\nStamped {UID_GRAMMAR_MIGRATION!r} (applied; {uids} uids). Boot the app.")
        return 0
    finally:
        await connection.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
