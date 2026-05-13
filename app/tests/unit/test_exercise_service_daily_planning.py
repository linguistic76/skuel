"""
ExerciseService — Daily Planning Methods
=========================================

Direct unit tests for the service-level methods that DailyPlanningMixin
calls (P2.3 + P2.5):
- get_actionable_exercises_for_user
- get_pending_revisions_for_user

These tests pin the contract that previously lived as inline code in
daily_planning.py: time estimates (45/60), subtype tagging, prerequisite
readiness math, and degradation behavior when prereq lookups fail.

The daily_planning.py test files use a mock that simulates the same
conversion — these tests exercise the real implementation.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from core.constants import ExerciseTimeEstimate
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import Errors, Result


def _make_service() -> tuple[ExerciseService, AsyncMock]:
    """ExerciseService with a fully mocked backend."""
    backend = AsyncMock()
    return ExerciseService(backend=backend), backend


def _make_context(
    unsubmitted: list[dict[str, str | None]] | None = None,
    revisions: list[dict[str, object]] | None = None,
    mastery: dict[str, float] | None = None,
) -> object:
    """Minimal RichUserContext stand-in carrying only what the two methods read."""

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.unsubmitted_exercises = unsubmitted or []
    ctx.pending_revised_exercises = revisions or []
    ctx.knowledge_mastery = mastery or {}
    return ctx


# =========================================================================
# get_actionable_exercises_for_user
# =========================================================================


class TestGetActionableExercises:
    @pytest.mark.anyio
    async def test_empty_context_returns_empty(self) -> None:
        service, _ = _make_service()
        ctx = _make_context()

        result = await service.get_actionable_exercises_for_user(ctx)

        assert result.is_ok
        assert result.value == []

    @pytest.mark.anyio
    async def test_returns_fresh_submission_time_estimate(self) -> None:
        """est_time_minutes must come from ExerciseTimeEstimate.FRESH_SUBMISSION_MINUTES."""
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok([])
        ctx = _make_context(
            unsubmitted=[{"uid": "ex_1", "title": "Essay", "due_date": None}]
        )

        result = await service.get_actionable_exercises_for_user(ctx)

        assert result.is_ok
        assert len(result.value) == 1
        cx = result.value[0]
        assert cx.est_time_minutes == ExerciseTimeEstimate.FRESH_SUBMISSION_MINUTES
        assert cx.subtype == "assignment"

    @pytest.mark.anyio
    async def test_past_due_date_marks_overdue(self) -> None:
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok([])
        past = (date.today() - timedelta(days=3)).isoformat()
        ctx = _make_context(unsubmitted=[{"uid": "ex_late", "title": "Late", "due_date": past}])

        result = await service.get_actionable_exercises_for_user(ctx)

        cx = result.value[0]
        assert cx.is_overdue is True
        assert cx.days_until_due == -3

    @pytest.mark.anyio
    async def test_unmastered_prereqs_populate_blocking_kus(self) -> None:
        """A required KU below 0.7 mastery shows up as a blocking_kus entry."""
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok(
            [
                {"uid": "ku_basics", "title": "Basics", "entity_type": "ku"},
                {"uid": "ku_advanced", "title": "Advanced", "entity_type": "ku"},
            ]
        )
        ctx = _make_context(
            unsubmitted=[{"uid": "ex_1", "title": "Essay", "due_date": None}],
            mastery={"ku_basics": 0.9, "ku_advanced": 0.4},  # only advanced is blocking
        )

        result = await service.get_actionable_exercises_for_user(ctx)

        cx = result.value[0]
        assert cx.blocking_kus == ("ku_advanced",)
        assert cx.readiness_score == 0.5  # 1 of 2 mastered
        assert cx.is_blocked is True
        assert cx.is_ready is False  # 0.5 < 0.7

    @pytest.mark.anyio
    async def test_prereq_lookup_failure_degrades_to_ready(self) -> None:
        """A failed get_required_knowledge call must not collapse the batch."""
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.fail(
            Errors.database(operation="get_required_knowledge", message="Neo4j unavailable")
        )
        ctx = _make_context(
            unsubmitted=[{"uid": "ex_1", "title": "Essay", "due_date": None}]
        )

        result = await service.get_actionable_exercises_for_user(ctx)

        assert result.is_ok
        cx = result.value[0]
        assert cx.blocking_kus == ()
        assert cx.readiness_score == 1.0

    @pytest.mark.anyio
    async def test_ready_exercises_sorted_before_blocked(self) -> None:
        service, backend = _make_service()

        async def fake_prereqs(uid: str) -> Result:
            if uid == "ex_blocked":
                return Result.ok([{"uid": "ku_x", "title": "X", "entity_type": "ku"}])
            return Result.ok([])

        backend.get_required_knowledge.side_effect = fake_prereqs
        ctx = _make_context(
            unsubmitted=[
                {"uid": "ex_blocked", "title": "Blocked", "due_date": None},
                {"uid": "ex_ready", "title": "Ready", "due_date": None},
            ],
            mastery={"ku_x": 0.1},
        )

        result = await service.get_actionable_exercises_for_user(ctx)

        uids = [cx.uid for cx in result.value]
        assert uids == ["ex_ready", "ex_blocked"]

    @pytest.mark.anyio
    async def test_default_limit_caps_at_3(self) -> None:
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok([])
        ctx = _make_context(
            unsubmitted=[{"uid": f"ex_{i}", "title": f"E{i}", "due_date": None} for i in range(7)]
        )

        result = await service.get_actionable_exercises_for_user(ctx)

        assert len(result.value) == 3


# =========================================================================
# get_pending_revisions_for_user
# =========================================================================


class TestGetPendingRevisions:
    @pytest.mark.anyio
    async def test_empty_context_returns_empty(self) -> None:
        service, _ = _make_service()
        ctx = _make_context()

        result = await service.get_pending_revisions_for_user(ctx)

        assert result.is_ok
        assert result.value == []

    @pytest.mark.anyio
    async def test_returns_revision_time_estimate_and_subtype(self) -> None:
        """est_time_minutes must come from ExerciseTimeEstimate.REVISION_MINUTES,
        and subtype must be 'revision' (drives daily-planning rationale routing)."""
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok([])
        ctx = _make_context(
            revisions=[
                {
                    "uid": "rev_1",
                    "title": "Revision 1",
                    "original_exercise_uid": "ex_orig",
                    "report_uid": "rep_1",
                    "revision_number": 1,
                }
            ]
        )

        result = await service.get_pending_revisions_for_user(ctx)

        assert result.is_ok
        cx = result.value[0]
        assert cx.est_time_minutes == ExerciseTimeEstimate.REVISION_MINUTES
        assert cx.subtype == "revision"
        # Revisions don't carry due-date context
        assert cx.due_date is None
        assert cx.is_overdue is False

    @pytest.mark.anyio
    async def test_prereq_lookup_uses_original_exercise_uid(self) -> None:
        """The prereq join walks REVISES_EXERCISE → Exercise → REQUIRES_KNOWLEDGE,
        so the lookup must use original_exercise_uid (not the revision uid)."""
        service, backend = _make_service()
        backend.get_required_knowledge.return_value = Result.ok(
            [{"uid": "ku_grammar", "title": "Grammar", "entity_type": "ku"}]
        )
        ctx = _make_context(
            revisions=[
                {
                    "uid": "rev_1",
                    "title": "Revision 1",
                    "original_exercise_uid": "ex_orig_xyz",
                }
            ],
            mastery={"ku_grammar": 0.3},
        )

        result = await service.get_pending_revisions_for_user(ctx)

        backend.get_required_knowledge.assert_called_once_with("ex_orig_xyz")
        cx = result.value[0]
        assert cx.blocking_kus == ("ku_grammar",)

    @pytest.mark.anyio
    async def test_revision_without_original_exercise_uid_skips_join(self) -> None:
        """Missing original_exercise_uid → no prereq query, defaults to ready."""
        service, backend = _make_service()
        ctx = _make_context(
            revisions=[{"uid": "rev_1", "title": "Orphaned revision"}]  # no original
        )

        result = await service.get_pending_revisions_for_user(ctx)

        backend.get_required_knowledge.assert_not_called()
        cx = result.value[0]
        assert cx.blocking_kus == ()
        assert cx.readiness_score == 1.0
