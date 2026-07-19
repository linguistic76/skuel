"""
Interaction Result Handler — ADR-051 Phase 2
============================================

Transitions ``Interaction.result_status`` as the report pipeline progresses.
The Interaction audit record is created at turn-in time with
``result_status=PENDING``; these handlers move it forward:

  ReportSubmitted             → COMPLETED         (submit_report is the terminal
                                                   approving path: it marks the
                                                   submission COMPLETED+APPROVED)
  EntryReportGenerated        → REPORT_GENERATED  (AI report persisted)
  UserEntryRevisionRequested  → REPORT_GENERATED  (revision report exists; the
                                                   loop continues — approval
                                                   arrives later as UserEntryApproved)
  UserEntryApproved           → COMPLETED         (post-revision approval — terminal)
  UserEntryProcessingFailed   → FAILED            (pipeline broke pre-report)

The SHARED_WITH_TEACHER transition is NOT event-driven — only
``UserEntryService.create_entry`` knows the share outcome, so it records
that transition directly after a successful teacher-review share.

All handlers are fire-and-forget: the transition is an audit concern and
must never propagate a failure into the pipeline that triggered it. The
forward-only guard lives in ``InteractionResult.allowed_from()`` +
``InteractionBackend.update_result_status_for_entry``, so out-of-order
event delivery is safe (a stale event is a logged no-op).

Registered in ``services_bootstrap/_event_wiring.py`` via functools.partial.

See: /docs/decisions/ADR-051-user-interaction-contract.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.events.learning_loop_events import (
    EntryReportGenerated,
    ReportSubmitted,
    UserEntryApproved,
    UserEntryRevisionRequested,
)
from core.events.user_entry_events import UserEntryProcessingFailed
from core.models.enums.interaction_enums import InteractionResult
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.services.interaction.interaction_service import InteractionService

logger = get_logger("skuel.events.interaction_result_handler")


async def _record(
    interaction_service: InteractionService,
    entry_uid: str,
    new_status: InteractionResult,
) -> None:
    """Shared fire-and-forget transition — failures are logged, never raised."""
    result = await interaction_service.record_result(entry_uid, new_status)
    if result.is_error:
        logger.warning(
            f"Interaction transition to {new_status.value} failed for entry "
            f"{entry_uid}: {result.expect_error()}"
        )


async def handle_report_submitted(
    event: ReportSubmitted,
    interaction_service: InteractionService,
) -> None:
    """Teacher feedback submitted → COMPLETED.

    ``TeacherReviewService.submit_report`` is the terminal approving path —
    its Cypher transitions the submission itself to COMPLETED with
    ``assessment_outcome=APPROVED``, so the interaction is fully processed
    (REPORT_GENERATED would strand approved submissions non-terminal; the
    revision path publishes UserEntryRevisionRequested instead).
    """
    await _record(interaction_service, event.submission_uid, InteractionResult.COMPLETED)


async def handle_entry_report_generated(
    event: EntryReportGenerated,
    interaction_service: InteractionService,
) -> None:
    """AI report persisted → REPORT_GENERATED."""
    await _record(interaction_service, event.entry_uid, InteractionResult.REPORT_GENERATED)


async def handle_revision_requested(
    event: UserEntryRevisionRequested,
    interaction_service: InteractionService,
) -> None:
    """Revision report created → REPORT_GENERATED (non-terminal).

    Both revision paths (``request_revision`` and
    ``request_revision_with_exercise``) persist an EntryReport before
    publishing this event; the loop continues and terminal COMPLETED
    arrives later via UserEntryApproved (``approve_report``).
    """
    await _record(interaction_service, event.entity_uid, InteractionResult.REPORT_GENERATED)


async def handle_entry_approved(
    event: UserEntryApproved,
    interaction_service: InteractionService,
) -> None:
    """Teacher approved the entry → COMPLETED (terminal)."""
    await _record(interaction_service, event.entity_uid, InteractionResult.COMPLETED)


async def handle_processing_failed(
    event: UserEntryProcessingFailed,
    interaction_service: InteractionService,
) -> None:
    """Pipeline processing failed → FAILED (only applies pre-report)."""
    await _record(interaction_service, event.entity_uid, InteractionResult.FAILED)
