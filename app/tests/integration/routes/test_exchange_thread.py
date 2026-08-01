"""The /exchange thread read — one (student, root exercise) chain, gated.

Pins the C5 contract (feedback-loop UX arc):

- The chain read returns the student's WHOLE exchange in one query: direct
  ``FULFILLS_EXERCISE`` turn-ins (with the edge revision), entries submitted
  against a revision (``FULFILLS_REVISED_EXERCISE``), the reports on those
  entries, and the revision requests responding to those reports.
- PRIVATE reports are excluded — a self-owned journal reflection is not part
  of the teacher↔student exchange (the C1 class rule).
- Scoping is per-student: another student's entries, reports, and revisions
  against the SAME exercise never leak into the thread.
- Teacher mode applies the Model B entry-level gate: only entries
  ``SHARED_WITH_GROUP`` an active group the viewer owns are in the chain, so
  a multi-class student's work directed to another teacher's classroom stays
  invisible even though both teachers pass the shared-group authority check.
- Not-found covers a missing exercise AND a student with no entries — an
  empty thread and a nonexistent one are indistinguishable.
- The orchestrator gate: the viewer reads their own exchange freely; another
  student's exchange requires a shared ACTIVE owned group (the report-download
  gate), and every denial collapses to not-found (404-not-403).

Run against a real Neo4j: the chain resolves against persisted edges and the
NULL-preserving OPTIONAL MATCH pipeline — a mocked backend would only assert
the query was issued, not that its collection algebra holds.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
from core.services.report.report_relationship_service import ReportRelationshipService
from core.services.report.teacher_review_service import TeacherReviewService

TEACHER = "user_ext_teacher"
SECOND_TEACHER = "user_ext_second_teacher"  # student's OTHER class
OTHER_TEACHER = "user_ext_other_teacher"  # no shared group with STUDENT
STUDENT = "user_ext_student"
OTHER_STUDENT = "user_ext_other_student"
GROUP_UID = "group_ext"
SECOND_GROUP_UID = "group_ext_second"  # STUDENT's other class
OTHER_GROUP_UID = "group_ext_other"

EX = "ex_ext_root"
E1 = "ue_ext_rev1"  # direct turn-in, revision 1
E2 = "ue_ext_rev2"  # direct turn-in, revision 2 — carries the reports
E3 = "ue_ext_via_revised"  # entry against the revision request
E_SECOND = "ue_ext_second_class"  # shared ONLY with SECOND_TEACHER's group
R_SHARED = "er_ext_shared"  # teacher feedback on E2 — in the thread
R_PRIVATE = "er_ext_private"  # self-owned journal reflection — excluded
REVISED = "re_ext_revision"  # revision request responding to R_SHARED
O_ENTRY = "ue_ext_other_student"  # other student, same exercise — excluded
O_REPORT = "er_ext_other_student"
O_REVISED = "re_ext_other_student"


@pytest.fixture
def relationship_service(neo4j_driver) -> ReportRelationshipService:
    """Real service over a real user_entry backend."""
    return ReportRelationshipService(backend=UserEntryBackend(driver=neo4j_driver))


@pytest.fixture
def orchestrator(neo4j_driver, relationship_service) -> UserEntryOrchestrator:
    """Orchestrator with only the two collaborators the exchange read touches.

    ``get_exchange_thread`` uses ``teacher_review_service`` (the authority
    gate) and ``report_relationship_service`` (the chain read); the other
    collaborators are never reached, so ``None`` is honest here.
    """
    review_service = TeacherReviewService(
        user_entry_backend=UserEntryBackend(driver=neo4j_driver),
        report_backend=None,  # type: ignore[arg-type]
        exercise_backend=None,  # type: ignore[arg-type]
        group_backend=None,  # type: ignore[arg-type]
        ku_interaction_service=None,  # type: ignore[arg-type]
        report_mastery_service=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    return UserEntryOrchestrator(
        user_entry_service=None,  # type: ignore[arg-type]
        exercises_service=None,  # type: ignore[arg-type]
        teacher_review_service=review_service,
        user_service=None,  # type: ignore[arg-type]
        activity_report_service=None,  # type: ignore[arg-type]
        revised_exercise_service=None,  # type: ignore[arg-type]
        entry_report_service=None,  # type: ignore[arg-type]
        sharing_service=None,  # type: ignore[arg-type]
        assessment_service=None,  # type: ignore[arg-type]
        report_relationship_service=relationship_service,
    )


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver) -> None:
    """One exchange for STUDENT plus a parallel one for OTHER_STUDENT.

    STUDENT's chain: rev-1 and rev-2 turn-ins, a shared teacher report and a
    PRIVATE reflection on rev 2, a revision request responding to the shared
    report, and a follow-up entry against that revision — all shared with
    TEACHER's group. STUDENT is multi-class: a fourth entry on the same
    exercise is shared ONLY with SECOND_TEACHER's group. OTHER_STUDENT has
    their own entry/report/revision on the SAME exercise — none of it may
    appear in STUDENT's thread. OTHER_TEACHER shares no group with STUDENT.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher})
            MERGE (st:User {uid: $second_teacher})
            MERGE (ot:User {uid: $other_teacher})
            MERGE (s:User {uid: $student})
            MERGE (os:User {uid: $other_student})
            MERGE (g:Group {uid: $group}) SET g.is_active = true
            MERGE (sg:Group {uid: $second_group}) SET sg.is_active = true
            MERGE (g2:Group {uid: $other_group}) SET g2.is_active = true
            MERGE (t)-[:OWNS]->(g)
            MERGE (st)-[:OWNS]->(sg)
            MERGE (ot)-[:OWNS]->(g2)
            MERGE (s)-[:MEMBER_OF]->(g)
            MERGE (s)-[:MEMBER_OF]->(sg)
            MERGE (os)-[:MEMBER_OF]->(g2)
            CREATE (ex:Entity:Exercise {
                uid: $ex, entity_type: 'exercise', title: 'Root exercise',
                status: 'active', created_at: datetime(), updated_at: datetime()
            })
            CREATE (e1:Entity:UserEntry {
                uid: $e1, entity_type: 'user_entry', title: 'Turn-in rev 1',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT4H'), updated_at: datetime()
            })
            CREATE (e2:Entity:UserEntry {
                uid: $e2, entity_type: 'user_entry', title: 'Turn-in rev 2',
                status: 'completed', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT3H'), updated_at: datetime()
            })
            CREATE (r1:Entity:EntryReport {
                uid: $r_shared, entity_type: 'entry_report', title: 'Feedback',
                status: 'completed', visibility: 'shared',
                processed_content: 'Good work',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (rp:Entity:EntryReport {
                uid: $r_private, entity_type: 'entry_report', title: 'Reflection',
                status: 'completed', visibility: 'private',
                content: 'My own notes',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (re:Entity:RevisedExercise {
                uid: $revised, entity_type: 'revised_exercise', title: 'Try again',
                status: 'active', revision_number: 2, instructions: 'Tighten it',
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            CREATE (e3:Entity:UserEntry {
                uid: $e3, entity_type: 'user_entry', title: 'Turn-in after revision',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT30M'), updated_at: datetime()
            })
            CREATE (esc:Entity:UserEntry {
                uid: $e_second, entity_type: 'user_entry', title: 'Second-class turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT20M'), updated_at: datetime()
            })
            CREATE (oe:Entity:UserEntry {
                uid: $o_entry, entity_type: 'user_entry', title: 'Other student turn-in',
                status: 'submitted', pipeline: 'teacher_review',
                created_at: datetime() - duration('PT4H'), updated_at: datetime()
            })
            CREATE (orep:Entity:EntryReport {
                uid: $o_report, entity_type: 'entry_report', title: 'Other feedback',
                status: 'completed', visibility: 'shared',
                processed_content: 'Different classroom',
                created_at: datetime() - duration('PT2H'), updated_at: datetime()
            })
            CREATE (ore:Entity:RevisedExercise {
                uid: $o_revised, entity_type: 'revised_exercise', title: 'Other revision',
                status: 'active', revision_number: 2,
                created_at: datetime() - duration('PT1H'), updated_at: datetime()
            })
            MERGE (s)-[:OWNS]->(e1)
            MERGE (s)-[:OWNS]->(e2)
            MERGE (s)-[:OWNS]->(e3)
            MERGE (s)-[:OWNS]->(esc)
            MERGE (s)-[:OWNS]->(r1)
            MERGE (s)-[:OWNS]->(rp)
            MERGE (os)-[:OWNS]->(oe)
            MERGE (os)-[:OWNS]->(orep)
            MERGE (e1)-[:FULFILLS_EXERCISE {revision: 1}]->(ex)
            MERGE (e2)-[:FULFILLS_EXERCISE {revision: 2}]->(ex)
            MERGE (esc)-[:FULFILLS_EXERCISE {revision: 3}]->(ex)
            MERGE (oe)-[:FULFILLS_EXERCISE {revision: 1}]->(ex)
            MERGE (e1)-[:SHARED_WITH_GROUP]->(g)
            MERGE (e2)-[:SHARED_WITH_GROUP]->(g)
            MERGE (e3)-[:SHARED_WITH_GROUP]->(g)
            MERGE (esc)-[:SHARED_WITH_GROUP]->(sg)
            MERGE (oe)-[:SHARED_WITH_GROUP]->(g2)
            MERGE (r1)-[:REPORT_FOR]->(e2)
            MERGE (rp)-[:REPORT_FOR]->(e2)
            MERGE (orep)-[:REPORT_FOR]->(oe)
            MERGE (re)-[:RESPONDS_TO_REPORT]->(r1)
            MERGE (re)-[:REVISES_EXERCISE]->(ex)
            MERGE (ore)-[:RESPONDS_TO_REPORT]->(orep)
            MERGE (ore)-[:REVISES_EXERCISE]->(ex)
            MERGE (e3)-[:FULFILLS_REVISED_EXERCISE]->(re)
            """,
            teacher=TEACHER,
            second_teacher=SECOND_TEACHER,
            other_teacher=OTHER_TEACHER,
            student=STUDENT,
            other_student=OTHER_STUDENT,
            group=GROUP_UID,
            second_group=SECOND_GROUP_UID,
            other_group=OTHER_GROUP_UID,
            ex=EX,
            e1=E1,
            e2=E2,
            e3=E3,
            e_second=E_SECOND,
            r_shared=R_SHARED,
            r_private=R_PRIVATE,
            revised=REVISED,
            o_entry=O_ENTRY,
            o_report=O_REPORT,
            o_revised=O_REVISED,
        )


class TestExchangeChainRead:
    """The chain read returns the whole exchange, correctly scoped."""

    async def test_chain_collects_all_three_artifact_kinds(
        self, relationship_service, seeded
    ) -> None:
        result = await relationship_service.get_exchange_thread(EX, STUDENT)
        assert result.is_ok, f"chain read failed: {result}"
        thread = result.value

        assert thread["exercise_uid"] == EX
        assert thread["exercise_title"] == "Root exercise"
        assert {e["uid"] for e in thread["entries"]} == {E1, E2, E3, E_SECOND}, (
            "the self view spans ALL the student's classes"
        )
        assert {r["uid"] for r in thread["reports"]} == {R_SHARED}
        assert {r["uid"] for r in thread["revisions"]} == {REVISED}

    async def test_entry_provenance_fields(self, relationship_service, seeded) -> None:
        """Direct turn-ins carry the edge revision; revision responses name it."""
        thread = (await relationship_service.get_exchange_thread(EX, STUDENT)).value
        by_uid = {e["uid"]: e for e in thread["entries"]}
        assert by_uid[E1]["revision"] == 1
        assert by_uid[E2]["revision"] == 2
        assert by_uid[E3]["revision"] is None
        assert by_uid[E3]["via_revised_uid"] == REVISED
        # Every created_at is an ISO string (toString emission) — mixed native
        # datetimes vs mapper strings must never reach the renderer.
        for item in [*thread["entries"], *thread["reports"], *thread["revisions"]]:
            assert isinstance(item["created_at"], str) and item["created_at"]

    async def test_private_report_is_excluded(self, relationship_service, seeded) -> None:
        """A PRIVATE self-owned reflection is not part of the exchange (C1 rule)."""
        thread = (await relationship_service.get_exchange_thread(EX, STUDENT)).value
        assert R_PRIVATE not in {r["uid"] for r in thread["reports"]}

    async def test_other_students_chain_never_leaks(self, relationship_service, seeded) -> None:
        thread = (await relationship_service.get_exchange_thread(EX, STUDENT)).value
        assert O_ENTRY not in {e["uid"] for e in thread["entries"]}
        assert O_REPORT not in {r["uid"] for r in thread["reports"]}
        assert O_REVISED not in {r["uid"] for r in thread["revisions"]}, (
            "revisions must be scoped through the chain's own reports"
        )

    async def test_missing_exercise_and_empty_thread_are_not_found(
        self, relationship_service, seeded
    ) -> None:
        missing = await relationship_service.get_exchange_thread("ex_ext_nope", STUDENT)
        assert missing.is_error
        never_submitted = await relationship_service.get_exchange_thread(EX, TEACHER)
        assert never_submitted.is_error, (
            "an exercise the student never submitted against reads as not-found"
        )


class TestExchangeAccessGate:
    """Viewer rules: self freely; another student only via a shared active group."""

    async def test_student_reads_own_exchange(self, orchestrator, seeded) -> None:
        result = await orchestrator.get_exchange_thread(viewer_uid=STUDENT, exercise_uid=EX)
        assert result.is_ok
        assert {e["uid"] for e in result.value["entries"]} == {E1, E2, E3, E_SECOND}

    async def test_group_teacher_reads_student_exchange(self, orchestrator, seeded) -> None:
        result = await orchestrator.get_exchange_thread(
            viewer_uid=TEACHER, exercise_uid=EX, student_uid=STUDENT
        )
        assert result.is_ok
        assert result.value["student_uid"] == STUDENT

    async def test_teacher_mode_scopes_to_own_classroom(self, orchestrator, seeded) -> None:
        """Multi-class student: each teacher sees only entries shared with THEIR group.

        Both teachers pass the shared-group authority check; the entry-level
        gate must still partition the chain — reports/revisions hang off the
        entries, so the second teacher sees neither of them either.
        """
        first = await orchestrator.get_exchange_thread(
            viewer_uid=TEACHER, exercise_uid=EX, student_uid=STUDENT
        )
        assert first.is_ok
        assert {e["uid"] for e in first.value["entries"]} == {E1, E2, E3}
        assert E_SECOND not in {e["uid"] for e in first.value["entries"]}

        second = await orchestrator.get_exchange_thread(
            viewer_uid=SECOND_TEACHER, exercise_uid=EX, student_uid=STUDENT
        )
        assert second.is_ok
        assert {e["uid"] for e in second.value["entries"]} == {E_SECOND}
        assert second.value["reports"] == []
        assert second.value["revisions"] == []

    async def test_unrelated_teacher_gets_not_found(self, orchestrator, seeded) -> None:
        """No shared active group → the same not-found a missing exercise yields."""
        result = await orchestrator.get_exchange_thread(
            viewer_uid=OTHER_TEACHER, exercise_uid=EX, student_uid=STUDENT
        )
        assert result.is_error
        assert "not found" in result.expect_error().message.lower()
