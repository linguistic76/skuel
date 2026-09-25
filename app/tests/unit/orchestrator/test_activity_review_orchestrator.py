"""``ActivityReviewOrchestrator.submit_report`` checks the subject is a user
before the report is written as theirs (Submit & Share arc R11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.type_hints import UserUID
from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result


@pytest.fixture
def activity_report() -> MagicMock:
    service = MagicMock()
    service.submit_report = AsyncMock(return_value=Result.ok(MagicMock(uid="ar_1")))
    return service


@pytest.fixture
def user_service() -> MagicMock:
    service = MagicMock()
    service.get_user = AsyncMock(return_value=Result.ok(MagicMock(uid="user_student")))
    return service


@pytest.fixture
def orchestrator(activity_report: MagicMock, user_service: MagicMock) -> ActivityReviewOrchestrator:
    return ActivityReviewOrchestrator(activity_report=activity_report, user_service=user_service)


@pytest.mark.asyncio
async def test_an_unknown_subject_is_a_validation_error_on_subject_uid(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    user_service.get_user = AsyncMock(return_value=Result.ok(None))

    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"), subject_uid=UserUID("user_typo"), feedback_text="…"
    )

    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.VALIDATION
    assert error.details.get("field") == "subject_uid"
    activity_report.submit_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_user_read_propagates(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    user_service.get_user = AsyncMock(
        return_value=Result.fail(Errors.database("get_user", "connection lost"))
    )

    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"), subject_uid=UserUID("user_student"), feedback_text="…"
    )

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.DATABASE
    activity_report.submit_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_known_subject_reaches_the_writer(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock
) -> None:
    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        time_period="2026-09",
        domains=["tasks"],
    )

    assert result.is_ok
    activity_report.submit_report.assert_awaited_once_with(
        admin_uid="user_admin",
        subject_uid="user_student",
        feedback_text="Good week.",
        time_period="2026-09",
        domains=["tasks"],
    )
