"""
Unit Tests — method 1 answers: a failed application read is a ``Result``, the boost is per unit
==============================================================================================

``get_optimal_next_path_steps`` enriches every candidate with where that knowledge is
applied (``_get_application_opportunities_for_ku``). Two things that method must be true
about:

- A failed graph read fails the answer as a ``Result`` — never a raise inside a
  ``Result``-returning path. The application reads take whatever uid the source handed
  over: the ZPD and vector sources hand Ku uids, and ``PsApplicationDiscoveryService``
  reads the knowledge end as an ``:Entity`` without verifying it first, so a Ku uid is an
  answer, not a refusal.
- Compound evidence lifts the candidate it is evidence FOR. A prerequisite term computed
  over the whole candidate list would lift every candidate by the same constant.
"""

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from core.models.zpd.zpd_assessment import ZoneEvidence, ZPDAssessment
from core.services.ps.ps_application_discovery_service import PsApplicationDiscoveryService
from core.services.ps_service import PsService
from core.services.tasks_service import TasksService
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.services.zpd.zpd_service import ZPDService
from core.utils.result_simplified import Errors, Result

pytestmark = pytest.mark.asyncio

KU = "ku.test.anchor"  # a Ku uid — what the ZPD source hands method 1
OTHER = "ku.test.other"
READINESS = 0.8


def _assessment(
    proximal: list[str], evidence: dict[str, ZoneEvidence] | None = None
) -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=[],
        proximal_zone=proximal,
        engaged_paths=[],
        readiness_scores=dict.fromkeys(proximal, READINESS),
        blocking_gaps=[],
        behavioral_readiness=0.0,
        zone_evidence=evidence or {},
    )


def _hub(
    assessment: ZPDAssessment, *, habits: Result[list[str]] | None = None
) -> UserContextIntelligence:
    """The real hub over a ZPD source; the habits read answers as given."""
    ps = create_autospec(PsService, instance=True)
    ps.find_habits_reinforcing_knowledge.return_value = habits or Result.ok([])
    ps.find_events_applying_knowledge.return_value = Result.ok([])
    tasks = create_autospec(TasksService, instance=True)
    tasks.get_learning_tasks_for_user.return_value = Result.ok([])
    zpd = create_autospec(ZPDService, instance=True)
    zpd.assess_zone.return_value = Result.ok(assessment)
    factory = UserContextIntelligenceFactory(
        tasks=tasks,
        goals=MagicMock(),
        habits=MagicMock(),
        events=MagicMock(),
        choices=MagicMock(),
        principles=MagicMock(),
        ps=ps,
        lp=MagicMock(),
        exercises=MagicMock(),
        report=MagicMock(),
        calendar=MagicMock(),
        vector_search_service=None,
        zpd_service=zpd,
    )
    return factory.create(RichUserContext(user_uid="user_test"))


class TestAFailedApplicationReadIsAResult:
    async def test_a_not_found_habits_read_fails_the_answer_without_raising(self) -> None:
        refused: Result[list[str]] = Result.fail(Errors.not_found("PathStep", KU))
        hub = _hub(_assessment([KU]), habits=refused)

        result = await hub.get_optimal_next_path_steps()

        assert result.is_error
        assert result.expect_error().category == refused.expect_error().category

    async def test_the_habits_found_ride_on_the_step(self) -> None:
        hub = _hub(_assessment([KU]), habits=Result.ok(["habit.test.reinforces"]))

        result = await hub.get_optimal_next_path_steps(consider_capacity=False)

        assert result.is_ok, result
        (step,) = result.value
        assert step.ku_uid == KU
        assert step.application_opportunities["habits"] == ("habit.test.reinforces",)


class TestDiscoveryReadsTheKnowledgeEndAsAnEntity:
    async def test_a_ku_uid_is_read_not_verified_against_the_path_step_backend(self) -> None:
        repo = MagicMock()
        # A PathStep-backend ``get`` finds no PathStep for a Ku uid; the read must not ask it.
        repo.get = AsyncMock(return_value=Result.ok(None))
        repo.find_connected_activities = AsyncMock(
            return_value=Result.ok([{"entity_uid": "habit.test.reinforces"}])
        )
        service = PsApplicationDiscoveryService(repo=repo)

        found = await service.find_habits_reinforcing_knowledge(KU, "user_test", only_active=False)

        assert found.is_ok, found
        assert found.value == ["habit.test.reinforces"]
        repo.get.assert_not_called()
        assert repo.find_connected_activities.call_args.kwargs["ku_uid"] == KU


class TestCompoundEvidenceLiftsItsOwnUnit:
    async def test_only_the_confirmed_candidate_is_boosted(self) -> None:
        confirmed = ZoneEvidence(ku_uid=KU, submission_count=1, habit_reinforcement=True)
        assert confirmed.is_confirmed  # two signal types — the premise
        assessment = _assessment([KU, OTHER], evidence={KU: confirmed})
        hub = _hub(assessment)

        result = await hub.get_optimal_next_path_steps(
            consider_goals=False, consider_capacity=False
        )

        assert result.is_ok, result
        base = round(
            READINESS * 0.5
            + assessment.life_path_alignment * 0.3
            + assessment.behavioral_readiness * 0.2,
            3,
        )
        by_uid = {step.ku_uid: step.priority_score for step in result.value}
        assert by_uid == {KU: min(1.0, base + 0.05), OTHER: base}
