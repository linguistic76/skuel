"""Integration test: AI report generation wires through SubmissionsBackend.

Verifies the canonical report-creation path end-to-end against a real Neo4j
instance. Covers the behavioral fix from plans/steady-swimming-axolotl.md
Step 1: AI reports must get a SHARES_WITH edge from the submission owner
(student) to the report node, so they appear in the same student-visible
read path as teacher reports.

Cypher-level equivalent of Verification step 3 from the plan:

    MATCH (s:Entity {uid: $sub})<-[:REPORT_FOR]-(r:ExerciseReport)
    OPTIONAL MATCH (student:User)-[:SHARES_WITH]->(r)
    RETURN r.processor_type, r.assessment_outcome,
           student.uid IS NOT NULL AS shared

LLM is mocked — no API keys, no network. The Cypher + backend are real.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.submissions_backend import SubmissionsBackend
from core.models.enums.entity_enums import EntityType, ProcessorType
from core.models.enums.learning_enums import AssessmentOutcome
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.models.submissions.exercise_submission import ExerciseSubmission
from core.models.submissions.submission import Submission
from core.services.report.exercise_report_service import ExerciseReportService
from core.utils.result_simplified import Result

STUDENT_UID = "user_ai_report_student"
AUTHOR_UID = "user_ai_report_author"
SUBMISSION_UID = "es_ai_report_integration_001"
EXERCISE_UID = "ex_ai_report_integration_001"


@pytest_asyncio.fixture
async def seeded_submission(neo4j_driver, clean_neo4j):
    """Seed the minimum graph needed by create_report_node.

    Creates:
      (student:User)
      (author:User)
      (submission:Entity:ExerciseSubmission {uid, status})
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
                CREATE (submission:Entity:ExerciseSubmission {
                    uid: $submission_uid,
                    title: 'Integration Submission',
                    entity_type: 'exercise_submission',
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
async def submissions_backend(neo4j_driver):
    return SubmissionsBackend(neo4j_driver, NeoLabel.ENTITY, Submission)


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
    )


def _make_submission() -> ExerciseSubmission:
    # Service only reads fields; the persisted node is what matters for Cypher.
    from core.models.enums.entity_enums import EntityStatus

    return ExerciseSubmission(
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
    submissions_backend,
):
    """End-to-end: AI report is visible to the student via SHARES_WITH."""
    service = ExerciseReportService(
        llm_caller=_make_llm_caller("Detailed feedback body."),
        submissions_backend=submissions_backend,
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
            OPTIONAL MATCH (author:User)-[:OWNS]->(r)
            RETURN labels(r)           AS labels,
                   r.entity_type       AS entity_type,
                   r.processor_type    AS processor_type,
                   r.assessment_outcome AS assessment_outcome,
                   r.content           AS content,
                   student.uid         AS student_uid,
                   share.role          AS share_role,
                   author.uid          AS author_uid
            """,
            sub=SUBMISSION_UID,
            rep=report_uid,
        )
        record = await cursor.single()

    assert record is not None, "REPORT_FOR edge from report to submission is missing"
    # Multi-label assertion — typed reads via ExerciseReportBackend depend on
    # both labels being present on newly-created report nodes.
    labels = set(record["labels"])
    assert "Entity" in labels and "ExerciseReport" in labels, (
        f"Report node must carry both :Entity and :ExerciseReport labels, got {labels}"
    )
    assert record["entity_type"] == EntityType.EXERCISE_REPORT.value
    assert record["processor_type"] == ProcessorType.LLM.value
    assert record["assessment_outcome"] == AssessmentOutcome.AI_EVALUATED.value
    assert record["content"] == "Detailed feedback body."

    # The behavioral fix: AI reports MUST be shared with the submission owner.
    assert record["student_uid"] == STUDENT_UID, (
        "AI report is not SHARES_WITH the student — students will not see it."
    )
    assert record["share_role"] == "student"

    # Symmetric with teacher reports: author owns the report node.
    assert record["author_uid"] == AUTHOR_UID


@pytest.mark.asyncio
async def test_ai_report_denormalizes_feedback_onto_submission(
    neo4j_driver,
    seeded_submission,
    submissions_backend,
):
    """create_report_node also writes report_content onto the submission for
    quick list display. AI path must trigger this same denormalization."""
    service = ExerciseReportService(
        llm_caller=_make_llm_caller("Denorm check."),
        submissions_backend=submissions_backend,
    )

    result = await service.generate_report(
        entry=_make_submission(),
        exercise=_make_exercise(),
        user_uid=AUTHOR_UID,
    )
    assert not result.is_error

    async with neo4j_driver.session() as session:
        cursor = await session.run(
            """
            MATCH (s:Entity {uid: $sub})
            RETURN s.report_content       AS report_content,
                   s.report_generated_at  AS report_generated_at,
                   s.status               AS status
            """,
            sub=SUBMISSION_UID,
        )
        record = await cursor.single()

    assert record is not None
    assert record["report_content"] == "Denorm check."
    assert record["report_generated_at"] is not None
    # AI path passes submission_status=None → status must be unchanged.
    assert record["status"] == "active"
