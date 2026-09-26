"""The derived review standing (Submit & Share arc PR 6c, R2) — one derivation on a real graph.

``build_review_standing_subquery`` derives the "reviewed" badges: an entry is
*reviewed* when an outcome-bearing report stands on it, and *revised after
feedback* when an earlier entry of the same owner in the same exchange
(``turn_in_exercise_uid``) carries such a report older than this entry. Run
against a real Neo4j because the predicate crosses the two stamp shapes the
writers produce — ``UserEntry.created_at`` an ISO string (the mapper),
``EntryReport.created_at`` a native datetime — and a raw ``<`` between them is
NULL: a never-matching predicate that a mocked backend could not expose.

    e1  string stamp 00:00, report r1 (human, 01:00Z) → reviewed · Teacher, not revised
    e2  string stamp 02:00, no report                 → revised after feedback (r1 < e2)
    e3  NATIVE stamp 03:00Z, human 03:30Z + AI 04:00Z → reviewed · AI (newest), revised
    t2  the trap: its prior's report is NEWER than t2 → NOT revised
    j1  an outcome-less report only                   → unreviewed
    x1  another owner reviewed earlier in the exchange → NOT revised (same owner only)
    p1  not a turn-in, reviewed                       → reviewed, never revised
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.services.report.report_relationship_service import ReportRelationshipService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

OWNER = "user_rsr_owner"
OTHER = "user_rsr_other"
EX = "ex_rsr_main"
EX_TRAP = "ex_rsr_trap"
EX_CROSS = "ex_rsr_cross"


@pytest.fixture
def service(neo4j_driver) -> ReportRelationshipService:
    return ReportRelationshipService(backend=UserEntryBackend(driver=neo4j_driver))


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (o:User {uid: $owner})
            MERGE (x:User {uid: $other})

            // the main exchange: e1 (reviewed) → e2 (revised) → e3 (native stamp, reviewed twice)
            CREATE (e1:Entity:UserEntry {uid: 'ue_rsr_e1', entity_type: 'user_entry',
                title: 'first', status: 'completed', user_uid: $owner,
                turn_in_exercise_uid: $ex, turn_in_exercise_title: 'Main',
                created_at: '2026-08-01T00:00:00.000000'})
            CREATE (r1:Entity:EntryReport {uid: 'er_rsr_r1', entity_type: 'entry_report',
                title: 'r1', status: 'completed', processor_type: 'human',
                assessment_outcome: 'needs_revision', created_at: datetime('2026-08-01T01:00:00Z')})
            CREATE (e2:Entity:UserEntry {uid: 'ue_rsr_e2', entity_type: 'user_entry',
                title: 'second', status: 'submitted', user_uid: $owner,
                turn_in_exercise_uid: $ex, turn_in_exercise_title: 'Main',
                created_at: '2026-08-01T02:00:00.000000'})
            CREATE (e3:Entity:UserEntry {uid: 'ue_rsr_e3', entity_type: 'user_entry',
                title: 'third', status: 'completed', user_uid: $owner,
                turn_in_exercise_uid: $ex, turn_in_exercise_title: 'Main',
                created_at: datetime('2026-08-01T03:00:00Z')})
            CREATE (r3h:Entity:EntryReport {uid: 'er_rsr_r3h', entity_type: 'entry_report',
                title: 'r3 human', status: 'completed', processor_type: 'human',
                assessment_outcome: 'approved', created_at: datetime('2026-08-01T03:30:00Z')})
            CREATE (r3a:Entity:EntryReport {uid: 'er_rsr_r3a', entity_type: 'entry_report',
                title: 'r3 ai', status: 'completed', processor_type: 'llm',
                assessment_outcome: 'ai_evaluated', created_at: datetime('2026-08-01T04:00:00Z')})
            MERGE (o)-[:OWNS]->(e1) MERGE (o)-[:OWNS]->(e2) MERGE (o)-[:OWNS]->(e3)
            MERGE (o)-[:OWNS]->(r1) MERGE (o)-[:OWNS]->(r3h) MERGE (o)-[:OWNS]->(r3a)
            MERGE (r1)-[:REPORT_FOR]->(e1)
            MERGE (r3h)-[:REPORT_FOR]->(e3)
            MERGE (r3a)-[:REPORT_FOR]->(e3)

            // the trap exchange: the prior's report is dated AFTER the later entry
            CREATE (t1:Entity:UserEntry {uid: 'ue_rsr_t1', entity_type: 'user_entry',
                title: 'trap first', status: 'completed', user_uid: $owner,
                turn_in_exercise_uid: $ex_trap, turn_in_exercise_title: 'Trap',
                created_at: '2026-08-02T00:00:00.000000'})
            CREATE (t2:Entity:UserEntry {uid: 'ue_rsr_t2', entity_type: 'user_entry',
                title: 'trap second', status: 'submitted', user_uid: $owner,
                turn_in_exercise_uid: $ex_trap, turn_in_exercise_title: 'Trap',
                created_at: '2026-08-02T01:00:00.000000'})
            CREATE (rt:Entity:EntryReport {uid: 'er_rsr_rt', entity_type: 'entry_report',
                title: 'late report on t1', status: 'completed', processor_type: 'human',
                assessment_outcome: 'approved', created_at: datetime('2026-08-02T02:00:00Z')})
            MERGE (o)-[:OWNS]->(t1) MERGE (o)-[:OWNS]->(t2) MERGE (o)-[:OWNS]->(rt)
            MERGE (rt)-[:REPORT_FOR]->(t1)

            // an outcome-less report (a journal reflection) reviews nothing
            CREATE (j1:Entity:UserEntry {uid: 'ue_rsr_j1', entity_type: 'user_entry',
                title: 'journal', status: 'completed', user_uid: $owner,
                created_at: '2026-08-03T00:00:00.000000'})
            CREATE (rj:Entity:EntryReport {uid: 'er_rsr_rj', entity_type: 'entry_report',
                title: 'reflection', status: 'completed', processor_type: 'llm',
                created_at: datetime('2026-08-03T01:00:00Z')})
            MERGE (o)-[:OWNS]->(j1) MERGE (o)-[:OWNS]->(rj)
            MERGE (rj)-[:REPORT_FOR]->(j1)

            // another owner reviewed earlier in the same exchange — not the owner's revision
            CREATE (xo:Entity:UserEntry {uid: 'ue_rsr_xo', entity_type: 'user_entry',
                title: 'other first', status: 'completed', user_uid: $other,
                turn_in_exercise_uid: $ex_cross, turn_in_exercise_title: 'Cross',
                created_at: '2026-08-04T00:00:00.000000'})
            CREATE (rx:Entity:EntryReport {uid: 'er_rsr_rx', entity_type: 'entry_report',
                title: 'other report', status: 'completed', processor_type: 'human',
                assessment_outcome: 'approved', created_at: datetime('2026-08-04T01:00:00Z')})
            CREATE (x1:Entity:UserEntry {uid: 'ue_rsr_x1', entity_type: 'user_entry',
                title: 'mine later', status: 'submitted', user_uid: $owner,
                turn_in_exercise_uid: $ex_cross, turn_in_exercise_title: 'Cross',
                created_at: '2026-08-04T02:00:00.000000'})
            MERGE (x)-[:OWNS]->(xo) MERGE (x)-[:OWNS]->(rx) MERGE (o)-[:OWNS]->(x1)
            MERGE (rx)-[:REPORT_FOR]->(xo)

            // reviewed work that is not a turn-in can never be "revised after feedback"
            CREATE (p1:Entity:UserEntry {uid: 'ue_rsr_p1', entity_type: 'user_entry',
                title: 'plain', status: 'completed', user_uid: $owner,
                created_at: '2026-08-05T00:00:00.000000'})
            CREATE (rp:Entity:EntryReport {uid: 'er_rsr_rp', entity_type: 'entry_report',
                title: 'plain report', status: 'completed', processor_type: 'human',
                assessment_outcome: 'approved', created_at: datetime('2026-08-05T01:00:00Z')})
            MERGE (o)-[:OWNS]->(p1) MERGE (o)-[:OWNS]->(rp)
            MERGE (rp)-[:REPORT_FOR]->(p1)
            """,
            owner=OWNER,
            other=OTHER,
            ex=EX,
            ex_trap=EX_TRAP,
            ex_cross=EX_CROSS,
        )


async def _standing(service: ReportRelationshipService, uid: str):
    result = await service.get_entry_review_standing(uid)
    assert result.is_ok, result.error
    return result.value


class TestReviewStanding:
    async def test_a_reviewed_first_entry_is_reviewed_and_not_revised(self, service, seeded):
        assert await _standing(service, "ue_rsr_e1") == {
            "reviewed_by": "human",
            "revised_after_feedback": False,
        }

    async def test_a_later_entry_after_the_report_is_revised_after_feedback(self, service, seeded):
        """The stamp trap crossed: a string entry stamp against a native report stamp."""
        assert await _standing(service, "ue_rsr_e2") == {
            "reviewed_by": None,
            "revised_after_feedback": True,
        }

    async def test_a_native_entry_stamp_derives_the_same_way_and_the_newest_report_names_the_source(
        self, service, seeded
    ):
        assert await _standing(service, "ue_rsr_e3") == {
            "reviewed_by": "llm",
            "revised_after_feedback": True,
        }

    async def test_a_report_written_after_the_later_entry_does_not_make_it_a_revision(
        self, service, seeded
    ):
        assert await _standing(service, "ue_rsr_t2") == {
            "reviewed_by": None,
            "revised_after_feedback": False,
        }

    async def test_an_outcome_less_report_reviews_nothing(self, service, seeded):
        assert await _standing(service, "ue_rsr_j1") == {
            "reviewed_by": None,
            "revised_after_feedback": False,
        }

    async def test_another_owners_review_in_the_exchange_is_not_mine(self, service, seeded):
        assert await _standing(service, "ue_rsr_x1") == {
            "reviewed_by": None,
            "revised_after_feedback": False,
        }

    async def test_reviewed_work_outside_any_exchange_is_never_revised(self, service, seeded):
        assert await _standing(service, "ue_rsr_p1") == {
            "reviewed_by": "human",
            "revised_after_feedback": False,
        }

    async def test_a_uid_naming_no_entry_reads_none(self, service, seeded):
        assert await _standing(service, "ue_rsr_missing") is None
