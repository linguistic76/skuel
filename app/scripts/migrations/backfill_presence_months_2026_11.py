#!/usr/bin/env python3
"""
Backfill the presence record from the sign-in audit trail
=========================================================

The presence record is ``(:User)-[:PRESENT_IN {sign_ins, days, last_day}]->
(:Month {key})``: the months a user signed in during, or had a live session seen
in. Every sign-in and every session's first request of a day writes it
(``SessionBackend``), and ``/admin/analytics`` reads retention from it. A
sign-in also leaves an ``:AuthEvent``, which the telemetry prune deletes by age.
This run copies the sign-ins the audit trail holds onto the record, once, for
the user-months the record does not hold.

See: /docs/decisions/ADR-080-auradb-three-horizon-strategy.md

What it reads
-------------
``LOGIN_SUCCESS`` auth events, each joined to its user by the ``HAD_AUTH_EVENT``
edge, never by the event's ``user_uid`` property: an event whose account was
erased has no edge and is not counted.

Browser sign-ins only. The test is the event's ``user_agent`` starting
``Mozilla/``, which every browser sends and no HTTP library does by default;
sign-ins made by scripts (``python-httpx``, ``curl``, ...) are test and tooling
traffic and say nothing about a person being present. An event with no user
agent is not a browser sign-in.

Months and days are UTC: an event's ``timestamp`` is read in UTC whatever offset
it was stored with.

What it writes
--------------
One edge per user and month that has a browser sign-in, with ``sign_ins`` the
events in the month, ``days`` the distinct UTC days among them and ``last_day``
the latest. The live writers count every day a session makes a request; a
backfilled month counts only the days with a sign-in, so its ``days`` is a
floor on the days active, and ``/admin/analytics`` marks it "≥". A user-month that already holds an edge is left exactly as it is:
the live writers have been counting it, and adding the audit trail on top would
count its sign-ins twice.

A ``:MigrationRecord`` named ``presence_backfill_2026_11`` is written in the
same transaction, with the counts. A run that finds the record writes nothing,
so a second run adds nothing. The record is not one the graph driver requires
(``graph_driver.DATA_MIGRATIONS``): a graph without the backfill is read
correctly, only with a shorter history.

Usage (the live graph is AuraDB; run under ``direnv exec .``):
    uv run scripts/migrations/backfill_presence_months_2026_11.py --dry-run
    uv run scripts/migrations/backfill_presence_months_2026_11.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.utils.process_clock import pin_process_clock_to_utc

pin_process_clock_to_utc()  # before any clock read (ADR-089)

from core.models.auth.auth_event import AuthEventType
from core.models.enums.migration_enums import MigrationState
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncManagedTransaction

#: The record's name on the graph.
PRESENCE_BACKFILL = "presence_backfill_2026_11"
#: What a browser's user agent starts with.
BROWSER_AGENT_PREFIX = "Mozilla/"

_RECORD = NeoLabel.MIGRATION_RECORD.value
_MONTH = NeoLabel.MONTH.value
_PRESENT_IN = RelationshipName.PRESENT_IN.value
_HAD_AUTH_EVENT = RelationshipName.HAD_AUTH_EVENT.value

# One row per user and UTC month with a browser sign-in. ``held`` says the
# user-month already has its edge.
_USER_MONTHS = f"""
MATCH (u:User)-[:{_HAD_AUTH_EVENT}]->(e:AuthEvent)
WHERE e.event_type = $login_success AND e.user_agent STARTS WITH $browser
WITH u, datetime({{datetime: e.timestamp, timezone: 'UTC'}}) AS at
WITH u, substring(toString(at), 0, 7) AS month, toString(date(at)) AS day
WITH u, month, count(*) AS sign_ins, count(DISTINCT day) AS days, max(day) AS last_day
RETURN u.uid AS user_uid, month, sign_ins, days, last_day,
       EXISTS {{ (u)-[:{_PRESENT_IN}]->(:{_MONTH} {{key: month}}) }} AS held
ORDER BY user_uid, month
"""

_RECORD_STATE = f"MATCH (r:{_RECORD} {{name: $name}}) RETURN r.state AS state"

_WRITE_USER_MONTHS = f"""
UNWIND $rows AS row
MATCH (u:User {{uid: row.user_uid}})
MERGE (m:{_MONTH} {{key: row.month}})
MERGE (u)-[p:{_PRESENT_IN}]->(m)
ON CREATE SET p.sign_ins = row.sign_ins, p.days = row.days, p.last_day = row.last_day
"""

_WRITE_RECORD = f"""
CREATE (r:{_RECORD} {{name: $name, state: $applied, applied_at: datetime(),
                      user_months: $user_months, sign_ins: $sign_ins}})
"""


@dataclass(frozen=True)
class UserMonth:
    """One user's browser sign-ins in one UTC month, as the audit trail holds them."""

    user_uid: str
    month: str
    sign_ins: int
    days: int
    last_day: str
    held: bool


@dataclass(frozen=True)
class BackfillOutcome:
    """What a run wrote; ``already_applied`` when the record was there and nothing was."""

    already_applied: bool
    user_months: int = 0
    sign_ins: int = 0


async def read_user_months(driver: AsyncDriver) -> list[UserMonth]:
    """Every user-month the audit trail's browser sign-ins make."""
    records, _, _ = await driver.execute_query(
        _USER_MONTHS,
        login_success=AuthEventType.LOGIN_SUCCESS.value,
        browser=BROWSER_AGENT_PREFIX,
    )
    return [
        UserMonth(
            user_uid=str(record["user_uid"]),
            month=str(record["month"]),
            sign_ins=int(record["sign_ins"]),
            days=int(record["days"]),
            last_day=str(record["last_day"]),
            held=bool(record["held"]),
        )
        for record in records
    ]


async def record_is_applied(driver: AsyncDriver) -> bool:
    """Whether the graph holds this backfill's record."""
    records, _, _ = await driver.execute_query(_RECORD_STATE, name=PRESENCE_BACKFILL)
    return bool(records)


async def _write(tx: AsyncManagedTransaction, rows: list[UserMonth]) -> BackfillOutcome:
    # Read again inside the write transaction: a second run racing the first
    # finds the record (its name is unique) and writes nothing.
    held = await (await tx.run(_RECORD_STATE, name=PRESENCE_BACKFILL)).data()
    if held:
        return BackfillOutcome(already_applied=True)
    new = [row for row in rows if not row.held]
    result = await tx.run(
        _WRITE_USER_MONTHS,
        rows=[
            {
                "user_uid": row.user_uid,
                "month": row.month,
                "sign_ins": row.sign_ins,
                "days": row.days,
                "last_day": row.last_day,
            }
            for row in new
        ],
    )
    await result.consume()
    sign_ins = sum(row.sign_ins for row in new)
    await (
        await tx.run(
            _WRITE_RECORD,
            name=PRESENCE_BACKFILL,
            applied=MigrationState.APPLIED.value,
            user_months=len(new),
            sign_ins=sign_ins,
        )
    ).consume()
    return BackfillOutcome(already_applied=False, user_months=len(new), sign_ins=sign_ins)


async def apply_backfill(driver: AsyncDriver) -> BackfillOutcome:
    """Write the edges and the record in one transaction, unless the record is there."""
    from adapters.persistence.neo4j.graph_driver import ensure_record_name_is_unique
    from adapters.persistence.neo4j.neo4j_schema_manager import Neo4jSchemaManager

    # Schema first: a constraint cannot share a transaction with data writes.
    await ensure_record_name_is_unique(driver)
    constraint = await Neo4jSchemaManager(driver).ensure_month_key_is_unique()
    if constraint.is_error:
        raise RuntimeError(f"could not create the Month key constraint: {constraint.error}")

    rows = await read_user_months(driver)
    async with driver.session() as session:
        return await session.execute_write(_write, rows)


def render(rows: list[UserMonth]) -> str:
    """The user-months as a table, with what a run would write."""
    lines = [f"{'user':<24} {'month':<8} {'sign-ins':>8} {'days':>5}  last day"]
    for row in rows:
        note = "   (edge already there: left as it is)" if row.held else ""
        lines.append(
            f"{row.user_uid:<24} {row.month:<8} {row.sign_ins:>8} {row.days:>5}  "
            f"{row.last_day}{note}"
        )
    new = [row for row in rows if not row.held]
    lines.append(
        f"\n{len(new)} user-month(s) to write, {sum(row.sign_ins for row in new)} sign-in(s), "
        f"{len({row.user_uid for row in new})} user(s), "
        f"{len({row.month for row in new})} month(s); "
        f"{len(rows) - len(new)} already held."
    )
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the presence record from browser sign-ins in the audit trail"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the user-months the run would write, and write nothing",
    )
    args = parser.parse_args(argv)

    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        driver = adapter.get_driver()
        if await record_is_applied(driver):
            print(f"The {PRESENCE_BACKFILL!r} record is on the graph: nothing to write.")
            return 0
        rows = await read_user_months(driver)
        print(render(rows))
        if args.dry_run:
            print("\nDRY RUN: nothing was written.")
            return 0
        outcome = await apply_backfill(driver)
        if outcome.already_applied:
            print(f"\nThe {PRESENCE_BACKFILL!r} record appeared during the run: nothing written.")
            return 0
        print(
            f"\nWrote {outcome.user_months} user-month(s), {outcome.sign_ins} sign-in(s), "
            f"and the {PRESENCE_BACKFILL!r} record."
        )
        return 0
    finally:
        await adapter.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
