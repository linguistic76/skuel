"""Tests for ADR-051 Phase 2 — InteractionResult transitions in the report pipeline.

Three layers:
- InteractionResult enum: the forward-only transition table (allowed_from).
- InteractionService.record_result: guard computation + backend delegation.
- interaction_result_handler: event → transition mapping (fire-and-forget).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.handlers import interaction_result_handler
from core.events.learning_loop_events import (
    EntryReportGenerated,
    ReportSubmitted,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.events.user_entry_events import UserEntryProcessingFailed
from core.models.enums.interaction_enums import InteractionResult
from core.services.interaction.interaction_service import InteractionService
from core.utils.result_simplified import Errors, Result

ENTRY_UID = "ue_entry_001"


# ============================================================================
# Enum transition table
# ============================================================================


class TestInteractionResultTransitions:
    def test_pending_is_never_a_transition_target(self):
        assert InteractionResult.PENDING.allowed_from() == ()

    def test_shared_with_teacher_only_from_pending(self):
        assert InteractionResult.SHARED_WITH_TEACHER.allowed_from() == (InteractionResult.PENDING,)

    def test_report_generated_from_pending_or_shared(self):
        assert set(InteractionResult.REPORT_GENERATED.allowed_from()) == {
            InteractionResult.PENDING,
            InteractionResult.SHARED_WITH_TEACHER,
        }

    def test_completed_from_all_non_terminal_states(self):
        assert set(InteractionResult.COMPLETED.allowed_from()) == {
            InteractionResult.PENDING,
            InteractionResult.SHARED_WITH_TEACHER,
            InteractionResult.REPORT_GENERATED,
        }

    def test_failed_only_applies_pre_report(self):
        assert set(InteractionResult.FAILED.allowed_from()) == {
            InteractionResult.PENDING,
            InteractionResult.SHARED_WITH_TEACHER,
        }

    def test_no_status_transitions_from_itself(self):
        for status in InteractionResult:
            assert status not in status.allowed_from()

    def test_terminal_states_are_never_a_source(self):
        """COMPLETED and FAILED appear in no allowed_from — nothing leaves them."""
        for target in InteractionResult:
            for terminal in (InteractionResult.COMPLETED, InteractionResult.FAILED):
                assert terminal not in target.allowed_from()

    def test_is_terminal(self):
        assert InteractionResult.COMPLETED.is_terminal()
        assert InteractionResult.FAILED.is_terminal()
        assert not InteractionResult.PENDING.is_terminal()
        assert not InteractionResult.SHARED_WITH_TEACHER.is_terminal()
        assert not InteractionResult.REPORT_GENERATED.is_terminal()


# ============================================================================
# InteractionService.record_result
# ============================================================================


def _make_backend(transitioned: int = 1) -> MagicMock:
    backend = MagicMock()
    backend.update_result_status_for_entry = AsyncMock(return_value=Result.ok(transitioned))
    backend.health_check = AsyncMock(return_value=Result.ok(True))
    return backend


def _make_service(backend: MagicMock | None = None) -> InteractionService:
    return InteractionService(backend=backend or _make_backend())


class TestRecordResult:
    @pytest.mark.asyncio
    async def test_transition_delegates_guard_to_backend(self):
        backend = _make_backend()
        service = _make_service(backend)

        result = await service.record_result(ENTRY_UID, InteractionResult.REPORT_GENERATED)

        assert result.is_ok
        assert result.value is True
        backend.update_result_status_for_entry.assert_awaited_once_with(
            entry_uid=ENTRY_UID,
            new_status=InteractionResult.REPORT_GENERATED,
            allowed_from=InteractionResult.REPORT_GENERATED.allowed_from(),
        )

    @pytest.mark.asyncio
    async def test_zero_transitions_is_a_valid_no_op(self):
        """No Interaction record (journal entry) or stale event → ok(False)."""
        service = _make_service(_make_backend(transitioned=0))
        result = await service.record_result(ENTRY_UID, InteractionResult.COMPLETED)
        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_pending_target_is_rejected(self):
        backend = _make_backend()
        service = _make_service(backend)
        result = await service.record_result(ENTRY_UID, InteractionResult.PENDING)
        assert result.is_error
        backend.update_result_status_for_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_backend_error_propagates(self):
        backend = _make_backend()
        backend.update_result_status_for_entry = AsyncMock(
            return_value=Result.fail(Errors.database("update", "boom"))
        )
        service = _make_service(backend)
        result = await service.record_result(ENTRY_UID, InteractionResult.FAILED)
        assert result.is_error


# ============================================================================
# interaction_result_handler — event → transition mapping
# ============================================================================


def _make_interaction_service(result: Result | None = None) -> MagicMock:
    svc = MagicMock()
    svc.record_result = AsyncMock(return_value=result or Result.ok(True))
    return svc


class TestInteractionResultHandler:
    @pytest.mark.asyncio
    async def test_report_submitted_marks_completed(self):
        """submit_report is the terminal approving path — the submission itself
        transitions to COMPLETED+APPROVED, so the interaction completes too
        (Codex P2 on PR #730: REPORT_GENERATED would strand it non-terminal)."""
        svc = _make_interaction_service()
        event = ReportSubmitted(
            submission_uid=ENTRY_UID,
            teacher_uid="user_teacher",
            student_uid="user_student",
            report_uid="er_001",
        )
        await interaction_result_handler.handle_report_submitted(event, svc)
        svc.record_result.assert_awaited_once_with(ENTRY_UID, InteractionResult.COMPLETED)

    @pytest.mark.asyncio
    async def test_revision_requested_marks_report_generated(self):
        """Both revision paths persist an EntryReport before publishing this
        event — the report exists but the loop continues (non-terminal)."""
        svc = _make_interaction_service()
        event = UserEntryRevisionRequested(
            entity_uid=ENTRY_UID,
            teacher_uid="user_teacher",
            student_uid="user_student",
            revision_notes="tighten the argument",
        )
        await interaction_result_handler.handle_revision_requested(event, svc)
        svc.record_result.assert_awaited_once_with(ENTRY_UID, InteractionResult.REPORT_GENERATED)

    @pytest.mark.asyncio
    async def test_entry_report_generated_marks_report_generated(self):
        svc = _make_interaction_service()
        event = EntryReportGenerated(
            entry_uid=ENTRY_UID,
            report_uid="er_002",
            student_uid="user_student",
            source="llm",
        )
        await interaction_result_handler.handle_entry_report_generated(event, svc)
        svc.record_result.assert_awaited_once_with(ENTRY_UID, InteractionResult.REPORT_GENERATED)

    @pytest.mark.asyncio
    async def test_entry_approved_marks_completed(self):
        svc = _make_interaction_service()
        event = UserEntryApproved(
            entity_uid=ENTRY_UID,
            teacher_uid="user_teacher",
            student_uid="user_student",
        )
        await interaction_result_handler.handle_entry_approved(event, svc)
        svc.record_result.assert_awaited_once_with(ENTRY_UID, InteractionResult.COMPLETED)

    @pytest.mark.asyncio
    async def test_processing_failed_marks_failed(self):
        svc = _make_interaction_service()
        event = UserEntryProcessingFailed(
            entity_uid=ENTRY_UID,
            user_uid="user_student",
            pipeline="transcribe",
            error="deepgram unavailable",
        )
        await interaction_result_handler.handle_processing_failed(event, svc)
        svc.record_result.assert_awaited_once_with(ENTRY_UID, InteractionResult.FAILED)

    @pytest.mark.asyncio
    async def test_transition_failure_is_swallowed(self):
        """Fire-and-forget: a failed transition must never raise into the pipeline."""
        svc = _make_interaction_service(Result.fail(Errors.database("update", "down")))
        event = UserEntryApproved(
            entity_uid=ENTRY_UID,
            teacher_uid="user_teacher",
            student_uid="user_student",
        )
        await interaction_result_handler.handle_entry_approved(event, svc)  # no raise
        svc.record_result.assert_awaited_once()
