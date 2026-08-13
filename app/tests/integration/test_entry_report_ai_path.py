"""Integration test: AI report generation wires through UserEntryBackend.

Verifies the canonical report-creation path end-to-end against a real Neo4j
instance. AI reports must get a SHARES_WITH edge from the entry owner
(student) to the report node, so they appear in the same student-visible
read path as teacher reports.

Cypher-level equivalent of that guarantee:

    MATCH (s:Entity {uid: $sub})<-[:REPORT_FOR]-(r:EntryReport)
    OPTIONAL MATCH (student:User)-[:SHARES_WITH]->(r)
    RETURN r.processor_type, r.assessment_outcome,
           student.uid IS NOT NULL AS shared

LLM is mocked — no API keys, no network. The Cypher + backend are real.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.exercise_backends import EntryReportBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.pipeline import ReportSource
from core.models.exercises.exercise import Exercise
from core.models.report.entry_report import EntryReport
from core.models.user_entry.user_entry import UserEntry
from core.services.report.entry_report_service import EntryReportService
from core.utils.result_simplified import Result

STUDENT_UID = "user_ai_report_student"
AUTHOR_UID = "user_ai_report_author"
SUBMISSION_UID = "ue_ai_report_integration_001"
EXERCISE_UID = "ex_ai_report_integration_001"


@pytest_asyncio.fixture
async def seeded_submission(neo4j_driver, clean_neo4j):
    """Seed the minimum graph needed by create_report_node.

    Creates:
      (student:User)
      (author:User)
      (submission:Entity:UserEntry {uid, status, pipeline})
      (student)-[:OWNS]->(submission)

    The OWNS edge is what create_report_node uses to discover the student
    and attach SHARES_WITH.
    """
    async with neo4j_driver.session() as session:
        await (
            await session.run(
                """
                MERGE (student:User {uid: $student_uid})
                MERGE (author:User {uid: $author_uid})
                CREATE (submission:Entity:UserEntry {
                    uid: $submission_uid,
                    title: 'Integration Submission',
                    entity_type: 'user_entry',
                    pipeline: 'teacher_review',
                    status: 'active',
                    user_uid: $student_uid,
                    content: 'Student work.',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (student)-[:OWNS]->(submission)
                """,
                student_uid=STUDENT_UID,
                author_uid=AUTHOR_UID,
                submission_uid=SUBMISSION_UID,
            )
        ).consume()

    yield

    async with neo4j_driver.session() as session:
        await (
            await session.run(
                """
                MATCH (u:User) WHERE u.uid IN [$student_uid, $author_uid]
                DETACH DELETE u
                """,
                student_uid=STUDENT_UID,
                author_uid=AUTHOR_UID,
            )
        ).consume()


@pytest_asyncio.fixture
async def entry_report_backend(neo4j_driver):
    return EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )


def _make_llm_caller(text: str = "AI-generated feedback body.") -> MagicMock:
    caller = MagicMock()
    caller.generate = AsyncMock(return_value=Result.ok(text))
    caller.get_supported_models = MagicMock(return_value={"anthropic": ["claude-sonnet-4-6"]})
    caller.is_model_supported = MagicMock(return_value=True)
    return caller


def _make_exercise() -> Exercise:
    return Exercise(
        uid=EXERCISE_UID,
        title="Week 3 Reflection",
        entity_type=EntityType.EXERCISE,
        instructions="Evaluate the student's reasoning.",
        model="claude-sonnet-4-6",
        path_step_uid="ps:test:week-3",  # PERSONAL scope requires a PathStep link
    )


def _make_submission() -> UserEntry:
    # Service only reads fields; the persisted node is what matters for Cypher.
    from core.models.enums.entity_enums import EntityStatus

    return UserEntry(
        uid=SUBMISSION_UID,
        title="Integration Submission",
        user_uid=STUDENT_UID,
        status=EntityStatus.ACTIVE,
        content="Student work.",
    )


@pytest.mark.asyncio
async def test_ai_report_creates_shares_with_edge_to_student(
    neo4j_driver,
    seeded_submission,
    entry_report_backend,
):
    """End-to-end: AI report is visible to the student via SHARES_WITH."""
    service = EntryReportService(
        llm_caller=_make_llm_caller("Detailed feedback body."),
        backend=entry_report_backend,
    )

    result = await service.generate_report(
        entry=_make_submission(),
        exercise=_make_exercise(),
        user_uid=AUTHOR_UID,
    )

    assert not result.is_error, result.error if result.is_error else None
    report_uid = result.value.uid

    async with neo4j_driver.session() as session:
        cursor = await session.run(
            """
            MATCH (s:Entity {uid: $sub})<-[:REPORT_FOR]-(r:Entity {uid: $rep})
            OPTIONAL MATCH (student:User)-[share:SHARES_WITH]->(r)
            OPTIONAL MATCH (owner:User)-[:OWNS]->(r)
            RETURN labels(r)           AS labels,
                   r.entity_type       AS entity_type,
                   r.title             AS title,
                   r.processor_type    AS processor_type,
                   r.assessment_outcome AS assessment_outcome,
                   r.processed_content AS content,
                   r.author_uid        AS author_uid,
                   student.uid         AS student_uid,
                   share.role          AS share_role,
                   owner.uid           AS owner_uid
            """,
            sub=SUBMISSION_UID,
            rep=report_uid,
        )
        record = await cursor.single()

    assert record is not None, "REPORT_FOR edge from report to submission is missing"
    # Multi-label assertion — typed reads via EntryReportBackend depend on
    # both labels being present on newly-created report nodes.
    labels = set(record["labels"])
    assert "Entity" in labels and "EntryReport" in labels, (
        f"Report node must carry both :Entity and :EntryReport labels, got {labels}"
    )
    assert record["entity_type"] == EntityType.ENTRY_REPORT.value
    assert record["processor_type"] == ReportSource.LLM.value
    assert record["assessment_outcome"] == AssessmentOutcome.AI_EVALUATED.value
    assert record["content"] == "Detailed feedback body."
    # C3 title composition: no FULFILLS_EXERCISE edge is seeded, so the
    # subject falls back to the submission's own title — never a raw UID.
    assert record["title"] == "AI feedback on 'Integration Submission'"

    # The behavioral fix: AI reports MUST be shared with the submission owner.
    assert record["student_uid"] == STUDENT_UID, (
        "AI report is not SHARES_WITH the student — students will not see it."
    )
    assert record["share_role"] == "student"

    # LLM-authored reports carry no human author (EntryReport contract) — the
    # triggerer is not the author. The OWNS edge, by contrast, always points at
    # the student so the report surfaces in the student's hub.
    assert record["author_uid"] is None
    assert record["owner_uid"] == STUDENT_UID


@pytest.mark.asyncio
async def test_ai_report_title_composed_from_fulfilled_exercise(
    neo4j_driver,
    seeded_submission,
    entry_report_backend,
):
    """C3: with a FULFILLS_EXERCISE edge present, the report title is composed
    from the exercise's title at creation — "AI feedback on '{exercise.title}'"."""
    async with neo4j_driver.session() as session:
        await (
            await session.run(
                """
                MATCH (submission:Entity {uid: $sub})
                CREATE (ex:Entity:Exercise {
                    uid: $ex_uid,
                    title: 'Week 3 Reflection',
                    entity_type: 'exercise'
                })
                CREATE (submission)-[:FULFILLS_EXERCISE]->(ex)
                """,
                sub=SUBMISSION_UID,
                ex_uid=EXERCISE_UID,
            )
        ).consume()

    service = EntryReportService(
        llm_caller=_make_llm_caller("Composed-title check."),
        backend=entry_report_backend,
    )
    result = await service.generate_report(
        entry=_make_submission(),
        exercise=_make_exercise(),
        user_uid=AUTHOR_UID,
    )
    assert not result.is_error, result.error if result.is_error else None
    # The service-side entity echoes the backend-composed title.
    assert result.value.title == "AI feedback on 'Week 3 Reflection'"

    async with neo4j_driver.session() as session:
        cursor = await session.run(
            "MATCH (r:EntryReport {uid: $uid}) RETURN r.title AS title",
            uid=result.value.uid,
        )
        record = await cursor.single()
    assert record is not None
    assert record["title"] == "AI feedback on 'Week 3 Reflection'"


@pytest.mark.asyncio
async def test_ai_report_is_discoverable_via_typed_read(
    neo4j_driver,
    seeded_submission,
    entry_report_backend,
):
    """The typed read path (EntryReportService.list_for_submission) is the
    canonical source of truth for report content after c703a596 — the former
    submission.report_content denormalization was dead weight and has been
    removed. AI reports must appear in the typed list with the expected body,
    and the AI path must leave submission.status unchanged."""
    service = EntryReportService(
        llm_caller=_make_llm_caller("Typed read check."),
        backend=entry_report_backend,
    )

    result = await service.generate_report(
        entry=_make_submission(),
        exercise=_make_exercise(),
        user_uid=AUTHOR_UID,
    )
    assert not result.is_error

    listed = await service.list_for_submission(SUBMISSION_UID)
    assert not listed.is_error, listed.error if listed.is_error else None
    reports = listed.value
    assert len(reports) == 1
    assert reports[0].processed_content == "Typed read check."
    # subject_uid is projected from the REPORT_FOR edge on read (not stored as
    # a node property). Without projection this silently hydrates to None and
    # breaks the student-subject branch of the ownership check in
    # entry_reports_ui.entry_report_detail.
    assert reports[0].subject_uid == SUBMISSION_UID

    # AI path passes submission_status=None → status must be unchanged.
    async with neo4j_driver.session() as session:
        cursor = await session.run(
            "MATCH (s:Entity {uid: $sub}) RETURN s.status AS status",
            sub=SUBMISSION_UID,
        )
        record = await cursor.single()
    assert record is not None
    assert record["status"] == "active"

    # Typed single-fetch: get hydrates subject_uid + all report fields.
    report_uid = reports[0].uid
    fetched = await service.get(report_uid)
    assert not fetched.is_error, fetched.error if fetched.is_error else None
    report = fetched.value
    assert isinstance(report, EntryReport)
    assert report.uid == report_uid
    assert report.subject_uid == SUBMISSION_UID
    assert report.assessment_outcome == AssessmentOutcome.AI_EVALUATED
    assert report.processed_content == "Typed read check."

    # Reports created via create_report_node must land with visibility='shared'
    # so UnifiedSharingService.check_access grants access to students who
    # follow the SHARES_WITH edge.
    async with neo4j_driver.session() as session:
        cursor = await session.run(
            "MATCH (r:EntryReport {uid: $uid}) RETURN r.visibility AS visibility",
            uid=report_uid,
        )
        record = await cursor.single()
    assert record is not None
    assert record["visibility"] == "shared"

    # get on a missing UID narrows to a not-found error.
    missing = await service.get("sr_does_not_exist")
    assert missing.is_error
