#!/usr/bin/env python3
"""
Clear the six time zones nobody chose
=====================================

UTC Instants arc PR 2a (R2 — docs/roadmap/utc-instants-arc.md): a user's zone is
``UserPreferences.timezone``, an IANA name chosen in Settings, or null, which
follows ``SKUEL_TIMEZONE``. Six users hold ``"UTC"`` because it was the field's
default, not because anyone chose it. This script sets those six to null. It is
keyed by uid, never by value: ``"UTC"`` is a zone a user may choose.

The zone lives inside the User node's ``preferences`` property — the JSON object
string the mapper writes for ``User.preferences`` — so the script reads that
string, and rewrites it with ``"timezone": null`` and every other key as it was.

**Census** (the default, read-only): lists every user whose stored zone is
``"UTC"``, and every other user's stored zone for the record. It STOPS (exit 2)
unless the ``"UTC"`` users are exactly the six below, when a user's preferences
cannot be read, or when one of the six uids names more than one User node.

**--confirm**: the census, then ONE write in one transaction — each of the six
set to null where its ``preferences`` still equals what the census read. A row
that changed since the census rolls the whole write back (exit 1, nothing
written). Then the census again, which must show the six at null.

Laptop only, run once, with Mike's OK on the count first (the arc's § Standing
conventions: every AuraDB write). PR 2b does not start until it has run: PR 2b
makes every calendar site follow the stored zone.

Usage (from app/, with the laptop's .env loaded):
    uv run python scripts/migrations/clear_unchosen_utc_timezone_2026_09.py            # census
    uv run python scripts/migrations/clear_unchosen_utc_timezone_2026_09.py --confirm  # write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars, so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

#: The users whose "UTC" is the field's old default, never a choice (read-only
#: census of the daily graph, 2026-09-27).
NEVER_CHOSEN: frozenset[str] = frozenset(
    {
        "user_system",
        "user_linguistic76",
        "user_iw_test",
        "user_admin",
        "user_vault_watcher",
        "user_uxsmoke",
    }
)

OLD_DEFAULT = "UTC"

_USER = NeoLabel.USER.value

_USER_PREFERENCES = f"""
MATCH (u:{_USER})
RETURN u.uid AS uid, u.preferences AS preferences
ORDER BY uid
"""

# Compare-and-set on the whole preferences string the census read: a row that
# changed since is not rewritten from a stale copy, and its absence from the
# RETURN rolls the transaction back.
_CLEAR = f"""
UNWIND $rows AS row
MATCH (u:{_USER} {{uid: row.uid}})
WHERE u.preferences = row.old
SET u.preferences = row.new
RETURN u.uid AS uid
"""

# The stored-zone states a User node can be in.
_NO_KEY = "no timezone key"
_NO_PREFERENCES = "no preferences"
_NULL = "null"


def _preferences(raw: object) -> dict[str, Any] | None:
    """The stored ``preferences`` JSON object as a mapping; None when it is not one."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _cleared(raw: str) -> str:
    """The same preferences with the zone set to null — no other key changes."""
    parsed = _preferences(raw)
    if parsed is None:
        raise ValueError(f"preferences are not a JSON object: {raw!r}")
    return json.dumps({**parsed, "timezone": None})


@dataclass(frozen=True)
class Census:
    """Every User node's stored zone, read once."""

    #: Stored zone "UTC" — the clear's candidates. Rows keep the raw preferences.
    utc: list[Row]
    #: uid → stored zone for every other user: a name, "null", or no stored zone.
    others: dict[str, str]
    #: Users whose preferences are present but not a JSON object.
    unreadable: list[str]
    #: Expected uids that name more than one User node.
    duplicates: list[str]
    #: The uids the clear is for.
    expected: frozenset[str]

    @property
    def utc_uids(self) -> frozenset[str]:
        return frozenset(str(row["uid"]) for row in self.utc)

    @property
    def done(self) -> bool:
        """The six are cleared: none holds "UTC" and each is at null."""
        return not self.utc and all(self.others.get(uid) == _NULL for uid in self.expected)

    @property
    def stops(self) -> list[str]:
        """Why the clear must not run; empty when it may."""
        reasons: list[str] = []
        if self.unreadable:
            reasons.append(f"unreadable preferences: {', '.join(sorted(self.unreadable))}")
        if self.duplicates:
            reasons.append(f"uid on more than one User node: {', '.join(self.duplicates)}")
        if not self.done and self.utc_uids != self.expected:
            extra = sorted(self.utc_uids - self.expected)
            missing = sorted(self.expected - self.utc_uids)
            if extra:
                reasons.append(f'"UTC" outside the six (a choice to keep?): {", ".join(extra)}')
            if missing:
                held = ", ".join(f"{uid}={self.others.get(uid, 'no User node')}" for uid in missing)
                reasons.append(f'of the six, not holding "UTC": {held}')
        return reasons


async def _fetch(
    driver: AsyncDriver, query: str, params: dict[str, object] | None = None
) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


async def run_census(driver: AsyncDriver, expected: frozenset[str]) -> Census:
    """Print the census of every User node's stored zone against ``expected`` and return it."""
    rows = await _fetch(driver, _USER_PREFERENCES)
    counts = Counter(str(row["uid"]) for row in rows)
    utc: list[Row] = []
    others: dict[str, str] = {}
    unreadable: list[str] = []
    for row in rows:
        uid, raw = str(row["uid"]), row["preferences"]
        if raw is None:
            others[uid] = _NO_PREFERENCES
            continue
        parsed = _preferences(raw)
        if parsed is None:
            unreadable.append(uid)
            continue
        if "timezone" not in parsed:
            others[uid] = _NO_KEY
        elif parsed["timezone"] == OLD_DEFAULT:
            utc.append(row)
        elif parsed["timezone"] is None:
            others[uid] = _NULL
        else:
            others[uid] = str(parsed["timezone"])
    duplicates = sorted(uid for uid in expected if counts[uid] > 1)
    census = Census(utc, others, unreadable, duplicates, expected)

    print(f'\nUsers whose stored zone is "{OLD_DEFAULT}" (the old default): {len(utc)}')
    for row in utc:
        marker = "" if row["uid"] in expected else "   <- NOT one of the six"
        print(f"  {row['uid']}{marker}")
    chosen = {
        uid: zone for uid, zone in others.items() if zone not in (_NULL, _NO_KEY, _NO_PREFERENCES)
    }
    print(f"\nUsers with another stored zone (a choice; never touched): {len(chosen)}")
    for uid, zone in sorted(chosen.items()):
        print(f"  {uid}  {zone}")
    following = {uid: state for uid, state in others.items() if uid not in chosen}
    print(f"\nUsers with no stored zone (they follow SKUEL_TIMEZONE): {len(following)}")
    for uid, state in sorted(following.items()):
        print(f"  {uid}  ({state})")
    if unreadable:
        print(f"\nUsers whose preferences are not a JSON object: {len(unreadable)}")
        for uid in sorted(unreadable):
            print(f"  {uid}")
    if census.done:
        print(f'\nDONE: none holds "{OLD_DEFAULT}" and the six are at null.')
    elif census.stops:
        print("\nSTOP:")
        for reason in census.stops:
            print(f"  {reason}")
    else:
        print(f'\nOK: the "{OLD_DEFAULT}" users are exactly the six this script clears.')
    return census


async def clear(driver: AsyncDriver, rows: list[Row]) -> list[str]:
    """ONE transaction: set each row's zone to null where its preferences still match.

    Returns the uids that no longer matched the census; when there is any, the
    transaction is rolled back and nothing is written.
    """
    payload = [
        {"uid": str(row["uid"]), "old": row["preferences"], "new": _cleared(row["preferences"])}
        for row in rows
    ]
    wanted = sorted(item["uid"] for item in payload)
    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            result = await tx.run(_CLEAR, rows=payload)
            written = sorted([str(record["uid"]) async for record in result])
            if written != wanted:
                await tx.rollback()
                return sorted(set(wanted) - set(written)) or written
            await tx.commit()
            return []
        finally:
            if not tx.closed():
                await tx.rollback()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description='Set the six never-chosen "UTC" time zones to null (UTC arc PR 2a)'
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the clear (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== CENSUS ===" if not args.confirm else "=== BEFORE ===")
        census = await run_census(driver, NEVER_CHOSEN)
        if census.done:
            print("\nNothing to clear.")
            return 0
        if census.stops:
            print("\nREFUSED: nothing written. The census above says why; Mike rules.")
            return 2
        print(f'\nWould clear: {len(census.utc)} user(s), each "timezone": "{OLD_DEFAULT}" -> null')
        if not args.confirm:
            print(
                "\nCENSUS ONLY: nothing written. With Mike's OK on the count, re-run with --confirm."
            )
            return 0

        unmatched = await clear(driver, census.utc)
        if unmatched:
            print(
                "\nFAILED: preferences changed since the census for "
                f"{', '.join(unmatched)}; the transaction was rolled back and nothing was written."
            )
            return 1
        print(f"\nCleared {len(census.utc)} user(s) in one transaction.")

        print("\n=== AFTER ===")
        after = await run_census(driver, NEVER_CHOSEN)
        if not after.done:
            print("\nFAILED: the six are not all at null after the write.")
            return 1
        print("\nOK: the six follow SKUEL_TIMEZONE.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
