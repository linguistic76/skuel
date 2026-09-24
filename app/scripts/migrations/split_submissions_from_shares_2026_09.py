#!/usr/bin/env python3
"""
Split feedback requests from shares — SHARED_WITH_GROUP → SUBMITTED_TO_GROUP
=============================================================================

Re-types the group edges that are feedback requests onto their own kind,
``SUBMITTED_TO_GROUP`` (ADR-088 §2). A feedback request is read by the
teachers who own the group, under ``(teacher)-[:OWNS]->(group)``; a share,
``SHARED_WITH_GROUP``, is read by every member. Every teacher-side reader
reads the request kind, so a row still carrying the share kind is in no
queue until it is re-typed. Why the two kinds exist, and the leak the split
closes, is ADR-088's record and the Submit & Share arc's
(``docs/roadmap/submission-sharing-arc.md``, PR 1) — not repeated here.

What is re-typed, and why only that:

- **UserEntry edges on ``pipeline = 'teacher_review'``** — read as feedback
  requests: ``group:<uid>`` on a TEACHER_REVIEW entry is the per-teacher
  route (ADR-088 §8). The share kind records no intent, so this only narrows
  access; an owner who meant a class share re-shares through the share door.
  Every such row is listed for a person to confirm before ``--confirm``.
- **Every FormSubmission edge** — every form group target is a feedback
  request (ADR-088 §2).
- **UserEntry edges on any other pipeline are NOT touched, and an unruled
  one STOPS the run** (exit 2, before and regardless of ``--confirm``). An
  explicit ``group:`` share on ``none`` / ``llm_summary`` is a legitimate
  share, and the edge cannot say whether it was authored as one, so a person
  rules on each such row — delete it in the graph, or keep it as a share by
  naming it with ``--keep-share <entry_uid> <group_uid>`` (repeatable) —
  then re-runs. A kept row is excluded from the stop and left untouched. A
  ``--keep-share`` that names no unruled off-pipeline row is itself a stop
  (a stale ruling, or one aimed at a ``teacher_review`` row, which is always
  re-typed), so no ruling passes silently.

Re-typing is the no-APOC MERGE + copy + DELETE pattern
(``migrate_supports_habit_to_reinforces_habit_2026_08.cypher``): the request
kind is MERGEd (idempotent — a re-run after a partial failure is safe), the
share kind's ``shared_at`` becomes the request's ``submitted_at`` (the first
filing; an existing ``submitted_at`` wins), and the share kind is deleted.
``share_version`` is not carried: it is a share concept, ``'original'`` on
every row, and a feedback request has no versions.

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0 share-kind rows on
``teacher_review`` UserEntries and on FormSubmissions (the second census
catches rows the old code wrote in between).

The census also reports the acceptance count — classmate-visible turn-ins:
a ``MEMBER_OF`` member reaching a ``teacher_review`` entry it does not own
through the share kind — which reads 0 once the re-type has run.

Usage:
    uv run scripts/migrations/split_submissions_from_shares_2026_09.py            # census
    uv run scripts/migrations/split_submissions_from_shares_2026_09.py --confirm  # re-type
    uv run scripts/migrations/split_submissions_from_shares_2026_09.py \\
        --keep-share ue_abc group_xyz --confirm   # a ruled-legitimate share stays
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from neo4j import AsyncDriver

# One driver record, keyed by RETURN alias. Values are heterogeneous Neo4j
# scalars (strings, ints, temporal), so the value type is a boundary.
type Row = dict[str, Any]  # boundary: raw neo4j-driver record

_OLD = RelationshipName.SHARED_WITH_GROUP.value
_NEW = RelationshipName.SUBMITTED_TO_GROUP.value
_ENTITY = NeoLabel.ENTITY.value
_USER_ENTRY = NeoLabel.USER_ENTRY.value
_GROUP = NeoLabel.GROUP.value
_USER = NeoLabel.USER.value
_OWNS = RelationshipName.OWNS.value
_MEMBER_OF = RelationshipName.MEMBER_OF.value

# --- census ---------------------------------------------------------------

_USER_ENTRY_OLD_BY_PIPELINE = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})-[s:{_OLD}]->(g:{_GROUP})
RETURN coalesce(e.pipeline, '') AS pipeline, count(s) AS edges
ORDER BY pipeline
"""

_USER_ENTRY_OLD_ROWS = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})-[s:{_OLD}]->(g:{_GROUP})
RETURN e.uid AS uid, e.title AS title, coalesce(e.pipeline, '') AS pipeline,
       e.status AS status, e.user_uid AS owner, g.uid AS group_uid,
       toString(s.shared_at) AS shared_at, s.share_version AS share_version
ORDER BY pipeline, owner, title, group_uid
"""

_FORM_OLD_ROWS = f"""
MATCH (fs:{_ENTITY} {{entity_type: $form_submission}})-[s:{_OLD}]->(g:{_GROUP})
RETURN fs.uid AS uid, fs.title AS title, fs.user_uid AS owner, g.uid AS group_uid,
       toString(s.shared_at) AS shared_at, s.share_version AS share_version
ORDER BY owner, title, group_uid
"""

_NEW_COUNTS = f"""
MATCH (e:{_ENTITY})-[s:{_NEW}]->(:{_GROUP})
RETURN e.entity_type AS entity_type, count(s) AS edges
ORDER BY entity_type
"""

# The acceptance count: a group member (not the owner) who can reach a
# teacher_review turn-in through the share kind — the classmate leak.
_CLASSMATE_VISIBLE_TURN_INS = f"""
MATCH (viewer:{_USER})-[:{_MEMBER_OF}]->(g:{_GROUP})<-[:{_OLD}]-(e:{_ENTITY}:{_USER_ENTRY})
WHERE g.is_active = true
  AND e.pipeline = $teacher_review
  AND e.user_uid <> viewer.uid
RETURN count(DISTINCT e) AS turn_ins, count(DISTINCT viewer) AS viewers
"""

# --- write ----------------------------------------------------------------

_RETYPE_USER_ENTRY = f"""
MATCH (e:{_ENTITY}:{_USER_ENTRY})-[stale:{_OLD}]->(g:{_GROUP})
WHERE e.pipeline = $teacher_review
MERGE (e)-[fresh:{_NEW}]->(g)
SET fresh.submitted_at = coalesce(fresh.submitted_at, stale.shared_at, datetime())
DELETE stale
RETURN count(stale) AS edges_migrated
"""

_RETYPE_FORM = f"""
MATCH (fs:{_ENTITY} {{entity_type: $form_submission}})-[stale:{_OLD}]->(g:{_GROUP})
MERGE (fs)-[fresh:{_NEW}]->(g)
SET fresh.submitted_at = coalesce(fresh.submitted_at, stale.shared_at, datetime())
DELETE stale
RETURN count(stale) AS edges_migrated
"""


async def _fetch(driver: AsyncDriver, query: str, params: dict[str, str]) -> list[Row]:
    result = await driver.execute_query(query, params)
    return [dict(record) for record in result.records]


def _print_rows(heading: str, rows: list[Row]) -> None:
    print(f"\n{heading}: {len(rows)}")
    for row in rows:
        pipeline = f"  [{row['pipeline']}]" if "pipeline" in row else ""
        status = f"  status={row['status']}" if "status" in row else ""
        print(
            f"  {row['uid']}{pipeline}{status}  → {row['group_uid']}  "
            f"(owner {row['owner']}, shared {row['shared_at']}, "
            f"share_version {row['share_version']})  {row['title']!r}"
        )


async def _census(
    driver: AsyncDriver, kept: set[tuple[str, str]]
) -> tuple[list[Row], list[Row], list[Row]]:
    """Print the census; return (user-entry rows, form rows, unruled off-pipeline rows).

    ``kept`` holds the ``(entry_uid, group_uid)`` pairs a person ruled to be
    legitimate shares; they print as kept and are not counted as unruled.
    """
    params = {
        "form_submission": EntityType.FORM_SUBMISSION.value,
        "teacher_review": Pipeline.TEACHER_REVIEW.value,
    }
    by_pipeline = await _fetch(driver, _USER_ENTRY_OLD_BY_PIPELINE, params)
    print(f"UserEntry {_OLD} edges by pipeline:")
    if not by_pipeline:
        print("  (none)")
    for row in by_pipeline:
        print(f"  {row['pipeline'] or '<none>'}: {row['edges']}")
    ue_rows = await _fetch(driver, _USER_ENTRY_OLD_ROWS, params)
    _print_rows(f"UserEntry rows carrying {_OLD} (teacher_review rows are RE-TYPED)", ue_rows)
    off_pipeline = [r for r in ue_rows if r["pipeline"] != Pipeline.TEACHER_REVIEW.value]
    kept_rows = [r for r in off_pipeline if (str(r["uid"]), str(r["group_uid"])) in kept]
    unruled = [r for r in off_pipeline if (str(r["uid"]), str(r["group_uid"])) not in kept]
    if kept_rows:
        print(f"\nKept as shares (--keep-share, untouched): {len(kept_rows)}")
        for row in kept_rows:
            print(f"  {row['uid']}  [{row['pipeline']}]  → {row['group_uid']}")
    form_rows = await _fetch(driver, _FORM_OLD_ROWS, params)
    _print_rows(f"FormSubmission rows carrying {_OLD} (ALL are RE-TYPED)", form_rows)

    new_counts = await _fetch(driver, _NEW_COUNTS, params)
    print(f"\n{_NEW} edges by entity_type:")
    if not new_counts:
        print("  (none)")
    for row in new_counts:
        print(f"  {row['entity_type']}: {row['edges']}")

    leak = await _fetch(driver, _CLASSMATE_VISIBLE_TURN_INS, params)
    turn_ins = int(leak[0]["turn_ins"]) if leak else 0
    viewers = int(leak[0]["viewers"]) if leak else 0
    print(
        f"\nClassmate-visible turn-ins (a MEMBER_OF member reaching a teacher_review "
        f"entry it does not own through {_OLD}): {turn_ins} entries, {viewers} viewers"
    )
    return ue_rows, form_rows, unruled


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Re-type teacher_review UserEntry and all FormSubmission {_OLD} edges to {_NEW}"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the re-type (default is a census: print every row, change nothing)",
    )
    parser.add_argument(
        "--keep-share",
        nargs=2,
        action="append",
        default=[],
        metavar=("ENTRY_UID", "GROUP_UID"),
        help=(
            "An off-pipeline UserEntry edge a person ruled to be a legitimate share: "
            "excluded from the stop and left untouched (repeatable)"
        ),
    )
    args = parser.parse_args()
    kept: set[tuple[str, str]] = {(str(e), str(g)) for e, g in args.keep_share}

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        ue_rows, form_rows, unruled = await _census(driver, kept)

        # A keep ruling applies to an off-pipeline row only: a teacher_review
        # row is always re-typed, so a ruling aimed at one — or at a row that
        # carries no share-kind edge — must stop here, never pass into --confirm.
        off_pipeline_present = {
            (str(r["uid"]), str(r["group_uid"]))
            for r in ue_rows
            if r["pipeline"] != Pipeline.TEACHER_REVIEW.value
        }
        stale_keeps = sorted(kept - off_pipeline_present)
        if stale_keeps:
            print(
                f"\nSTOP: --keep-share names {len(stale_keeps)} row(s) that are not an "
                f"off-pipeline {_OLD} edge (a teacher_review row is always re-typed):"
            )
            for entry_uid, group_uid in stale_keeps:
                print(f"  {entry_uid} → {group_uid}")
            print("A ruling must name a live off-pipeline row. Nothing was written.")
            return 2

        if unruled:
            print(
                f"\nSTOP: {len(unruled)} UserEntry {_OLD} edge(s) sit on a pipeline other "
                "than teacher_review and carry no ruling. Those may be legitimate shares "
                "(an explicit 'group:' on none / llm_summary) or the old vault 'teachers' "
                "default — the row cannot say which. A person rules on each such row above: "
                "delete it in the graph, or keep it with --keep-share <entry_uid> <group_uid>; "
                "then re-run. Nothing was written."
            )
            return 2

        to_retype = [r for r in ue_rows if r["pipeline"] == Pipeline.TEACHER_REVIEW.value]
        print(
            f"\nWould re-type: {len(to_retype)} UserEntry edge(s) + {len(form_rows)} "
            f"FormSubmission edge(s) → {_NEW}"
        )
        if not args.confirm:
            print("\nCENSUS ONLY — nothing written. Re-run with --confirm to re-type.")
            return 0
        if not to_retype and not form_rows:
            print("\nNothing to re-type.")
            return 0

        params = {
            "form_submission": EntityType.FORM_SUBMISSION.value,
            "teacher_review": Pipeline.TEACHER_REVIEW.value,
        }
        ue_done = await _fetch(driver, _RETYPE_USER_ENTRY, params)
        form_done = await _fetch(driver, _RETYPE_FORM, params)
        ue_count = int(ue_done[0]["edges_migrated"]) if ue_done else 0
        form_count = int(form_done[0]["edges_migrated"]) if form_done else 0
        print(f"\nRe-typed {ue_count} UserEntry edge(s) and {form_count} FormSubmission edge(s).")

        print("\n=== AFTER ===")
        ue_after, form_after, _ = await _census(driver, kept)
        remaining = [r for r in ue_after if r["pipeline"] == Pipeline.TEACHER_REVIEW.value]
        if remaining or form_after:
            print(
                f"\nFAILED: {len(remaining)} teacher_review UserEntry and {len(form_after)} "
                f"FormSubmission {_OLD} edge(s) remain."
            )
            return 1
        print("\nOK: no teacher_review UserEntry or FormSubmission edge carries the old kind.")
        return 0
    finally:
        await driver.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
