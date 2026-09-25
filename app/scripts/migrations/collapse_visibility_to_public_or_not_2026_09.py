#!/usr/bin/env python3
"""
Collapse ``visibility`` to public-or-not — ``shared`` / ``team`` → ``private``
=============================================================================

``Visibility`` is ``{private, public}`` (ADR-088 §4): the share links are the
one record of who else may open an entity, and the property says only
whether it is published. The ``shared`` and ``team`` values are gone from the
enum, so a node still carrying one cannot be read back — the DTO parse
raises on an unknown member — until it is rewritten. Why the two values are
gone is ADR-088's record and the Submit & Share arc's
(``docs/roadmap/submission-sharing-arc.md``, PR 2a) — not repeated here.

What is rewritten, and why only that:

- **Every ``:Entity`` node with ``visibility IN ['shared', 'team']``**, label
  by label — the value is outside the enum everywhere, so the rewrite is
  label-agnostic. Neither value grants anything: every read admits by edge
  (``build_search_visibility_clause``, ADR-085) or by ownership, so setting
  both to ``private`` changes what no reader sees.
- **A spawned, user-owned node carrying ``public``** — a student's task /
  goal / habit / event / choice / principle spawned from a PathStep template.
  The instance is the student's own and takes the user-owned default
  (``private``); a curriculum template's ``public`` is not its to carry.
  Identified by the ``SPAWNED_FROM`` edge and a ``user_uid``, so a TEACHER's
  deliberate ``public`` on an authored entity is never touched.

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0 rows of either kind. The
second census is the invariant check: no writer on the new code produces a
retired value, so a non-zero count means a write landed between the rewrite
and the restart.

Usage:
    uv run scripts/migrations/collapse_visibility_to_public_or_not_2026_09.py            # census
    uv run scripts/migrations/collapse_visibility_to_public_or_not_2026_09.py --confirm  # rewrite
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.metadata_enums import Visibility
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, temporal), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_ENTITY = NeoLabel.ENTITY.value
_SPAWNED_FROM = RelationshipName.SPAWNED_FROM.value
_PRIVATE = Visibility.PRIVATE.value
_PUBLIC = Visibility.PUBLIC.value
# The two values outside the enum. Spelled here, not through the enum: the
# enum has no member for them, which is the point of the rewrite.
_RETIRED = ["shared", "team"]

# --- census ---------------------------------------------------------------

_RETIRED_BY_TYPE = f"""
MATCH (n:{_ENTITY})
WHERE n.visibility IN $retired
RETURN coalesce(n.entity_type, '<no entity_type>') AS entity_type,
       n.visibility AS visibility, count(n) AS nodes
ORDER BY entity_type, visibility
"""

_RETIRED_ROWS = f"""
MATCH (n:{_ENTITY})
WHERE n.visibility IN $retired
RETURN n.uid AS uid, coalesce(n.entity_type, '<no entity_type>') AS entity_type,
       n.visibility AS visibility, n.user_uid AS owner, n.title AS title
ORDER BY entity_type, owner, uid
"""

_SPAWNED_PUBLIC_ROWS = f"""
MATCH (n:{_ENTITY})-[:{_SPAWNED_FROM}]->(:{_ENTITY})
WHERE n.visibility = $public AND n.user_uid IS NOT NULL
RETURN n.uid AS uid, coalesce(n.entity_type, '<no entity_type>') AS entity_type,
       n.visibility AS visibility, n.user_uid AS owner, n.title AS title
ORDER BY entity_type, owner, uid
"""

_VALUES_IN_USE = f"""
MATCH (n:{_ENTITY})
WHERE n.visibility IS NOT NULL
RETURN n.visibility AS visibility, count(n) AS nodes
ORDER BY visibility
"""

# --- write ----------------------------------------------------------------

_REWRITE_RETIRED = f"""
MATCH (n:{_ENTITY})
WHERE n.visibility IN $retired
SET n.visibility = $private
RETURN count(n) AS nodes_rewritten
"""

_REWRITE_SPAWNED_PUBLIC = f"""
MATCH (n:{_ENTITY})-[:{_SPAWNED_FROM}]->(:{_ENTITY})
WHERE n.visibility = $public AND n.user_uid IS NOT NULL
SET n.visibility = $private
RETURN count(n) AS nodes_rewritten
"""

_PARAMS: dict[str, Any] = {"retired": _RETIRED, "private": _PRIVATE, "public": _PUBLIC}


async def _fetch(driver: AsyncDriver, query: str) -> list[Row]:
    result = await driver.execute_query(query, _PARAMS)
    return [dict(record) for record in result.records]


def _print_rows(heading: str, rows: list[Row]) -> None:
    print(f"\n{heading}: {len(rows)}")
    for row in rows:
        print(
            f"  {row['uid']}  [{row['entity_type']}]  visibility={row['visibility']}  "
            f"(owner {row['owner']})  {row['title']!r}"
        )


async def _census(driver: AsyncDriver) -> tuple[list[Row], list[Row]]:
    """Print the census; return (retired-value rows, spawned-public rows)."""
    values = await _fetch(driver, _VALUES_IN_USE)
    print("visibility values in use:")
    if not values:
        print("  (none)")
    for row in values:
        print(f"  {row['visibility']}: {row['nodes']}")

    by_type = await _fetch(driver, _RETIRED_BY_TYPE)
    print(f"\nNodes carrying a retired value ({', '.join(_RETIRED)}) by entity_type:")
    if not by_type:
        print("  (none)")
    for row in by_type:
        print(f"  {row['entity_type']} / {row['visibility']}: {row['nodes']}")
    retired_rows = await _fetch(driver, _RETIRED_ROWS)
    _print_rows("Rows carrying a retired value (ALL are set to private)", retired_rows)

    spawned_rows = await _fetch(driver, _SPAWNED_PUBLIC_ROWS)
    _print_rows(
        "Spawned user-owned rows carrying public (ALL are set to private)", spawned_rows
    )
    return retired_rows, spawned_rows


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set every retired visibility value, and a spawned instance's public, to private"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the rewrite (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        retired_rows, spawned_rows = await _census(driver)
        print(
            f"\nWould rewrite: {len(retired_rows)} retired-value row(s) + "
            f"{len(spawned_rows)} spawned-public row(s) → {_PRIVATE}"
        )
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to rewrite.")
            return 0
        if not retired_rows and not spawned_rows:
            print("\nNothing to rewrite.")
            return 0

        retired_done = await _fetch(driver, _REWRITE_RETIRED)
        spawned_done = await _fetch(driver, _REWRITE_SPAWNED_PUBLIC)
        retired_count = int(retired_done[0]["nodes_rewritten"]) if retired_done else 0
        spawned_count = int(spawned_done[0]["nodes_rewritten"]) if spawned_done else 0
        print(
            f"\nRewrote {retired_count} retired-value row(s) and {spawned_count} "
            f"spawned-public row(s)."
        )

        print("\n=== AFTER ===")
        retired_after, spawned_after = await _census(driver)
        if retired_after or spawned_after:
            print(
                f"\nFAILED: {len(retired_after)} retired-value and {len(spawned_after)} "
                "spawned-public row(s) remain."
            )
            return 1
        print("\nOK: no node carries a retired visibility value or a spawned public.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
