#!/usr/bin/env python3
"""
Vault notes are drafts — copy provenance first-class, no links on a living note
===============================================================================

Submit & Share arc PR 8 (R9): a vault note is a draft, never submitted or
shared; ``status: submitted`` files a frozen copy, and only the copy carries
an audience. Two things the old code left in the graph change meaning:

1. **Copy provenance.** A frozen copy recorded the living note it came from
   inside its ``metadata`` JSON (the ``submitted_from_entry`` key). The new
   code reads only the first-class ``submitted_from_uid`` property — the
   vault door's dedup and the review queue's supersede rule key on it, with
   no fallback to the old key (a fallback would be a second provenance
   authority hiding an incomplete migration). ``--confirm`` moves every key
   onto the property and removes it from ``metadata``. A copy migrated here
   carries no ``submission_fingerprint``: if its note still says
   ``status: submitted``, the next sync files one fresh copy.
2. **Links on living notes.** A living vault note (``metadata`` carries
   ``vault_file_path``) holds no audience link on the new code — drafts are
   never shared, and a re-sync never retracts one. ``--confirm`` deletes
   every ``SHARED_WITH_GROUP`` from, and every ``SHARES_WITH`` to, a living
   note. A ``SUBMITTED_TO_GROUP`` on a living note is a feedback request a
   teacher may be reviewing: it is reported and blocks ``--confirm`` until a
   person rules on it — never deleted here.

Reported, never written: living ``teacher_review`` notes (the new vault door
refuses the pipeline — the author edits the note), and turn-ins that carry a
``vault_file_path`` (the retired first-sync path; the note's next sync mints
a fresh living node instead of reusing one).

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must read 0 old keys and 0 links on living
notes. The second census catches rows the old code wrote in between.

Usage:
    uv run scripts/migrations/vault_notes_are_drafts_2026_09.py            # census
    uv run scripts/migrations/vault_notes_are_drafts_2026_09.py --confirm  # write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, temporal), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

OLD_KEY = "submitted_from_entry"
_VAULT_KEY = "vault_file_path"

_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_USER = NeoLabel.USER.value
_GROUP = NeoLabel.GROUP.value
_SHARED_WITH_GROUP = RelationshipName.SHARED_WITH_GROUP.value
_SHARES_WITH = RelationshipName.SHARES_WITH.value
_SUBMITTED_TO_GROUP = RelationshipName.SUBMITTED_TO_GROUP.value
_FULFILLS = RelationshipName.FULFILLS_EXERCISE.value

# A CONTAINS pre-filter keeps the read small; every row is then confirmed by a
# structured JSON parse (``_metadata``), never by the substring.
_OLD_KEY_ROWS = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.metadata CONTAINS $old_key
RETURN e.uid AS uid, e.title AS title, e.metadata AS metadata,
       e.submitted_from_uid AS submitted_from_uid
ORDER BY uid
"""

_LIVING_LINKS = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.metadata CONTAINS $vault_key
CALL (e) {{
  MATCH (e)-[:{_SHARED_WITH_GROUP}]->(g:{_GROUP})
  RETURN $group_share AS kind, g.uid AS target
  UNION
  MATCH (u:{_USER})-[:{_SHARES_WITH}]->(e)
  RETURN $person_share AS kind, u.uid AS target
  UNION
  MATCH (e)-[:{_SUBMITTED_TO_GROUP}]->(g:{_GROUP})
  RETURN $feedback_request AS kind, g.uid AS target
}}
RETURN e.uid AS uid, e.title AS title, e.pipeline AS pipeline, e.metadata AS metadata,
       kind, target
ORDER BY kind, uid, target
"""

_LIVING_TEACHER_REVIEW = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})
WHERE e.metadata CONTAINS $vault_key AND e.pipeline = $teacher_review
RETURN e.uid AS uid, e.title AS title, e.status AS status, e.metadata AS metadata
ORDER BY uid
"""

_VAULT_TURN_INS = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})-[:{_FULFILLS}]->()
WHERE e.metadata CONTAINS $vault_key
RETURN DISTINCT e.uid AS uid, e.title AS title, e.metadata AS metadata
ORDER BY uid
"""

# Guarded on the metadata read at census time: a row changed since is not
# rewritten from a stale copy (it reports 0 and fails the run).
_MOVE_KEY = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY} {{uid: $uid}})
WHERE e.metadata = $old_metadata
SET e.submitted_from_uid = $source, e.metadata = $new_metadata
RETURN count(e) AS moved
"""

_DELETE_GROUP_SHARE = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY} {{uid: $uid}})-[s:{_SHARED_WITH_GROUP}]->(:{_GROUP} {{uid: $target}})
DELETE s
RETURN count(s) AS removed
"""

_DELETE_PERSON_SHARE = f"""
MATCH (:{_USER} {{uid: $target}})-[s:{_SHARES_WITH}]->(e:{_ENTITY}:{_USER_ENTRY} {{uid: $uid}})
DELETE s
RETURN count(s) AS removed
"""


def _metadata(raw: Any) -> dict[str, Any] | None:
    """The persisted ``metadata`` JSON string as a mapping, or None when it is not one."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_living(row: Row) -> bool:
    parsed = _metadata(row.get("metadata"))
    return parsed is not None and bool(parsed.get(_VAULT_KEY))


async def _fetch(driver: AsyncDriver, query: str, params: dict[str, Any] | None = None) -> list[Row]:
    result = await driver.execute_query(query, params or {})
    return [dict(record) for record in result.records]


class Census:
    """What the graph holds for this migration, read once."""

    def __init__(
        self,
        old_keys: list[Row],
        conflicts: list[Row],
        share_links: list[Row],
        feedback_requests: list[Row],
        living_teacher_review: list[Row],
        vault_turn_ins: list[Row],
    ) -> None:
        self.old_keys = old_keys
        self.conflicts = conflicts
        self.share_links = share_links
        self.feedback_requests = feedback_requests
        self.living_teacher_review = living_teacher_review
        self.vault_turn_ins = vault_turn_ins

    @property
    def clean(self) -> bool:
        return not (self.old_keys or self.conflicts or self.share_links or self.feedback_requests)


async def _census(driver: AsyncDriver) -> Census:
    """Print the census and return it."""
    old_keys: list[Row] = []
    conflicts: list[Row] = []
    for row in await _fetch(driver, _OLD_KEY_ROWS, {"old_key": OLD_KEY}):
        parsed = _metadata(row["metadata"])
        if parsed is None or OLD_KEY not in parsed:
            continue  # the substring sat in some other value
        row["source"] = str(parsed[OLD_KEY])
        existing = row.get("submitted_from_uid")
        (conflicts if existing not in (None, row["source"]) else old_keys).append(row)
    print(f"\nCopies carrying the old metadata key '{OLD_KEY}' (ALL are moved): {len(old_keys)}")
    for row in old_keys:
        print(f"  {row['uid']}  from={row['source']}  title={row['title']!r}")
    if conflicts:
        print(f"\nSTOP — the old key disagrees with submitted_from_uid: {len(conflicts)}")
        for row in conflicts:
            print(
                f"  {row['uid']}  metadata={row['source']}  "
                f"submitted_from_uid={row['submitted_from_uid']}"
            )

    links = [
        row
        for row in await _fetch(
            driver,
            _LIVING_LINKS,
            {
                "vault_key": _VAULT_KEY,
                "group_share": _SHARED_WITH_GROUP,
                "person_share": _SHARES_WITH,
                "feedback_request": _SUBMITTED_TO_GROUP,
            },
        )
        if _is_living(row)
    ]
    share_links = [row for row in links if row["kind"] != _SUBMITTED_TO_GROUP]
    feedback_requests = [row for row in links if row["kind"] == _SUBMITTED_TO_GROUP]
    print(f"\nShare links on living vault notes (ALL are retracted): {len(share_links)}")
    for row in share_links:
        print(
            f"  {row['kind']}  {row['uid']} ↔ {row['target']}  "
            f"[{row['pipeline']}]  title={row['title']!r}"
        )
    print(f"\nFeedback requests on living vault notes (STOP — a person rules): {len(feedback_requests)}")
    for row in feedback_requests:
        print(f"  {row['uid']} → {row['target']}  [{row['pipeline']}]  title={row['title']!r}")

    living_tr = [
        row
        for row in await _fetch(
            driver,
            _LIVING_TEACHER_REVIEW,
            {"vault_key": _VAULT_KEY, "teacher_review": Pipeline.TEACHER_REVIEW.value},
        )
        if _is_living(row)
    ]
    print(f"\nLiving teacher_review notes (report only — the door now refuses them): {len(living_tr)}")
    for row in living_tr:
        print(f"  {row['uid']}  status={row['status']}  title={row['title']!r}")

    turn_ins = [
        row
        for row in await _fetch(driver, _VAULT_TURN_INS, {"vault_key": _VAULT_KEY})
        if _is_living(row)
    ]
    print(f"\nTurn-ins carrying a vault_file_path (report only — never a living identity): {len(turn_ins)}")
    for row in turn_ins:
        print(f"  {row['uid']}  title={row['title']!r}")

    return Census(old_keys, conflicts, share_links, feedback_requests, living_tr, turn_ins)


async def _move_keys(driver: AsyncDriver, rows: list[Row]) -> list[str]:
    failures: list[str] = []
    for row in rows:
        parsed = _metadata(row["metadata"]) or {}
        remaining = {k: v for k, v in parsed.items() if k != OLD_KEY}
        done = await _fetch(
            driver,
            _MOVE_KEY,
            {
                "uid": row["uid"],
                "old_metadata": row["metadata"],
                "new_metadata": json.dumps(remaining),
                "source": row["source"],
            },
        )
        if not done or int(done[0]["moved"]) != 1:
            failures.append(f"{row['uid']} (metadata changed since the census)")
    return failures


async def _retract(driver: AsyncDriver, rows: list[Row]) -> list[str]:
    failures: list[str] = []
    for row in rows:
        query = _DELETE_GROUP_SHARE if row["kind"] == _SHARED_WITH_GROUP else _DELETE_PERSON_SHARE
        done = await _fetch(driver, query, {"uid": row["uid"], "target": row["target"]})
        if not done or int(done[0]["removed"]) != 1:
            failures.append(f"{row['kind']} {row['uid']} ↔ {row['target']}")
    return failures


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move copy provenance onto submitted_from_uid; retract links on living vault notes"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        census = await _census(driver)
        print(
            f"\nWould move: {len(census.old_keys)} key(s); "
            f"would retract: {len(census.share_links)} link(s)"
        )
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to write.")
            return 0
        if census.conflicts or census.feedback_requests:
            print("\nREFUSED — resolve every STOP row above first; nothing was written.")
            return 1
        if census.clean:
            print("\nNothing to do.")
            return 0

        failures = await _move_keys(driver, census.old_keys)
        failures += await _retract(driver, census.share_links)

        print("\n=== AFTER ===")
        after = await _census(driver)
        if failures or not after.clean:
            print("\nFAILED:")
            for line in failures:
                print(f"  {line}")
            return 1
        print("\nOK: no copy carries the old key; no living vault note carries a link.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
