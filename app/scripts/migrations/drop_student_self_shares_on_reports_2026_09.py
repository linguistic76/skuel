#!/usr/bin/env python3
"""
Drop the student's self-share on their own EntryReports
=======================================================

An EntryReport is owned by the student it is about (``user_uid`` + ``OWNS``)
and is read as an owner read (ADR-088 §3). The report writers once also
wrote ``(student)-[:SHARES_WITH]->(report)`` — a share link from the owner
to their own node — which put the student's own feedback on the Shared page
beside other people's work. Feedback lives in the GradeBook, never on the
Shared page (Submit & Share arc R3), and the writers no longer create the
edge; this script deletes the ones that stand. Why is ADR-088's record and
the arc's (``docs/roadmap/submission-sharing-arc.md``, PR 6b) — not
repeated here.

What is deleted, and why only that:

- **Every ``SHARES_WITH`` from a user to an EntryReport they own**
  (``report.user_uid = user.uid``). The edge grants its owner nothing they do
  not already have, and nothing reads it (the Shared page lists user
  entries and form submissions only).
- **Nothing else.** The RevisedExercise → student grant is a share from the
  teacher-owned revision to the student (not a self-share) and stays; a
  ``SHARES_WITH`` from a non-owner to a report would be a real share and is
  reported, never touched (there are none — ADR-040 never shared a report
  with a non-owner).

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0. The second census is the
invariant check: the old code wrote the self-share unconditionally, so a
non-zero count means a report was written between the delete and the restart.

Usage:
    uv run scripts/migrations/drop_student_self_shares_on_reports_2026_09.py            # census
    uv run scripts/migrations/drop_student_self_shares_on_reports_2026_09.py --confirm  # delete
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, temporal), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_REPORT = NeoLabel.ENTRY_REPORT.value
_USER = NeoLabel.USER.value
_SHARES_WITH = RelationshipName.SHARES_WITH.value

# --- census ---------------------------------------------------------------

_SELF_SHARE_ROWS = f"""
MATCH (u:{_USER})-[r:{_SHARES_WITH}]->(fb:{_REPORT})
WHERE fb.user_uid = u.uid
RETURN fb.uid AS report_uid, u.uid AS student, r.role AS role, toString(r.shared_at) AS shared_at
ORDER BY shared_at
"""

_OTHER_SHARE_ROWS = f"""
MATCH (u:{_USER})-[r:{_SHARES_WITH}]->(fb:{_REPORT})
WHERE fb.user_uid IS NULL OR fb.user_uid <> u.uid
RETURN fb.uid AS report_uid, u.uid AS recipient, fb.user_uid AS owner, r.role AS role
ORDER BY report_uid
"""

# --- write ----------------------------------------------------------------

_DELETE_SELF_SHARES = f"""
MATCH (u:{_USER})-[r:{_SHARES_WITH}]->(fb:{_REPORT})
WHERE fb.user_uid = u.uid
DELETE r
RETURN count(r) AS edges_deleted
"""


async def _fetch(driver: AsyncDriver, query: str) -> list[Row]:
    result = await driver.execute_query(query)
    return [dict(record) for record in result.records]


async def _census(driver: AsyncDriver) -> list[Row]:
    """Print the census; return the self-share rows (the ones the write deletes)."""
    self_rows = await _fetch(driver, _SELF_SHARE_ROWS)
    print(f"\nStudent self-shares on their own EntryReports (ALL are deleted): {len(self_rows)}")
    for row in self_rows:
        print(
            f"  {row['report_uid']}  student={row['student']}  role={row['role']}  "
            f"shared_at={row['shared_at']}"
        )
    other_rows = await _fetch(driver, _OTHER_SHARE_ROWS)
    print(f"\nSHARES_WITH from a non-owner to an EntryReport (reported, NEVER touched): {len(other_rows)}")
    for row in other_rows:
        print(
            f"  {row['report_uid']}  recipient={row['recipient']}  owner={row['owner']}  "
            f"role={row['role']}"
        )
    return self_rows


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete every student's SHARES_WITH on their own EntryReports (R3)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the delete (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        self_rows = await _census(driver)
        print(f"\nWould delete: {len(self_rows)} self-share edge(s)")
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to delete.")
            return 0
        if not self_rows:
            print("\nNothing to delete.")
            return 0

        done = await _fetch(driver, _DELETE_SELF_SHARES)
        deleted = int(done[0]["edges_deleted"]) if done else 0
        print(f"\nDeleted {deleted} self-share edge(s).")

        print("\n=== AFTER ===")
        remaining = await _census(driver)
        if remaining:
            print(f"\nFAILED: {len(remaining)} self-share edge(s) remain.")
            return 1
        print("\nOK: no student holds a SHARES_WITH on their own EntryReport.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
