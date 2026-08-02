"""The GradeBook summary read — one line per exchange, one query (arc 2 C1+C2).

Pins the ``get_student_exchange_summaries`` contract:

- One summary row per root exercise the student has lineage entries against —
  direct ``FULFILLS_EXERCISE`` turn-ins + resubmits via
  ``FULFILLS_REVISED_EXERCISE`` → ``REVISES_EXERCISE`` (the exchange-thread
  lineage lens). A resubmit carrying ONLY the revised edge still rolls up to
  its root exercise.
- Latest-entry pick is by ``created_at`` — a later resubmit (no edge revision)
  outranks an earlier numbered direct turn-in.
- Status derivation: ``revision_requested`` on the latest entry wins even
  when that entry has a report; otherwise report-on-latest-entry →
  feedback_received; otherwise waiting.
- PRIVATE reports never count anywhere (received-feedback class rule).
- Another student's entries/reports on the SAME exercise never leak.
- ``other_feedback`` carries received reports outside any exchange (report on
  an entry with no lineage, or on no entry at all), newest first.
- Lines come back newest-activity-first (entry vs report stamps, naive=UTC).

Run against a real Neo4j: entry ``created_at`` is seeded as ISO STRINGS (the
mapper's storage form) while report stamps are native datetimes — the exact
mixed-type emission the query's ``toString()`` boundary exists for.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.enums.pipeline import ExchangeStatus
from core.services.report.report_relationship_service import ReportRelationshipService

STUDENT = "user_sum_student"
OTHER = "user_sum_other"

EX_A = "ex_sum_a"  # one waiting turn-in
EX_B = "ex_sum_b"  # feedback received (+ excluded private report)
EX_C = "ex_sum_c"  # revision requested (report exists but revision wins)
EX_D = "ex_sum_d"  # resubmit via revised edge only → waiting again


@pytest.fixture
def service(neo4j_driver) -> ReportRelationshipService:
    """Real service over a real user_entry backend."""
    return ReportRelationshipService(backend=UserEntryBackend(driver=neo4j_driver))


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    """Four exchanges for STUDENT + non-lineage reports + a parallel student.

    Entry ``created_at`` values are ISO strings (mapper storage form);
    report/revision stamps are native datetimes at fixed instants so the
    newest-activity ordering is deterministic: C (05:30Z) > A (04:00) >
    D (03:00) > B (02:00Z).
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (s:User {uid: $student})
            MERGE (o:User {uid: $other})
            CREATE (exa:Entity:Exercise {uid: $ex_a, entity_type: 'exercise',
                title: 'Alpha', status: 'active', created_at: datetime()})
            CREATE (exb:Entity:Exercise {uid: $ex_b, entity_type: 'exercise',
                title: 'Bravo', status: 'active', created_at: datetime()})
            CREATE (exc:Entity:Exercise {uid: $ex_c, entity_type: 'exercise',
                title: 'Charlie', status: 'active', created_at: datetime()})
            CREATE (exd:Entity:Exercise {uid: $ex_d, entity_type: 'exercise',
                title: 'Delta', status: 'active', created_at: datetime()})

            // A: one waiting turn-in
            CREATE (a1:Entity:UserEntry {uid: 'ue_sum_a1', entity_type: 'user_entry',
                title: 'A turn-in', status: 'submitted',
                created_at: '2026-08-01T04:00:00.000000'})
            MERGE (s)-[:OWNS]->(a1)
            MERGE (a1)-[:FULFILLS_EXERCISE {revision: 1}]->(exa)

            // B: feedback received; the private reflection must count nowhere
            CREATE (b1:Entity:UserEntry {uid: 'ue_sum_b1', entity_type: 'user_entry',
                title: 'B turn-in', status: 'completed',
                created_at: '2026-08-01T01:00:00.000000'})
            CREATE (rb:Entity:EntryReport {uid: 'er_sum_rb', entity_type: 'entry_report',
                title: 'B feedback', status: 'completed', visibility: 'shared',
                processor_type: 'human',
                created_at: datetime('2026-08-01T02:00:00Z')})
            CREATE (rbp:Entity:EntryReport {uid: 'er_sum_rbp', entity_type: 'entry_report',
                title: 'B private reflection', status: 'completed', visibility: 'private',
                processor_type: 'llm',
                created_at: datetime('2026-08-01T02:30:00Z')})
            MERGE (s)-[:OWNS]->(b1)
            MERGE (s)-[:OWNS]->(rb)
            MERGE (s)-[:OWNS]->(rbp)
            MERGE (b1)-[:FULFILLS_EXERCISE {revision: 1}]->(exb)
            MERGE (rb)-[:REPORT_FOR]->(b1)
            MERGE (rbp)-[:REPORT_FOR]->(b1)

            // C: revision requested on the latest entry — wins over its report
            CREATE (c1:Entity:UserEntry {uid: 'ue_sum_c1', entity_type: 'user_entry',
                title: 'C turn-in', status: 'revision_requested',
                created_at: '2026-08-01T05:00:00.000000'})
            CREATE (rc:Entity:EntryReport {uid: 'er_sum_rc', entity_type: 'entry_report',
                title: 'C revision request', status: 'completed', visibility: 'shared',
                processor_type: 'human',
                created_at: datetime('2026-08-01T05:30:00Z')})
            MERGE (s)-[:OWNS]->(c1)
            MERGE (s)-[:OWNS]->(rc)
            MERGE (c1)-[:FULFILLS_EXERCISE {revision: 1}]->(exc)
            MERGE (rc)-[:REPORT_FOR]->(c1)

            // D: resubmit via the revised edge ONLY — waiting again
            CREATE (d1:Entity:UserEntry {uid: 'ue_sum_d1', entity_type: 'user_entry',
                title: 'D turn-in', status: 'revision_requested',
                created_at: '2026-08-01T00:00:00.000000'})
            CREATE (rd:Entity:EntryReport {uid: 'er_sum_rd', entity_type: 'entry_report',
                title: 'D revision request', status: 'completed', visibility: 'shared',
                processor_type: 'human',
                created_at: datetime('2026-08-01T00:30:00Z')})
            CREATE (red:Entity:RevisedExercise {uid: 're_sum_red',
                entity_type: 'revised_exercise', title: 'D try again', status: 'active',
                revision_number: 2, created_at: datetime('2026-08-01T00:45:00Z')})
            CREATE (d2:Entity:UserEntry {uid: 'ue_sum_d2', entity_type: 'user_entry',
                title: 'D resubmit', status: 'submitted',
                created_at: '2026-08-01T03:00:00.000000'})
            MERGE (s)-[:OWNS]->(d1)
            MERGE (s)-[:OWNS]->(rd)
            MERGE (s)-[:OWNS]->(d2)
            MERGE (d1)-[:FULFILLS_EXERCISE {revision: 1}]->(exd)
            MERGE (rd)-[:REPORT_FOR]->(d1)
            MERGE (red)-[:RESPONDS_TO_REPORT]->(rd)
            MERGE (red)-[:REVISES_EXERCISE]->(exd)
            MERGE (d2)-[:FULFILLS_REVISED_EXERCISE]->(red)

            // Received feedback OUTSIDE any exchange
            CREATE (pe:Entity:UserEntry {uid: 'ue_sum_plain', entity_type: 'user_entry',
                title: 'Plain journal entry', status: 'completed',
                created_at: '2026-07-30T10:00:00.000000'})
            CREATE (rp:Entity:EntryReport {uid: 'er_sum_plain', entity_type: 'entry_report',
                title: 'Journal response', status: 'completed', visibility: 'shared',
                processor_type: 'human',
                created_at: datetime('2026-07-30T12:00:00Z')})
            CREATE (rpp:Entity:EntryReport {uid: 'er_sum_plain_priv',
                entity_type: 'entry_report', title: 'Private journal note',
                status: 'completed', visibility: 'private', processor_type: 'llm',
                created_at: datetime('2026-07-30T13:00:00Z')})
            CREATE (rfree:Entity:EntryReport {uid: 'er_sum_free', entity_type: 'entry_report',
                title: 'Detached report', status: 'completed', visibility: 'shared',
                processor_type: 'llm',
                created_at: datetime('2026-07-31T12:00:00Z')})
            MERGE (s)-[:OWNS]->(pe)
            MERGE (s)-[:OWNS]->(rp)
            MERGE (s)-[:OWNS]->(rpp)
            MERGE (s)-[:OWNS]->(rfree)
            MERGE (rp)-[:REPORT_FOR]->(pe)
            MERGE (rpp)-[:REPORT_FOR]->(pe)

            // Parallel student on the same exercise — must never leak
            CREATE (o1:Entity:UserEntry {uid: 'ue_sum_o1', entity_type: 'user_entry',
                title: 'Other turn-in', status: 'completed',
                created_at: '2026-08-01T06:00:00.000000'})
            CREATE (ro:Entity:EntryReport {uid: 'er_sum_ro', entity_type: 'entry_report',
                title: 'Other feedback', status: 'completed', visibility: 'shared',
                processor_type: 'human',
                created_at: datetime('2026-08-01T06:30:00Z')})
            MERGE (o)-[:OWNS]->(o1)
            MERGE (o)-[:OWNS]->(ro)
            MERGE (o1)-[:FULFILLS_EXERCISE {revision: 1}]->(exa)
            MERGE (ro)-[:REPORT_FOR]->(o1)
            """,
            student=STUDENT,
            other=OTHER,
            ex_a=EX_A,
            ex_b=EX_B,
            ex_c=EX_C,
            ex_d=EX_D,
        )


class TestExchangeSummaries:
    async def test_one_line_per_exercise_newest_activity_first(self, service, seeded) -> None:
        result = await service.get_student_exchange_summaries(STUDENT)
        assert result.is_ok, f"summary read failed: {result}"
        rows = result.value["exercises"]
        assert [r["exercise_uid"] for r in rows] == [EX_C, EX_A, EX_D, EX_B], (
            "lines must order by latest activity (entry vs report stamps, naive=UTC)"
        )

    async def test_status_derivation_covers_all_three_states(self, service, seeded) -> None:
        rows = (await service.get_student_exchange_summaries(STUDENT)).value["exercises"]
        by_ex = {r["exercise_uid"]: r for r in rows}
        assert by_ex[EX_A]["exchange_status"] == ExchangeStatus.WAITING.value
        assert by_ex[EX_B]["exchange_status"] == ExchangeStatus.FEEDBACK_RECEIVED.value
        assert by_ex[EX_C]["exchange_status"] == ExchangeStatus.REVISION_REQUESTED.value, (
            "revision_requested wins even though the latest entry has a report"
        )
        assert by_ex[EX_D]["exchange_status"] == ExchangeStatus.WAITING.value, (
            "a resubmit with no report is waiting again"
        )

    async def test_resubmit_via_revised_edge_is_the_latest_entry(self, service, seeded) -> None:
        """created_at picks the resubmit over the numbered direct turn-in."""
        rows = (await service.get_student_exchange_summaries(STUDENT)).value["exercises"]
        d = next(r for r in rows if r["exercise_uid"] == EX_D)
        assert d["latest_entry_uid"] == "ue_sum_d2"
        assert d["entry_count"] == 2
        assert d["report_count"] == 1
        assert d["latest_report_uid"] is None, (
            "the report sits on the superseded entry, not the latest one"
        )

    async def test_private_reports_count_nowhere(self, service, seeded) -> None:
        rows = (await service.get_student_exchange_summaries(STUDENT)).value["exercises"]
        b = next(r for r in rows if r["exercise_uid"] == EX_B)
        assert b["report_count"] == 1
        assert b["latest_report_uid"] == "er_sum_rb"
        assert b["latest_report_source"] == "human"

    async def test_other_students_work_never_leaks(self, service, seeded) -> None:
        rows = (await service.get_student_exchange_summaries(STUDENT)).value["exercises"]
        a = next(r for r in rows if r["exercise_uid"] == EX_A)
        assert a["entry_count"] == 1
        assert a["report_count"] == 0
        assert a["latest_entry_uid"] == "ue_sum_a1"

    async def test_other_feedback_carries_non_lineage_reports_only(self, service, seeded) -> None:
        other = (await service.get_student_exchange_summaries(STUDENT)).value["other_feedback"]
        assert [r["uid"] for r in other] == ["er_sum_free", "er_sum_plain"], (
            "newest first; exchange reports and private reports excluded"
        )

    async def test_empty_student_gets_empty_lists_not_an_error(self, service, seeded) -> None:
        result = await service.get_student_exchange_summaries(OTHER)
        assert result.is_ok
        # OTHER has an exchange of their own (their entry on EX_A) but no
        # non-lineage feedback.
        assert [r["exercise_uid"] for r in result.value["exercises"]] == [EX_A]
        assert result.value["other_feedback"] == []
        nobody = await service.get_student_exchange_summaries("user_sum_ghost")
        assert nobody.is_ok
        assert nobody.value["exercises"] == []
        assert nobody.value["other_feedback"] == []
