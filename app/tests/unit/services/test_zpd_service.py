"""
Tests for ZPDService — compound evidence, life path integration, recommended actions.

Tests:
- _build_zone_evidence: per-source signal tracking
- _build_recommended_actions: priority formula
- assess_zone with context: life path wiring
- assess_zone without context: backward compatibility
- Snapshot handler event dispatch
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from core.models.zpd.zpd_assessment import ZPDAssessment
from core.services.zpd.zpd_service import ZPDService
from core.utils.result_simplified import Result

# ============================================================================
# Fixtures
# ============================================================================


def _make_backend(
    ku_count: int = 10,
    zone_data: tuple | None = None,
) -> AsyncMock:
    """Create a mock ZPDBackend."""
    backend = AsyncMock()
    backend.get_ku_count = AsyncMock(return_value=ku_count)

    if zone_data is None:
        # Default: 2 current, 2 proximal, no submissions
        zone_data = (
            ["ku_a", "ku_b"],  # current_zone
            ["ku_c", "ku_d"],  # proximal_zone
            ["lp_1"],  # engaged_paths
            [  # prereq_data
                {"ku_uid": "ku_c", "total": 2, "met": 1},
                {"ku_uid": "ku_d", "total": 0, "met": 0},
            ],
            [],  # blocking_gaps
            ["ku_a"],  # task_engaged
            ["ku_b"],  # journal_engaged
            ["ku_a"],  # habit_engaged
            [  # submission_data
                {"ku_uid": "ku_a", "best_score": 0.9, "count": 2},
            ],
        )
    backend.get_zone_data = AsyncMock(return_value=Result.ok(zone_data))
    return backend


@dataclass
class _MockContext:
    """Minimal UserContext stand-in."""

    life_path_alignment_score: float = 0.7
    life_path_uid: str | None = "lp_life_1"


# ============================================================================
# _build_zone_evidence
# ============================================================================


class TestBuildZoneEvidence:
    def test_task_and_habit_confirmed(self) -> None:
        service = ZPDService(backend=_make_backend())
        evidence = service._build_zone_evidence(
            current_zone=["ku_a", "ku_b"],
            task_engaged=["ku_a"],
            journal_engaged=["ku_b"],
            habit_engaged=["ku_a"],
            submission_data=[{"ku_uid": "ku_a", "best_score": 0.9, "count": 2}],
        )
        # ku_a: task + habit + submission = 3 signals -> confirmed
        assert evidence["ku_a"].is_confirmed
        assert evidence["ku_a"].signal_count == 3
        assert evidence["ku_a"].best_submission_score == 0.9

        # ku_b: journal only = 1 signal -> not confirmed
        assert not evidence["ku_b"].is_confirmed

    def test_empty_zone(self) -> None:
        service = ZPDService(backend=_make_backend())
        evidence = service._build_zone_evidence([], [], [], [], [])
        assert evidence == {}


# ============================================================================
# _build_recommended_actions
# ============================================================================


class TestBuildRecommendedActions:
    def test_produces_learn_actions(self) -> None:
        service = ZPDService(backend=_make_backend())
        actions = service._build_recommended_actions(
            proximal_zone=["ku_c", "ku_d"],
            readiness_scores={"ku_c": 0.5, "ku_d": 1.0},
            behavioral_readiness=0.6,
            life_path_alignment=0.8,
        )
        assert len(actions) == 2
        assert all(a.action_type == "learn" for a in actions)
        assert all(a.entity_type == "article" for a in actions)

    def test_priority_formula(self) -> None:
        service = ZPDService(backend=_make_backend())
        actions = service._build_recommended_actions(
            proximal_zone=["ku_c"],
            readiness_scores={"ku_c": 1.0},
            behavioral_readiness=0.5,
            life_path_alignment=0.8,
        )
        # priority = 1.0 * 0.5 + 0.8 * 0.3 + 0.5 * 0.2 = 0.5 + 0.24 + 0.1 = 0.84
        assert actions[0].priority == 0.84

    def test_empty_proximal(self) -> None:
        service = ZPDService(backend=_make_backend())
        actions = service._build_recommended_actions([], {}, 0.5, 0.0)
        assert actions == []

    def test_unblock_actions_from_blocking_gaps(self) -> None:
        service = ZPDService(backend=_make_backend())
        actions = service._build_recommended_actions(
            proximal_zone=["ku_c"],
            readiness_scores={"ku_c": 0.5},
            behavioral_readiness=0.5,
            life_path_alignment=0.0,
            blocking_gaps=["ku_gap_1", "ku_gap_2"],
        )
        unblock = [a for a in actions if a.action_type == "unblock"]
        assert len(unblock) == 2
        assert all(a.priority == 0.9 for a in unblock)

    def test_reinforce_actions_from_thin_evidence(self) -> None:
        from core.models.zpd.zpd_assessment import ZoneEvidence

        service = ZPDService(backend=_make_backend())
        evidence = {
            "ku_a": ZoneEvidence(ku_uid="ku_a", task_application=True, habit_reinforcement=True),  # confirmed
            "ku_b": ZoneEvidence(ku_uid="ku_b", journal_application=True),  # thin — 1 signal
        }
        actions = service._build_recommended_actions(
            proximal_zone=[],
            readiness_scores={},
            behavioral_readiness=0.5,
            life_path_alignment=0.0,
            zone_evidence=evidence,
        )
        reinforce = [a for a in actions if a.action_type == "reinforce"]
        assert len(reinforce) == 1  # only ku_b (ku_a is confirmed)
        assert reinforce[0].ku_uid == "ku_b"


# ============================================================================
# assess_zone with context
# ============================================================================


class TestAssessZoneWithContext:
    @pytest.mark.asyncio
    async def test_life_path_fields_populated(self) -> None:
        backend = _make_backend()
        service = ZPDService(backend=backend)
        ctx = _MockContext(life_path_alignment_score=0.85, life_path_uid="lp_life_1")

        result = await service.assess_zone("user_1", context=ctx)
        assert not result.is_error
        assessment = result.value

        assert assessment.life_path_alignment == 0.85
        assert assessment.life_path_uid == "lp_life_1"

    @pytest.mark.asyncio
    async def test_zone_evidence_populated(self) -> None:
        backend = _make_backend()
        service = ZPDService(backend=backend)

        result = await service.assess_zone("user_1")
        assert not result.is_error
        assessment = result.value

        assert "ku_a" in assessment.zone_evidence
        assert assessment.zone_evidence["ku_a"].task_application
        assert assessment.zone_evidence["ku_a"].habit_reinforcement

    @pytest.mark.asyncio
    async def test_recommended_actions_populated(self) -> None:
        backend = _make_backend()
        service = ZPDService(backend=backend)

        result = await service.assess_zone("user_1")
        assert not result.is_error
        assessment = result.value

        # 2 learn (proximal KUs) + 1 reinforce (ku_b has 1/4 evidence)
        learn_actions = [a for a in assessment.recommended_actions if a.action_type == "learn"]
        reinforce_actions = [a for a in assessment.recommended_actions if a.action_type == "reinforce"]
        assert len(learn_actions) == 2
        assert len(reinforce_actions) == 1
        assert reinforce_actions[0].ku_uid == "ku_b"

    @pytest.mark.asyncio
    async def test_submission_scores_populated(self) -> None:
        backend = _make_backend()
        service = ZPDService(backend=backend)

        result = await service.assess_zone("user_1")
        assert not result.is_error
        assessment = result.value

        assert assessment.submission_scores.get("ku_a") == 0.9


class TestAssessZoneWithoutContext:
    @pytest.mark.asyncio
    async def test_backward_compatible(self) -> None:
        """assess_zone without context still works (life_path defaults to 0)."""
        backend = _make_backend()
        service = ZPDService(backend=backend)

        result = await service.assess_zone("user_1")
        assert not result.is_error
        assessment = result.value

        assert assessment.life_path_alignment == 0.0
        assert assessment.life_path_uid is None
        assert len(assessment.current_zone) == 2

    @pytest.mark.asyncio
    async def test_empty_curriculum(self) -> None:
        backend = _make_backend(ku_count=1)
        service = ZPDService(backend=backend)

        result = await service.assess_zone("user_1")
        assert not result.is_error
        assert result.value.is_empty()


# ============================================================================
# ZPDSnapshotHandler
# ============================================================================


class TestZPDSnapshotHandler:
    @pytest.mark.asyncio
    async def test_takes_snapshot_on_submission_approved(self) -> None:
        from core.services.zpd.zpd_event_handler import ZPDSnapshotHandler

        zpd_service = AsyncMock()
        zpd_service.assess_zone = AsyncMock(
            return_value=Result.ok(
                ZPDAssessment(
                    current_zone=["ku_a"],
                    proximal_zone=["ku_b"],
                    engaged_paths=[],
                    readiness_scores={},
                    blocking_gaps=[],
                    behavioral_readiness=0.5,
                )
            )
        )
        snapshot_backend = AsyncMock()
        snapshot_backend.save_snapshot = AsyncMock(return_value=Result.ok(None))

        handler = ZPDSnapshotHandler(zpd_service, snapshot_backend)

        # Simulate SubmissionApproved event
        event = AsyncMock()
        event.student_uid = "user_1"
        await handler.handle_submission_approved(event)

        zpd_service.assess_zone.assert_called_once_with("user_1")
        snapshot_backend.save_snapshot.assert_called_once()
        call_args = snapshot_backend.save_snapshot.call_args
        assert call_args[0][0] == "user_1"
        assert call_args[0][2] == "submission.approved"

    @pytest.mark.asyncio
    async def test_skips_snapshot_on_empty_assessment(self) -> None:
        from core.services.zpd.zpd_event_handler import ZPDSnapshotHandler

        zpd_service = AsyncMock()
        zpd_service.assess_zone = AsyncMock(
            return_value=Result.ok(
                ZPDAssessment(
                    current_zone=[],
                    proximal_zone=[],
                    engaged_paths=[],
                    readiness_scores={},
                    blocking_gaps=[],
                    behavioral_readiness=0.5,
                )
            )
        )
        snapshot_backend = AsyncMock()

        handler = ZPDSnapshotHandler(zpd_service, snapshot_backend)

        event = AsyncMock()
        event.user_uid = "user_1"
        await handler.handle_knowledge_mastered(event)

        snapshot_backend.save_snapshot.assert_not_called()
