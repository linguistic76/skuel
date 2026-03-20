"""
Unit tests for ChoiceEventHandlerService.

Tests cover:
- handle_choice_outcome_recorded: happy path, missing choice early return, exception handling
- handle_choice_made: happy path with insight persistence, without principle alignment, exception handling
- Fire-and-forget contract: exceptions logged, never propagated
- Module-level helpers: categorize_outcome_quality, categorize_confidence
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from core.events.choice_events import ChoiceMade, ChoiceOutcomeRecorded
from core.services.choices.choice_event_handler_service import (
    ChoiceEventHandlerService,
    categorize_confidence,
    categorize_outcome_quality,
)
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.execute_query = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_relationships() -> AsyncMock:
    rels = AsyncMock()
    rels.get_related_uids = AsyncMock(return_value=Result.ok([]))
    return rels


@pytest.fixture
def mock_insight_store() -> AsyncMock:
    store = AsyncMock()
    store.create_insight = AsyncMock(return_value=Result.ok(True))
    return store


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.fixture
def service(mock_backend: Mock) -> ChoiceEventHandlerService:
    return ChoiceEventHandlerService(backend=mock_backend)


@pytest.fixture
def service_full(
    mock_backend: Mock,
    mock_relationships: AsyncMock,
    mock_insight_store: AsyncMock,
    mock_event_bus: AsyncMock,
) -> ChoiceEventHandlerService:
    return ChoiceEventHandlerService(
        backend=mock_backend,
        relationship_service=mock_relationships,
        insight_store=mock_insight_store,
        event_bus=mock_event_bus,
    )


def _make_mock_choice(description: str = "Test choice", complexity: float = 3.0) -> MagicMock:
    """Create a mock Choice with required attributes."""
    from core.models.choice.choice import Choice

    choice = MagicMock(spec=Choice)
    choice.description = description
    choice.calculate_decision_complexity.return_value = complexity
    return choice


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestCategorizeOutcomeQuality:
    def test_excellent(self):
        assert categorize_outcome_quality(0.9) == "excellent"

    def test_excellent_boundary(self):
        assert categorize_outcome_quality(0.8) == "excellent"

    def test_good(self):
        assert categorize_outcome_quality(0.7) == "good"

    def test_good_boundary(self):
        assert categorize_outcome_quality(0.6) == "good"

    def test_neutral(self):
        assert categorize_outcome_quality(0.5) == "neutral"

    def test_neutral_boundary(self):
        assert categorize_outcome_quality(0.4) == "neutral"

    def test_poor(self):
        assert categorize_outcome_quality(0.3) == "poor"

    def test_poor_boundary(self):
        assert categorize_outcome_quality(0.2) == "poor"

    def test_bad(self):
        assert categorize_outcome_quality(0.1) == "bad"

    def test_bad_zero(self):
        assert categorize_outcome_quality(0.0) == "bad"


class TestCategorizeConfidence:
    def test_very_high(self):
        assert categorize_confidence(0.95) == "very_high"

    def test_very_high_boundary(self):
        assert categorize_confidence(0.9) == "very_high"

    def test_high(self):
        assert categorize_confidence(0.8) == "high"

    def test_high_boundary(self):
        assert categorize_confidence(0.7) == "high"

    def test_moderate(self):
        assert categorize_confidence(0.6) == "moderate"

    def test_moderate_boundary(self):
        assert categorize_confidence(0.5) == "moderate"

    def test_low(self):
        assert categorize_confidence(0.4) == "low"

    def test_low_boundary(self):
        assert categorize_confidence(0.3) == "low"

    def test_very_low(self):
        assert categorize_confidence(0.1) == "very_low"

    def test_very_low_zero(self):
        assert categorize_confidence(0.0) == "very_low"


# ---------------------------------------------------------------------------
# handle_choice_outcome_recorded tests
# ---------------------------------------------------------------------------


class TestHandleChoiceOutcomeRecorded:
    @pytest.mark.asyncio
    async def test_happy_path(self, service_full: ChoiceEventHandlerService, mock_backend: Mock):
        """Outcome is analyzed and structured insights logged."""
        mock_choice = MagicMock()
        mock_choice.description = "Should I learn Rust?"
        mock_backend.get.return_value = Result.ok(mock_choice)

        event = ChoiceOutcomeRecorded(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            outcome_quality=0.85,
            lessons_learned=None,
            occurred_at=datetime.now(),
        )

        with patch.object(service_full.logger, "info") as mock_log:
            await service_full.handle_choice_outcome_recorded(event)
            log_calls = [c for c in mock_log.call_args_list if "outcome" in str(c).lower()]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_missing_choice_early_return(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """Handler returns early when choice not found."""
        mock_backend.get.return_value = Result.ok(None)

        event = ChoiceOutcomeRecorded(
            choice_uid="choice_missing",
            user_uid="user_mike",
            outcome_quality=0.5,
            lessons_learned=None,
            occurred_at=datetime.now(),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_choice_outcome_recorded(event)
            warn_calls = [c for c in mock_warn.call_args_list if "not found" in str(c).lower()]
            assert len(warn_calls) == 1

    @pytest.mark.asyncio
    async def test_backend_error_early_return(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """Handler returns early when backend returns error."""
        mock_backend.get.return_value = Result.fail("database error")

        event = ChoiceOutcomeRecorded(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            outcome_quality=0.5,
            lessons_learned=None,
            occurred_at=datetime.now(),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_choice_outcome_recorded(event)
            warn_calls = [c for c in mock_warn.call_args_list if "failed" in str(c).lower()]
            assert len(warn_calls) == 1

    @pytest.mark.asyncio
    async def test_principle_aligned_positive_outcome(
        self,
        service_full: ChoiceEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
    ):
        """Positive principle-aligned outcome is logged."""
        mock_choice = MagicMock()
        mock_choice.description = "Aligned choice"
        mock_backend.get.return_value = Result.ok(mock_choice)
        mock_relationships.get_related_uids.return_value = Result.ok(["principle_abc"])

        event = ChoiceOutcomeRecorded(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            outcome_quality=0.85,
            lessons_learned=None,
            occurred_at=datetime.now(),
        )

        with patch.object(service_full.logger, "info") as mock_log:
            await service_full.handle_choice_outcome_recorded(event)
            log_calls = [c for c in mock_log.call_args_list if "positive outcome" in str(c).lower()]
            assert len(log_calls) == 1

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = ChoiceOutcomeRecorded(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            outcome_quality=0.5,
            lessons_learned=None,
            occurred_at=datetime.now(),
        )

        # Should NOT raise
        await service.handle_choice_outcome_recorded(event)


# ---------------------------------------------------------------------------
# handle_choice_made tests
# ---------------------------------------------------------------------------


class TestHandleChoiceMade:
    @pytest.mark.asyncio
    async def test_happy_path(self, service_full: ChoiceEventHandlerService, mock_backend: Mock):
        """Choice made is analyzed and insights logged."""
        mock_choice = _make_mock_choice()
        mock_backend.get.return_value = Result.ok(mock_choice)

        event = ChoiceMade(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            selected_option="option_a",
            confidence=0.8,
            occurred_at=datetime.now(),
        )

        with patch.object(service_full.logger, "info") as mock_log:
            await service_full.handle_choice_made(event)
            log_calls = [c for c in mock_log.call_args_list if "choice made" in str(c).lower()]
            assert len(log_calls) >= 1

    @pytest.mark.asyncio
    async def test_high_confidence_principle_aligned_persists_insight(
        self,
        service_full: ChoiceEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
        mock_insight_store: AsyncMock,
    ):
        """High-confidence principle-aligned decision persists positive insight."""
        mock_choice = _make_mock_choice()
        mock_backend.get.return_value = Result.ok(mock_choice)
        mock_relationships.get_related_uids.return_value = Result.ok(["principle_abc"])

        event = ChoiceMade(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            selected_option="option_a",
            confidence=0.85,
            occurred_at=datetime.now(),
        )

        await service_full.handle_choice_made(event)

        # Insight store should have been called
        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert "Principle-Aligned" in insight.title

    @pytest.mark.asyncio
    async def test_complex_unaligned_persists_alignment_insight(
        self,
        service_full: ChoiceEventHandlerService,
        mock_backend: Mock,
        mock_relationships: AsyncMock,
        mock_insight_store: AsyncMock,
    ):
        """Complex decision without principle alignment persists alignment insight."""
        mock_choice = _make_mock_choice(complexity=7.0)
        mock_backend.get.return_value = Result.ok(mock_choice)
        # No principles aligned
        mock_relationships.get_related_uids.return_value = Result.ok([])

        event = ChoiceMade(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            selected_option="option_b",
            confidence=0.6,
            occurred_at=datetime.now(),
        )

        await service_full.handle_choice_made(event)

        mock_insight_store.create_insight.assert_called_once()
        insight = mock_insight_store.create_insight.call_args[0][0]
        assert "Without Principle" in insight.title

    @pytest.mark.asyncio
    async def test_no_insight_without_store(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """No insight persisted when insight_store is None."""
        mock_choice = _make_mock_choice(complexity=7.0)
        mock_backend.get.return_value = Result.ok(mock_choice)

        event = ChoiceMade(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            selected_option="option_a",
            confidence=0.85,
            occurred_at=datetime.now(),
        )

        # Should complete without error (no insight_store)
        await service.handle_choice_made(event)

    @pytest.mark.asyncio
    async def test_missing_choice_early_return(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """Handler returns early when choice not found."""
        mock_backend.get.return_value = Result.ok(None)

        event = ChoiceMade(
            choice_uid="choice_missing",
            user_uid="user_mike",
            selected_option="option_a",
            confidence=0.5,
            occurred_at=datetime.now(),
        )

        with patch.object(service.logger, "warning") as mock_warn:
            await service.handle_choice_made(event)
            warn_calls = [c for c in mock_warn.call_args_list if "not found" in str(c).lower()]
            assert len(warn_calls) == 1

    @pytest.mark.asyncio
    async def test_fire_and_forget_contract(
        self, service: ChoiceEventHandlerService, mock_backend: Mock
    ):
        """Exceptions are logged, never propagated."""
        from neo4j.exceptions import ServiceUnavailable

        mock_backend.get.side_effect = ServiceUnavailable("connection lost")

        event = ChoiceMade(
            choice_uid="choice_test_abc",
            user_uid="user_mike",
            selected_option="option_a",
            confidence=0.5,
            occurred_at=datetime.now(),
        )

        # Should NOT raise
        await service.handle_choice_made(event)
