"""The turn-in snapshot backfill — census, stamp, and what it leaves alone.

The queries are **imported from the script**
(``scripts/migrations/backfill_turn_in_exercise_snapshot_2026_09.py``), not
retyped: a copy would drift from what actually runs against AuraDB.

Pins the root resolution per source (Submit & Share arc PR 4a):

- a direct ``FULFILLS_EXERCISE`` edge to a live Exercise → that exercise;
- a direct edge to a RevisedExercise whose original is gone but named by
  ``original_exercise_uid`` → the original's uid, the revision's title;
- a ``FULFILLS_REVISED_EXERCISE`` edge only → the revision's
  ``REVISES_EXERCISE`` original;
- no edge, the retained ``fulfills_exercise_uid`` property and an
  ``Interaction`` trace (the exercise was deleted before the snapshot
  existed) → the property, resolved through a live RevisedExercise's
  ``original_exercise_uid``; with no live node at all, the placeholder title;
- a declared-intent-only entry (property, no edge, no trace — a living vault
  note) is listed and never stamped;
- an entry that already carries the snapshot is not a candidate;
- the second census after the stamp reads 0.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.models.user_entry.user_entry import EXERCISE_REMOVED_TITLE

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "backfill_turn_in_exercise_snapshot_2026_09.py"
)


def _load_migration():
    """Import the migration module by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("backfill_turn_in_exercise_snapshot", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()

STUDENT = "user_bf_student"
EX_LIVE = "ex_bf_live"
EX_ROOT_OF_RE = "ex_bf_root_of_re"
EX_GONE_ORIG = "ex_bf_gone_original"  # named by a revision's property, no node
RE_ORPHAN = "re_bf_orphan"  # revision whose original is gone
RE_LIVE = "re_bf_live"  # revision with a live REVISES_EXERCISE original
RE_BY_PROP = "re_bf_by_prop"  # live revision a property names; original gone
E_DIRECT = "ue_bf_direct"
E_DIRECT_RE = "ue_bf_direct_re"
E_REVISED_ONLY = "ue_bf_revised_only"
E_PROP_RE = "ue_bf_prop_re"
E_PROP_GONE = "ue_bf_prop_gone"
E_INTENT_ONLY = "ue_bf_intent_only"
E_STAMPED = "ue_bf_stamped"


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (s:User {uid: $student})
            CREATE (exl:Entity:Exercise {uid: $ex_live, entity_type: 'exercise', title: 'Live'})
            CREATE (exr:Entity:Exercise {uid: $ex_root, entity_type: 'exercise', title: 'Root'})
            CREATE (reo:Entity:RevisedExercise {uid: $re_orphan, entity_type: 'revised_exercise',
                title: 'Orphan revision', original_exercise_uid: $ex_gone_orig})
            CREATE (rel:Entity:RevisedExercise {uid: $re_live, entity_type: 'revised_exercise',
                title: 'Live revision', original_exercise_uid: $ex_root})
            CREATE (rep:Entity:RevisedExercise {uid: $re_by_prop, entity_type: 'revised_exercise',
                title: 'Named revision', original_exercise_uid: $ex_gone_orig})
            MERGE (rel)-[:REVISES_EXERCISE]->(exr)

            CREATE (d:Entity:UserEntry {uid: $e_direct, entity_type: 'user_entry',
                title: 'direct', pipeline: 'teacher_review', user_uid: $student})
            CREATE (dr:Entity:UserEntry {uid: $e_direct_re, entity_type: 'user_entry',
                title: 'direct to orphan revision', pipeline: 'teacher_review', user_uid: $student})
            CREATE (ro:Entity:UserEntry {uid: $e_revised_only, entity_type: 'user_entry',
                title: 'revised edge only', pipeline: 'teacher_review', user_uid: $student})
            CREATE (pr:Entity:UserEntry {uid: $e_prop_re, entity_type: 'user_entry',
                title: 'property names a live revision', pipeline: 'llm_summary',
                user_uid: $student, fulfills_exercise_uid: $re_by_prop})
            CREATE (pg:Entity:UserEntry {uid: $e_prop_gone, entity_type: 'user_entry',
                title: 'property names nothing live', pipeline: 'llm_summary',
                user_uid: $student, fulfills_exercise_uid: 'ex_bf_vanished'})
            CREATE (io:Entity:UserEntry {uid: $e_intent_only, entity_type: 'user_entry',
                title: 'living vault note', pipeline: 'none',
                user_uid: $student, fulfills_exercise_uid: $ex_live})
            CREATE (st:Entity:UserEntry {uid: $e_stamped, entity_type: 'user_entry',
                title: 'already stamped', pipeline: 'teacher_review', user_uid: $student,
                turn_in_exercise_uid: $ex_live, turn_in_exercise_title: 'Live (as submitted)'})
            MERGE (s)-[:OWNS]->(d) MERGE (s)-[:OWNS]->(dr) MERGE (s)-[:OWNS]->(ro)
            MERGE (s)-[:OWNS]->(pr) MERGE (s)-[:OWNS]->(pg) MERGE (s)-[:OWNS]->(io)
            MERGE (s)-[:OWNS]->(st)
            MERGE (d)-[:FULFILLS_EXERCISE {revision: 1}]->(exl)
            MERGE (st)-[:FULFILLS_EXERCISE {revision: 2}]->(exl)
            MERGE (dr)-[:FULFILLS_EXERCISE {revision: 1}]->(reo)
            MERGE (ro)-[:FULFILLS_REVISED_EXERCISE {revision: 1}]->(rel)
            // The turn-in trace: an Interaction records a frozen copy, never a living note
            CREATE (i1:Entity:Interaction {uid: 'int_bf_1', entity_type: 'interaction'})
            CREATE (i2:Entity:Interaction {uid: 'int_bf_2', entity_type: 'interaction'})
            MERGE (i1)-[:RECORDS]->(pr)
            MERGE (i2)-[:RECORDS]->(pg)
            """,
            student=STUDENT,
            ex_live=EX_LIVE,
            ex_root=EX_ROOT_OF_RE,
            ex_gone_orig=EX_GONE_ORIG,
            re_orphan=RE_ORPHAN,
            re_live=RE_LIVE,
            re_by_prop=RE_BY_PROP,
            e_direct=E_DIRECT,
            e_direct_re=E_DIRECT_RE,
            e_revised_only=E_REVISED_ONLY,
            e_prop_re=E_PROP_RE,
            e_prop_gone=E_PROP_GONE,
            e_intent_only=E_INTENT_ONLY,
            e_stamped=E_STAMPED,
        )


async def _snapshots(neo4j_driver) -> dict[str, tuple[str | None, str | None]]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Entity:UserEntry)
            RETURN e.uid AS uid, e.turn_in_exercise_uid AS ex, e.turn_in_exercise_title AS title
            """
        )
        return {r["uid"]: (r["ex"], r["title"]) async for r in result}


class TestCensus:
    async def test_candidates_are_the_turn_ins_only(self, neo4j_driver, seeded, capsys) -> None:
        candidates, intent_only = await migration.census(neo4j_driver)
        assert {r["uid"] for r in candidates} == {
            E_DIRECT,
            E_DIRECT_RE,
            E_REVISED_ONLY,
            E_PROP_RE,
            E_PROP_GONE,
        }
        assert [r["uid"] for r in intent_only] == [E_INTENT_ONLY]
        by_uid = {r["uid"]: r for r in candidates}
        assert by_uid[E_DIRECT]["source"] == "edge"
        assert by_uid[E_REVISED_ONLY]["source"] == "revised_edge"
        assert by_uid[E_PROP_GONE]["source"] == "property"
        assert by_uid[E_PROP_GONE]["title_is_placeholder"] is True
        assert by_uid[E_PROP_GONE]["root_live"] is False
        out = capsys.readouterr().out
        assert "left untouched" in out


class TestBackfill:
    async def test_roots_resolve_per_source_and_the_rest_is_untouched(
        self, neo4j_driver, seeded
    ) -> None:
        assert await migration.backfill(neo4j_driver) == 5
        snaps = await _snapshots(neo4j_driver)
        assert snaps[E_DIRECT] == (EX_LIVE, "Live")
        assert snaps[E_DIRECT_RE] == (EX_GONE_ORIG, "Orphan revision"), (
            "a revision whose original is gone resolves to the original's uid it names; "
            "the revision's title is the best remaining title"
        )
        assert snaps[E_REVISED_ONLY] == (EX_ROOT_OF_RE, "Root")
        assert snaps[E_PROP_RE] == (EX_GONE_ORIG, "Named revision"), (
            "the property resolves through the live revision's original_exercise_uid"
        )
        assert snaps[E_PROP_GONE] == ("ex_bf_vanished", EXERCISE_REMOVED_TITLE)
        assert snaps[E_INTENT_ONLY] == (None, None), "a living vault note is not a turn-in"
        assert snaps[E_STAMPED] == (EX_LIVE, "Live (as submitted)"), (
            "an existing snapshot is never rewritten"
        )

    async def test_second_census_reads_zero(self, neo4j_driver, seeded) -> None:
        await migration.backfill(neo4j_driver)
        candidates, intent_only = await migration.census(neo4j_driver)
        assert candidates == []
        assert [r["uid"] for r in intent_only] == [E_INTENT_ONLY]
        assert await migration.backfill(neo4j_driver) == 0, "the stamp is idempotent"
