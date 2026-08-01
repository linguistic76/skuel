"""Tests for EntryReportService (AI report generation path).

Mirrors test_teacher_review_service.py: mocks EntryReportBackendOperations.create_report_node
and asserts the parameters passed. The SHARES_WITH + OWNS + REPORT_FOR edges are
created inside the Cypher of create_report_node itself (covered by the teacher-path
tests and by integration checks against Neo4j); this suite verifies that the AI
path routes through the same canonical method with the correct params, so that
AI reports become visible to students via the same SHARES_WITH read path.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.learning_loop_events import EntryReportGenerated
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.learning_enums import AssessmentOutcome, MasteryImpact
from core.models.enums.pipeline import ReportSource
from core.models.exercises.exercise import Exercise
from core.models.report.entry_report import EntryReport
from core.models.user_entry.user_entry import UserEntry
from core.services.report.entry_report_service import EntryReportService
from core.utils.result_simplified import Errors, Result

STUDENT_UID = "user_student_xyz"
TEACHER_UID = "user_teacher_abc"
SUBMISSION_UID = "es_submission_001"
EXERCISE_UID = "ex_exercise_001"


def _make_submission(content: str = "My submitted work.") -> UserEntry:
    return UserEntry(
        uid=SUBMISSION_UID,
        title="Student Submission",
        user_uid=STUDENT_UID,
        status=EntityStatus.ACTIVE,
        content=content,
    )


def _make_exercise(
    *,
    title: str = "Week 3 Reflection",
    instructions: str = "Evaluate the student's reasoning.",
    model: str = "claude-sonnet-4-6",
    mastery_impact: MasteryImpact = MasteryImpact.MODERATE,
) -> Exercise:
    return Exercise(
        uid=EXERCISE_UID,
        title=title,
        entity_type=EntityType.EXERCISE,
        instructions=instructions,
        model=model,
        mastery_impact=mastery_impact,
        path_step_uid="ps_001",
    )


def _make_llm_caller(*, text: str = "Great work — here is your feedback.") -> MagicMock:
    caller = MagicMock()
    caller.generate = AsyncMock(return_value=Result.ok(text))
    caller.get_supported_models = MagicMock(return_value={"anthropic": ["claude-sonnet-4-6"]})
    caller.is_model_supported = MagicMock(return_value=True)
    return caller


def _make_ext_backend() -> MagicMock:
    backend = MagicMock()
    backend.create_report_node = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "uid": SUBMISSION_UID,
                    "status": EntityStatus.ACTIVE.value,
                    "student_uid": STUDENT_UID,
                    "report_entity_uid": "sr_will_be_overwritten",
                    # Composed backend-side from title_prefix + subject (C3).
                    "report_title": "AI feedback on 'Week 3 Reflection'",
                }
            ]
        )
    )
    return backend


def _make_service(
    *,
    llm_caller: MagicMock | None = None,
    backend: MagicMock | None = None,
) -> EntryReportService:
    return EntryReportService(
        llm_caller=llm_caller or _make_llm_caller(),
        backend=backend or _make_ext_backend(),
    )


# ============================================================================
# TestGenerateReportHappyPath
# ============================================================================


class TestGenerateReportHappyPath:
    @pytest.mark.asyncio
    async def test_success_returns_entry_report_entity(self):
        service = _make_service()

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert not result.is_error, result.error if result.is_error else None
        report = result.value
        assert report.entity_type == EntityType.ENTRY_REPORT
        assert report.processor_type == ReportSource.LLM
        assert report.assessment_outcome == AssessmentOutcome.AI_EVALUATED
        assert report.status == EntityStatus.COMPLETED
        assert report.subject_uid == SUBMISSION_UID
        assert report.user_uid == STUDENT_UID  # student always owns the report
        assert report.author_uid is None  # LLM-authored ⇒ no human author
        assert report.processed_content == "Great work — here is your feedback."
        assert report.uid.startswith("er_")

    @pytest.mark.asyncio
    async def test_llm_called_with_feedback_prompt(self):
        llm = _make_llm_caller()
        service = _make_service(llm_caller=llm)
        submission = _make_submission(content="Answer body.")
        exercise = _make_exercise(instructions="Grade this harshly.")

        await service.generate_report(
            entry=submission,
            exercise=exercise,
            user_uid=TEACHER_UID,
        )

        llm.generate.assert_awaited_once()
        call_kwargs = llm.generate.await_args.kwargs
        assert "Grade this harshly." in call_kwargs["prompt"]
        assert "Answer body." in call_kwargs["prompt"]
        assert call_kwargs["model"] == "claude-sonnet-4-6"


# ============================================================================
# TestEntryReportGeneratedEvent (ADR-051 Phase 2)
# ============================================================================


class TestEntryReportGeneratedEvent:
    """A persisted AI report publishes EntryReportGenerated — the trigger for
    the Interaction result_status transition (ADR-051 Phase 2)."""

    @pytest.mark.asyncio
    async def test_event_published_after_persist(self):
        event_bus = MagicMock()
        event_bus.publish_async = AsyncMock(return_value=None)
        service = EntryReportService(
            llm_caller=_make_llm_caller(),
            backend=_make_ext_backend(),
            event_bus=event_bus,
        )

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_ok
        event_bus.publish_async.assert_awaited_once()
        event = event_bus.publish_async.await_args.args[0]
        assert isinstance(event, EntryReportGenerated)
        assert event.entry_uid == SUBMISSION_UID
        assert event.report_uid == result.value.uid
        assert event.student_uid == STUDENT_UID
        assert event.source == ReportSource.LLM.value

    @pytest.mark.asyncio
    async def test_no_event_bus_is_fine(self):
        service = _make_service()  # event_bus omitted
        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )
        assert result.is_ok


# ============================================================================
# TestGenerateReportBackendDelegation
# ============================================================================


class TestGenerateReportBackendDelegation:
    """The AI path must route through EntryReportBackendOperations.create_report_node with
    the right params — this is what wires AI reports into the student-visible
    read path (SHARES_WITH) and keeps them symmetric with teacher reports."""

    @pytest.mark.asyncio
    async def test_delegates_to_canonical_create_report_node(self):
        backend = _make_ext_backend()
        service = _make_service(backend=backend)

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        backend.create_report_node.assert_awaited_once()
        # The entity echoes the backend-composed title, not a service-built one.
        assert result.value.title == "AI feedback on 'Week 3 Reflection'"

    @pytest.mark.asyncio
    async def test_params_mark_report_as_llm_processor(self):
        backend = _make_ext_backend()
        service = _make_service(backend=backend)

        await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        (params,), _ = backend.create_report_node.await_args
        assert params["processor_type"] == ReportSource.LLM.value
        assert params["assessment_outcome"] == AssessmentOutcome.AI_EVALUATED.value
        assert params["entity_type"] == EntityType.ENTRY_REPORT.value

    @pytest.mark.asyncio
    async def test_params_skip_status_transition_and_guard(self):
        """AI reports must pass None for both status fields so the backend
        skips the state-machine transition and the from-status guard — AI
        reports are not state-machine events the way teacher reviews are."""
        backend = _make_ext_backend()
        service = _make_service(backend=backend)

        await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        (params,), _ = backend.create_report_node.await_args
        assert params["submission_status"] is None
        assert params["allowed_from_statuses"] is None

    @pytest.mark.asyncio
    async def test_params_use_author_uid_none_for_llm(self):
        """Canonical method takes author_uid (renamed from teacher_uid); LLM ⇒ None."""
        backend = _make_ext_backend()
        service = _make_service(backend=backend)

        await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        (params,), _ = backend.create_report_node.await_args
        assert params["author_uid"] is None
        assert "teacher_uid" not in params

    @pytest.mark.asyncio
    async def test_params_include_submission_uid_and_feedback_text(self):
        backend = _make_ext_backend()
        llm = _make_llm_caller(text="Detailed feedback body.")
        service = _make_service(llm_caller=llm, backend=backend)

        await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(title="Reflection #3"),
            user_uid=TEACHER_UID,
        )

        (params,), _ = backend.create_report_node.await_args
        assert params["report_uid"] == SUBMISSION_UID
        assert params["feedback"] == "Detailed feedback body."
        assert params["report_file_path"] is None
        # Title is composed backend-side from the subject (C3) — the service
        # only supplies the lead-in, never a pre-baked title.
        assert params["title_prefix"] == "AI feedback on"
        assert "title" not in params
        assert params["now"]  # ISO timestamp, non-empty
        assert params["report_entity_uid"].startswith("er_")


# ============================================================================
# TestGenerateReportValidation
# ============================================================================


class TestGenerateReportValidation:
    @pytest.mark.asyncio
    async def test_invalid_exercise_fails_fast_without_llm_call(self):
        llm = _make_llm_caller()
        backend = _make_ext_backend()
        service = _make_service(llm_caller=llm, backend=backend)
        invalid_exercise = Exercise(
            uid=EXERCISE_UID,
            title="",  # missing title → invalid
            entity_type=EntityType.EXERCISE,
            instructions=None,
            model="claude-sonnet-4-6",
        )

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=invalid_exercise,
            user_uid=TEACHER_UID,
        )

        assert result.is_error
        llm.generate.assert_not_awaited()
        backend.create_report_node.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_submission_content_fails_fast(self):
        llm = _make_llm_caller()
        backend = _make_ext_backend()
        service = _make_service(llm_caller=llm, backend=backend)
        empty_submission = UserEntry(
            uid=SUBMISSION_UID,
            title="Empty",
            user_uid=STUDENT_UID,
            status=EntityStatus.ACTIVE,
            content=None,
        )

        result = await service.generate_report(
            entry=empty_submission,
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_error
        llm.generate.assert_not_awaited()
        backend.create_report_node.assert_not_awaited()


# ============================================================================
# TestGenerateReportErrorPropagation
# ============================================================================


class TestGenerateReportErrorPropagation:
    @pytest.mark.asyncio
    async def test_llm_error_propagates_without_backend_call(self):
        llm = _make_llm_caller()
        llm.generate.return_value = Result.fail(
            Errors.integration(service="LLM", operation="generate", message="rate limited")
        )
        backend = _make_ext_backend()
        service = _make_service(llm_caller=llm, backend=backend)

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_error
        backend.create_report_node.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_backend_error_propagates_as_database_failure(self):
        backend = _make_ext_backend()
        backend.create_report_node.return_value = Result.fail(
            Errors.database("create_report_node", "connection lost")
        )
        service = _make_service(backend=backend)

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_error

    @pytest.mark.asyncio
    async def test_backend_empty_result_fails(self):
        backend = _make_ext_backend()
        backend.create_report_node.return_value = Result.ok([])
        service = _make_service(backend=backend)

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_error


# ============================================================================
# TestGenerateReportWithoutBackend
# ============================================================================


# ============================================================================
# TestListForSubmission
# ============================================================================


def _make_entry_report_backend() -> MagicMock:
    backend = MagicMock()
    backend.list_for_submission = AsyncMock(return_value=Result.ok([]))
    backend.get = AsyncMock(return_value=Result.ok(None))
    return backend


class TestGet:
    """`get` narrows a typed single-fetch through the backend."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend_and_returns_report(self):
        report = EntryReport(
            uid="sr_teacher_042",
            entity_type=EntityType.ENTRY_REPORT,
            title="Teacher Feedback",
            user_uid=TEACHER_UID,
            status=EntityStatus.COMPLETED,
            processor_type=ReportSource.HUMAN,
            content="Solid work.",
            subject_uid=SUBMISSION_UID,
        )
        backend = _make_entry_report_backend()
        backend.get.return_value = Result.ok(report)
        service = EntryReportService(llm_caller=_make_llm_caller(), backend=backend)

        result = await service.get("sr_teacher_042")

        assert not result.is_error
        assert result.value is report
        backend.get.assert_awaited_once_with("sr_teacher_042")

    @pytest.mark.asyncio
    async def test_missing_report_narrows_to_not_found(self):
        backend = _make_entry_report_backend()
        backend.get.return_value = Result.ok(None)
        service = EntryReportService(llm_caller=_make_llm_caller(), backend=backend)

        result = await service.get("sr_missing")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_no_backend_fails_fast(self):
        service = EntryReportService(llm_caller=_make_llm_caller(), backend=None)

        result = await service.get("sr_any")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_backend_error_propagates(self):
        backend = _make_entry_report_backend()
        backend.get.return_value = Result.fail(Errors.database("get", "query failed"))
        service = EntryReportService(llm_caller=_make_llm_caller(), backend=backend)

        result = await service.get("sr_any")

        assert result.is_error


class TestListForSubmission:
    """`list_for_submission` delegates to EntryReportBackend and returns
    typed EntryReport entities — both teacher (HUMAN) and AI (LLM) reports
    appear, discriminated by processor_type."""

    @pytest.mark.asyncio
    async def test_delegates_to_backend_and_returns_typed_reports(self):
        ai_report = EntryReport(
            uid="sr_ai_001",
            entity_type=EntityType.ENTRY_REPORT,
            title="AI Feedback",
            user_uid=TEACHER_UID,
            status=EntityStatus.COMPLETED,
            processor_type=ReportSource.LLM,
            assessment_outcome=AssessmentOutcome.AI_EVALUATED,
            content="AI notes",
            subject_uid=SUBMISSION_UID,
        )
        teacher_report = EntryReport(
            uid="sr_teacher_001",
            entity_type=EntityType.ENTRY_REPORT,
            title="Teacher Feedback",
            user_uid=TEACHER_UID,
            status=EntityStatus.COMPLETED,
            processor_type=ReportSource.HUMAN,
            content="Teacher notes",
            subject_uid=SUBMISSION_UID,
        )
        backend = _make_entry_report_backend()
        backend.list_for_submission.return_value = Result.ok([ai_report, teacher_report])
        service = EntryReportService(
            llm_caller=_make_llm_caller(),
            backend=backend,
        )

        result = await service.list_for_submission(SUBMISSION_UID)

        assert not result.is_error
        assert result.value == [ai_report, teacher_report]
        backend.list_for_submission.assert_awaited_once_with(SUBMISSION_UID)

    @pytest.mark.asyncio
    async def test_no_backend_fails_fast(self):
        service = EntryReportService(
            llm_caller=_make_llm_caller(),
            backend=None,
        )

        result = await service.list_for_submission(SUBMISSION_UID)

        assert result.is_error

    @pytest.mark.asyncio
    async def test_backend_error_propagates(self):
        backend = _make_entry_report_backend()
        backend.list_for_submission.return_value = Result.fail(
            Errors.database("list_for_submission", "query failed")
        )
        service = EntryReportService(
            llm_caller=_make_llm_caller(),
            backend=backend,
        )

        result = await service.list_for_submission(SUBMISSION_UID)

        assert result.is_error


# ============================================================================
# TestGenerateReportWithoutBackend
# ============================================================================


class TestGenerateReportWithoutBackend:
    @pytest.mark.asyncio
    async def test_no_backend_returns_system_error(self):
        """Fail-fast: missing backend returns a system error
        rather than a transient non-persisted report (SKUEL fail-fast rule)."""
        service = EntryReportService(
            llm_caller=_make_llm_caller(text="Feedback text."),
            backend=None,
        )

        result = await service.generate_report(
            entry=_make_submission(),
            exercise=_make_exercise(),
            user_uid=TEACHER_UID,
        )

        assert result.is_error
        assert "backend" in str(result.error).lower()
