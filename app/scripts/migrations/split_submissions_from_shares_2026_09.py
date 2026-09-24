#!/usr/bin/env python3
"""
Split feedback requests from shares — SHARED_WITH_GROUP → SUBMITTED_TO_GROUP
=============================================================================

Submit & Share arc PR 1 (ADR-088 §2). Until this PR one edge,
``SHARED_WITH_GROUP``, meant both "for my teacher" (the review queue read it
under the teacher's ``OWNS``) and "for my class" (the groups hub read it under
a member's ``MEMBER_OF``), so every turn-in sent to a teacher was listed to
the whole group. The new code writes a feedback request as its own kind,
``SUBMITTED_TO_GROUP``, and every teacher-side reader now reads that kind —
so the rows the old code wrote must be re-typed, or the queue goes empty.

What is re-typed, and why only that:

- **UserEntry edges on ``pipeline = 'teacher_review'``** — read as feedback
  requests (Refinement 2: ``group:<uid>`` on TEACHER_REVIEW *was* the
  per-teacher route). The old edge records no intent, so this only narrows
  access: an owner who meant a class share re-shares through the share door
  (PR 6b). Every such row is listed for a person to confirm before
  ``--confirm``.
- **Every FormSubmission edge** — every form group target is a feedback
  request (ADR-088 §2).
- **UserEntry edges on any other pipeline are NOT touched, and their
  presence FAILS the run** (exit 2, before and regardless of ``--confirm``).
  An explicit ``group:`` share on ``none`` / ``llm_summary`` is a legitimate
  share, and a row made before PR 1 cannot be traced to its source (the
  vault ``teachers`` default of the time, or an explicit ``group:``), so a
  non-zero count is a stop-and-look: a person rules on those rows, then
  re-runs. Live 2026-09-24: 0 such rows.

Re-typing is the no-APOC MERGE + copy + DELETE pattern
(``migrate_supports_habit_to_reinforces_habit_2026_08.cypher``): the new edge
is MERGEd (idempotent — a re-run after a partial failure is safe), the old
edge's ``shared_at`` becomes the request's ``submitted_at`` (the first filing;
an existing ``submitted_at`` wins), and the old edge is deleted.
``share_version`` is not carried: it is a share concept, ``'original'`` on
every live row, and a feedback request has no versions.

Deploy order (the arc's Migrations convention): stop the running app →
census (this script, no flag) → ``--confirm`` with Mike's OK → start on the
new code → census again, which must report 0 old-kind rows on both labels
(the second census catches rows the old code wrote in between).

The census also reports the acceptance count — classmate-visible turn-ins:
a ``MEMBER_OF`` member reaching a ``teacher_review`` entry it does not own
through ``SHARED_WITH_GROUP`` — which reads 0 once the re-type has run.

Usage:
    uv run scripts/migrations/split_submissions_from_shares_2026_09.py            # census
    uv run scripts/migrations/split_submissions_from_shares_2026_09.py --confirm  # re-type
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName

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


async def _fetch(driver: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await driver.execute_query(query, params)
    return [dict(record) for record in result.records]


def _print_rows(heading: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n{heading}: {len(rows)}")
    for row in rows:
        pipeline = f"  [{row['pipeline']}]" if "pipeline" in row else ""
        status = f"  status={row['status']}" if "status" in row else ""
        print(
            f"  {row['uid']}{pipeline}{status}  → {row['group_uid']}  "
            f"(owner {row['owner']}, shared {row['shared_at']}, "
            f"share_version {row['share_version']})  {row['title']!r}"
        )


async def _census(driver: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Print the census; return (user-entry rows, form rows, off-pipeline count)."""
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
    off_pipeline = sum(
        int(row["edges"]) for row in by_pipeline if row["pipeline"] != Pipeline.TEACHER_REVIEW.value
    )

    ue_rows = await _fetch(driver, _USER_ENTRY_OLD_ROWS, params)
    _print_rows(f"UserEntry rows carrying {_OLD} (teacher_review rows are RE-TYPED)", ue_rows)
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
    return ue_rows, form_rows, off_pipeline


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Re-type teacher_review UserEntry and all FormSubmission {_OLD} edges to {_NEW}"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write the re-type (default is a census: print every row, change nothing)",
    )
    args = parser.parse_args()

    from adapters.persistence.neo4j.neo4j_connection import Neo4jConnection

    driver = Neo4jConnection().connect()
    try:
        print("=== BEFORE ===")
        ue_rows, form_rows, off_pipeline = await _census(driver)

        if off_pipeline:
            print(
                f"\nSTOP: {off_pipeline} UserEntry {_OLD} edge(s) sit on a pipeline other "
                "than teacher_review. Those may be legitimate shares (an explicit "
                "'group:' on none / llm_summary) or the old vault 'teachers' default — "
                "the row cannot say which. A person rules on each row above (keep it "
                "as a share, or delete it), then re-runs. Nothing was written."
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
        ue_after, form_after, _ = await _census(driver)
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
