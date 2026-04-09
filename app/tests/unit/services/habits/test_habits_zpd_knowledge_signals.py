"""
Unit tests for HabitsIntelligenceService.get_zpd_knowledge_signals.

Validates the ZPD bridge that feeds ``ZPDService.assess_zone``:
- Delegates the cross-domain habit↔KU row fetch to ``CrossDomainQueryService``.
- Blends streak + success_rate into a per-KU reinforcement strength.
- Marks KUs whose reinforcing habit has a broken streak or low success rate
  as at-risk.
- Propagates query failures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.services.cross_domain import HabitKnowledgeReinforcement
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.utils.result_simplified import Errors, Result


def _make_service(cross_domain_query: AsyncMock) -> HabitsIntelligenceService:
    backend = AsyncMock()
    relationships = AsyncMock()
    return HabitsIntelligenceService(
        backend=backend,
        relationship_service=relationships,
        cross_domain_query=cross_domain_query,
    )


class TestGetZpdKnowledgeSignals:
    @pytest.mark.asyncio
    async def test_delegates_to_cross_domain_query(self) -> None:
        cross_domain_query = AsyncMock()
        cross_domain_query.get_habit_knowledge_reinforcement.return_value = Result.ok(
            (
                HabitKnowledgeReinforcement(
                    habit_uid="habit_1",
                    current_streak=30,  # full streak factor
                    success_rate=1.0,  # max success
                    status="active",
                    ku_uids=("ku_a",),
                ),
                HabitKnowledgeReinforcement(
                    habit_uid="habit_2",
                    current_streak=15,
                    success_rate=0.6,
                    status="active",
                    ku_uids=("ku_b",),
                ),
            )
        )

        service = _make_service(cross_domain_query)

        result = await service.get_zpd_knowledge_signals(user_uid="user_mike")

        assert result.is_ok
        payload = result.value
        assert set(payload["reinforced_ku_uids"]) == {"ku_a", "ku_b"}
        # habit_1: streak_factor=1.0, strength = (1.0 * 0.5) + (1.0 * 0.5) = 1.0
        assert payload["reinforcement_strength"]["ku_a"] == 1.0
        # habit_2: streak_factor = 0.5, strength = (0.5 * 0.5) + (0.6 * 0.5) = 0.55
        assert payload["reinforcement_strength"]["ku_b"] == 0.55
        assert payload["at_risk_ku_uids"] == []
        cross_domain_query.get_habit_knowledge_reinforcement.assert_awaited_once_with("user_mike")

    @pytest.mark.asyncio
    async def test_at_risk_when_streak_broken(self) -> None:
        cross_domain_query = AsyncMock()
        cross_domain_query.get_habit_knowledge_reinforcement.return_value = Result.ok(
            (
                HabitKnowledgeReinforcement(
                    habit_uid="habit_broken",
                    current_streak=0,
                    success_rate=0.9,
                    status="active",
                    ku_uids=("ku_x",),
                ),
            )
        )

        service = _make_service(cross_domain_query)
        result = await service.get_zpd_knowledge_signals(user_uid="user_mike")

        assert result.is_ok
        assert result.value["at_risk_ku_uids"] == ["ku_x"]

    @pytest.mark.asyncio
    async def test_propagates_query_failure(self) -> None:
        cross_domain_query = AsyncMock()
        cross_domain_query.get_habit_knowledge_reinforcement.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        service = _make_service(cross_domain_query)
        result = await service.get_zpd_knowledge_signals(user_uid="user_mike")

        assert result.is_error
