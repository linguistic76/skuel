#!/usr/bin/env python3
"""Fill the NULL completion stamps on ``ProductivityAnalytics`` from task history.

An **idempotent, on-demand pass** — run by hand, never a loop, so the CORE
"no background workers" guarantee holds. Tier-independent: pure graph
maintenance, no API keys. What it fills and what it refuses to touch is in 1
below.

``ProductivityAnalytics`` holds exactly two figures: ``first_completion_at``
and ``last_completion_at``, written by the ``TaskCompleted`` handler on every
genuine completion moment. ``tasks_completed`` is **derived at read** — the
tasks the user currently owns in ``completed``, counted by
``CrossDomainBackend.get_productivity_analytics`` on the same traversal as the
velocity window — so nothing maintains it and nothing should still store it.

Two things can be wrong for that shape, and this script fixes both:

1. **Null stamps.** A user can own completed tasks and still carry no stamp —
   no ``ProductivityAnalytics`` node at all, or a node whose stamps are
   ``null``. Three causes, and only the first is finite — which is why this is
   worth re-running, not only running:

   - completions older than the handler that writes the stamps (the bulk of it,
     and the reason this script exists — the account is in
     ``docs/roadmap/done/vault-task-door-no-events.md``);
   - an announcement the vault door loses. That door has no outbox: when reading
     the persisted entities back fails,
     ``UnifiedIngestionService._publish_completions`` logs and drops the
     completion event, and nothing retries it — the next ingest reads those
     entities as already completed;
   - a stamp write that fails. ``CrossDomainAnalyticsService.handle_task_completed``
     logs a failed ``stamp_productivity_completion`` and returns ok, so the
     announcement is published and heard while the stamp never lands.

   ⚠ **It repairs a NULL stamp and nothing else** — the fill's contract is
   right below, and a stamp that exists is never moved. So a user who holds both
   stamps and then loses an announcement keeps a stale ``last_completion_at``,
   and nothing repairs that: it belongs to the durability gap
   (``docs/roadmap/ingest-transition-obligation-durability.md``), not here.

   This fills **only NULL stamps**: ``first_completion_at`` from the earliest
   ``Task.completion_date`` the user currently owns in ``completed``,
   ``last_completion_at`` from the latest. A stamp that exists is never moved —
   the handler's value is the real moment; this is a day-grained reconstruction
   (``completion_date`` is a calendar date, so midnight UTC is the honest
   projection, and a stamp filled here can order before or after a real one on
   the same day only by hours). The one edge the guard covers: a filled value
   never crosses the stamp that already exists (``first <= last`` holds after
   the write, whichever half was missing).

   Reconstructed from what the graph holds *now*: a task reopened or deleted
   since it was completed is not in the census. Truth over coverage — a user
   with a node but no stamped completed task keeps their ``null`` rather than
   receiving an invented date.

2. **The retired count.** Nodes written before the count was derived still
   carry ``tasks_completed`` — a number nothing reads and nothing maintains,
   which is exactly the shape that drifts and then gets trusted. Dropped.

**Storage shape matches the writer.** The handler writes
``datetime($occurred_at)`` (a ZONED DATETIME); so does this script, from the
``YYYY-MM-DD`` day the stamp projects to. ``completion_date`` itself is read
through ``left(toString(...), 10)`` because the *writer* decides its storage
type, not this reader — an ISO string on every live row, but a native
``date``/``datetime`` has to project to the same day rather than vanish.

Idempotent: a re-run with no NULL stamp left to fill and no retired count
changes nothing — which is what makes running it again safe. The write is one statement per concern, so an
interrupted run leaves each user either untouched or complete.

Usage:
    uv run scripts/backfill_productivity_completion_stamps.py             # census only (default)
    uv run scripts/backfill_productivity_completion_stamps.py --confirm   # write
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

COMPLETED = EntityStatus.COMPLETED.value

_USER = NeoLabel.USER.value
_TASK = NeoLabel.TASK.value
_ANALYTICS = NeoLabel.PRODUCTIVITY_ANALYTICS.value
_OWNS = RelationshipName.OWNS.value

# Both queries project a completed task's stamp to its calendar day whatever the
# writer stored it as, and traverse ownership by the universal :OWNS edge
# (ADR-086) — the same traversal the derived count uses.

# READ-ONLY. One row per user who either has a node or owns a stamped completed
# task. Both arms matter: the first catches a node whose stamps are null and
# unfillable (reported, left alone); the second catches a user who owns stamped
# completed tasks but has no analytics node at all.
CENSUS_QUERY = f"""
MATCH (u:{_USER})
OPTIONAL MATCH (u)-[:{_OWNS}]->(t:{_TASK} {{status: $completed}})
WHERE t.completion_date IS NOT NULL
WITH u,
     min(left(toString(t.completion_date), 10)) AS first_day,
     max(left(toString(t.completion_date), 10)) AS last_day
OPTIONAL MATCH (a:{_ANALYTICS} {{user_uid: u.uid}})
WITH u.uid AS user_uid, first_day, last_day, a
WHERE a IS NOT NULL OR first_day IS NOT NULL
RETURN user_uid,
       a IS NOT NULL AS has_node,
       a.first_completion_at IS NOT NULL AS has_first,
       a.last_completion_at IS NOT NULL AS has_last,
       a.tasks_completed IS NOT NULL AS has_retired_count,
       first_day,
       last_day
ORDER BY user_uid
"""

# The retired count is counted off the label, not per user: a node whose user
# row is gone still carries it, and the drop below reaches that node too.
RETIRED_COUNT_QUERY = f"""
MATCH (a:{_ANALYTICS})
WHERE a.tasks_completed IS NOT NULL
RETURN count(a) AS n
"""

# Fills NULL stamps only. ``old_first`` / ``old_last`` are read into scope
# BEFORE the SET so both right-hand sides see the pre-write values, and the
# guard keeps a filled value from crossing the stamp that already exists.
# MERGE creates the node for a user who never had one; a user with both stamps
# present is matched, coalesced to themselves, and counted in neither total.
# Idempotent by construction.
BACKFILL_QUERY = f"""
MATCH (u:{_USER})-[:{_OWNS}]->(t:{_TASK} {{status: $completed}})
WHERE t.completion_date IS NOT NULL
WITH u,
     min(left(toString(t.completion_date), 10)) AS first_day,
     max(left(toString(t.completion_date), 10)) AS last_day
MERGE (a:{_ANALYTICS} {{user_uid: u.uid}})
WITH a, datetime(first_day) AS first_dt, datetime(last_day) AS last_dt,
     a.first_completion_at AS old_first, a.last_completion_at AS old_last
SET a.first_completion_at = coalesce(
        old_first,
        CASE WHEN old_last < first_dt THEN old_last ELSE first_dt END
    ),
    a.last_completion_at = coalesce(
        old_last,
        CASE WHEN old_first > last_dt THEN old_first ELSE last_dt END
    )
RETURN count(CASE WHEN old_first IS NULL THEN 1 END) AS first_filled,
       count(CASE WHEN old_last IS NULL THEN 1 END) AS last_filled
"""

DROP_RETIRED_COUNT_QUERY = f"""
MATCH (a:{_ANALYTICS})
WHERE a.tasks_completed IS NOT NULL
REMOVE a.tasks_completed
RETURN count(a) AS n
"""


class CensusRow(TypedDict):
    """One ``CENSUS_QUERY`` row, keyed by its RETURN aliases.

    ``first_day`` / ``last_day`` are the ``YYYY-MM-DD`` projections of the
    user's earliest and latest stamped completed task, or ``None`` when they
    own none — which is how a node with null stamps reads as unfillable.
    """

    user_uid: str
    has_node: bool
    has_first: bool
    has_last: bool
    has_retired_count: bool
    first_day: str | None
    last_day: str | None


def _to_census_row(record: Mapping[str, Any]) -> CensusRow:  # boundary: raw neo4j-driver record
    """Project a driver record onto CensusRow (KeyError on alias drift).

    Nothing statically links a Cypher alias to a TypedDict key, so a renamed
    RETURN would type-check while the census read a missing key as "nothing to
    do" — a confident no-op on a pass whose job is to notice gaps. Indexing
    each alias turns that into a loud failure before anything is written.
    """
    return {
        "user_uid": str(record["user_uid"]),
        "has_node": bool(record["has_node"]),
        "has_first": bool(record["has_first"]),
        "has_last": bool(record["has_last"]),
        "has_retired_count": bool(record["has_retired_count"]),
        "first_day": None if record["first_day"] is None else str(record["first_day"]),
        "last_day": None if record["last_day"] is None else str(record["last_day"]),
    }


@dataclass(frozen=True)
class StampPlan:
    """What the write would do for one census row — pure, so it is testable DB-free.

    ``fill_first`` / ``fill_last`` carry the day that would be written, or
    ``None`` when nothing would be: the stamp already exists, or the user has
    no stamped completed task to derive it from (``unfillable``).
    """

    user_uid: str
    has_node: bool
    fill_first: str | None
    fill_last: str | None
    unfillable: bool
    drops_retired_count: bool

    @classmethod
    def from_row(cls, row: CensusRow) -> StampPlan:
        has_node = row["has_node"]
        first_day = row["first_day"]
        last_day = row["last_day"]
        first_missing = not row["has_first"]
        last_missing = not row["has_last"]
        return cls(
            user_uid=row["user_uid"],
            has_node=has_node,
            fill_first=first_day if first_missing and first_day is not None else None,
            fill_last=last_day if last_missing and last_day is not None else None,
            unfillable=has_node and (first_missing or last_missing) and first_day is None,
            drops_retired_count=row["has_retired_count"],
        )

    @property
    def creates_node(self) -> bool:
        return not self.has_node and self.fill_first is not None

    @property
    def writes_anything(self) -> bool:
        return self.fill_first is not None or self.fill_last is not None or self.drops_retired_count


async def census(driver: AsyncDriver) -> tuple[list[StampPlan], int]:
    """Read-only survey: ``(one plan per in-scope user, nodes carrying the retired count)``."""
    records, _, _ = await driver.execute_query(CENSUS_QUERY, completed=COMPLETED)
    plans = [StampPlan.from_row(_to_census_row(record)) for record in records]
    retired, _, _ = await driver.execute_query(RETIRED_COUNT_QUERY)
    return plans, int(retired[0]["n"]) if retired else 0


def _print_census(plans: list[StampPlan], retired_nodes: int, *, confirm: bool) -> None:
    header = (
        "ProductivityAnalytics stamp backfill"
        if confirm
        else "ProductivityAnalytics stamp backfill — CENSUS (nothing written)"
    )
    print(f"\n=== {header} ===\n")
    firsts = sum(1 for p in plans if p.fill_first is not None)
    lasts = sum(1 for p in plans if p.fill_last is not None)
    print(
        f"  Users in scope         {len(plans):>6}   (have a node, or own a stamped completed task)"
    )
    print(f"  Stamps to fill         {firsts + lasts:>6}   first: {firsts}   last: {lasts}")
    print(
        f"  Nodes to create        {sum(1 for p in plans if p.creates_node):>6}   "
        "(stamped completions, no node — pre-cascade history)"
    )
    print(
        f"  Unfillable             {sum(1 for p in plans if p.unfillable):>6}   "
        "(node with a null stamp, no stamped completed task — left null)"
    )
    print(f"  Retired count to drop  {retired_nodes:>6}   node(s) still carrying tasks_completed")

    if not plans:
        print()
        return

    print(f"\n  {'user':<30} {'node':<6} {'first':<18} {'last':<18} retired")
    for plan in plans:
        first = (
            f"fill {plan.fill_first}" if plan.fill_first else ("—" if plan.unfillable else "keep")
        )
        last = f"fill {plan.fill_last}" if plan.fill_last else ("—" if plan.unfillable else "keep")
        if not plan.has_node and plan.fill_first is None:
            first = last = "—"
        print(
            f"  {plan.user_uid:<30} {'yes' if plan.has_node else 'no':<6} {first:<18} "
            f"{last:<18} {'drop' if plan.drops_retired_count else '-'}"
        )
    print()


async def run_backfill(driver: AsyncDriver, *, confirm: bool) -> int:
    """Census the stamps and, with --confirm, fill the nulls and drop the retired count."""
    plans, retired_nodes = await census(driver)
    _print_census(plans, retired_nodes, confirm=confirm)

    pending = any(p.writes_anything for p in plans) or retired_nodes > 0
    if not pending:
        print(
            "Nothing to backfill — every fillable stamp is set and no node carries the retired count."
        )
        return 0

    if not confirm:
        print("Census only. Re-run with --confirm to write.")
        return 0

    filled, _, _ = await driver.execute_query(BACKFILL_QUERY, completed=COMPLETED)
    if filled:
        print(
            f"✓ filled {int(filled[0]['first_filled'])} × first_completion_at, "
            f"{int(filled[0]['last_filled'])} × last_completion_at"
        )
    dropped, _, _ = await driver.execute_query(DROP_RETIRED_COUNT_QUERY)
    if dropped:
        print(f"✓ dropped tasks_completed from {int(dropped[0]['n'])} node(s)")

    # Prove the pass converged rather than asserting it.
    after, retired_after = await census(driver)
    remaining = sum(1 for p in after if p.fill_first is not None or p.fill_last is not None)
    if remaining or retired_after:
        print(
            f"\nFAILED: {remaining} fillable stamp(s) and {retired_after} retired count(s) "
            "remain after the write. Investigate before re-running.",
            file=sys.stderr,
        )
        return 1
    print("Verified: no fillable stamp is null and no node carries the retired count.")
    return 0


async def run_against_configured_graph(*, confirm: bool) -> int:
    """Connect to the configured Neo4j and run one pass."""
    from adapters.persistence.neo4j_adapter import Neo4jAdapter

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        return await run_backfill(adapter.get_driver(), confirm=confirm)
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write. Without it the run is a read-only census. The stamps "
            "written are a day-grained reconstruction from completed-task history "
            "and are not reversed by re-running; existing stamps are never moved."
        ),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_against_configured_graph(confirm=args.confirm)))


if __name__ == "__main__":
    main()
