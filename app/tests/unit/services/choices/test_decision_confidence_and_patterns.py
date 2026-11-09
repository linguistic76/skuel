"""A decision's confidence is stored on the choice, and the decision-pattern reads report
only what the stored choices hold.

- ``make_decision`` writes ``decision_confidence`` beside the rationale; a confidence the
  learner did not state is written as nothing, and ``ChoiceMade`` carries the same value.
- Each of the decide form's five levels reaches the decision handler as the value the
  form posted, in its own ``categorize_confidence`` band, and only the two sure levels
  earn the high-confidence insight.
- ``get_decision_patterns`` averages confidence and satisfaction over the choices that
  record them, with how many those are; ``get_domain_decision_patterns`` averages the
  decision quality of each domain's decided choices; ``get_choice_quality_correlations``
  reports no correlation, sentence or recommendation it has not computed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events import BaseEvent, ChoiceMade
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceDecisionRequest
from core.models.enums.entity_enums import Domain
from core.services.choices.choice_event_handler_service import (
    ChoiceEventHandlerService,
    categorize_confidence,
)
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend
from ui.activities.choices_views import DECISION_CONFIDENCE_LEVELS

USER = "user_decision_confidence"
UID = "choice_1"
DECIDED_AT = datetime(2026, 11, 1, 9, 0)


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _options(count: int = 2) -> tuple[ChoiceOption, ...]:
    return tuple(ChoiceOption(uid=f"option_{i}", title=f"Option {i}") for i in range(count))


def _choice(uid: str = UID, **fields: Any) -> Choice:  # boundary: Choice field values
    return Choice(uid=uid, user_uid=USER, title="Where to practise", options=_options(), **fields)


def _decided(uid: str, **fields: Any) -> Choice:  # boundary: Choice field values
    return _choice(uid, decided_at=DECIDED_AT, selected_option_uid="option_0", **fields)


def _core(
    current: Choice,
) -> tuple[ChoicesCoreService, StatusGuardedWriteRecorder[Choice], _RecordingBus]:
    backend, recorder = guarded_backend(current, current)
    bus = _RecordingBus()
    return ChoicesCoreService(backend=backend, event_bus=bus), recorder, bus


def _intelligence(choices: list[Choice]) -> ChoicesIntelligenceService:
    backend = MagicMock()
    backend.find_by_date_range = AsyncMock(return_value=Result.ok(choices))
    service = ChoicesIntelligenceService(
        backend=backend,
        cross_domain_query=MagicMock(),
        relationship_service=MagicMock(),
    )
    service._fetch_alignment_links = AsyncMock(return_value=Result.ok(({}, {})))  # type: ignore[method-assign]
    return service


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------


class TestTheRequest:
    def test_an_unstated_confidence_is_none(self) -> None:
        assert ChoiceDecisionRequest(selected_option_uid="option_0").confidence is None

    def test_the_form_posts_a_level_as_text(self) -> None:
        request = ChoiceDecisionRequest.model_validate(
            {"selected_option_uid": "option_0", "confidence": "0.7"}
        )
        assert request.confidence == 0.7


@pytest.mark.asyncio
class TestTheDecisionStoresItsConfidence:
    async def test_a_stated_confidence_is_written_and_published(self) -> None:
        service, recorder, bus = _core(_choice())

        result = await service.make_decision(UID, "option_1", confidence=0.7)

        assert result.is_ok, result
        assert recorder.last_updates["decision_confidence"] == 0.7
        assert [event.confidence for event in bus.of(ChoiceMade)] == [0.7]

    async def test_an_unstated_confidence_writes_none(self) -> None:
        service, recorder, bus = _core(_choice())

        result = await service.make_decision(UID, "option_1")

        assert result.is_ok, result
        assert recorder.last_updates["decision_confidence"] is None
        assert [event.confidence for event in bus.of(ChoiceMade)] == [None]


@pytest.mark.asyncio
class TestTheHandlerReadsTheStatedLevel:
    async def test_each_form_level_lands_in_its_own_band(self) -> None:
        """The five levels, posted through the request into the real write, give five
        bands of ``categorize_confidence``, lowest to highest."""
        bands = []
        for value, _label in DECISION_CONFIDENCE_LEVELS:
            request = ChoiceDecisionRequest.model_validate(
                {"selected_option_uid": "option_0", "confidence": value}
            )
            service, recorder, bus = _core(_choice())
            await service.make_decision(UID, "option_0", confidence=request.confidence)
            stored = recorder.last_updates["decision_confidence"]
            (made,) = bus.of(ChoiceMade)
            assert made.confidence == stored == float(value)
            bands.append(categorize_confidence(stored))

        assert bands == ["very_low", "low", "moderate", "high", "very_high"]

    @pytest.mark.parametrize(
        ("value", "earns"),
        [(value, float(value) >= 0.7) for value, _label in DECISION_CONFIDENCE_LEVELS]
        + [(None, False)],
    )
    async def test_only_a_sure_decision_a_principle_informs_earns_the_insight(
        self, value: str | None, earns: bool
    ) -> None:
        choice = _choice()
        service, _recorder, bus = _core(choice)
        await service.make_decision(
            UID, "option_0", confidence=float(value) if value is not None else None
        )
        (made,) = bus.of(ChoiceMade)

        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(choice))
        relationships = MagicMock()
        relationships.get_related_uids = AsyncMock(return_value=Result.ok(["principle_1"]))
        insights = MagicMock()
        insights.create_insight = AsyncMock(return_value=Result.ok(True))
        handler = ChoiceEventHandlerService(
            backend=backend, relationship_service=relationships, insight_store=insights
        )

        await handler.handle_choice_made(made)

        assert insights.create_insight.called is earns

    async def test_an_unstated_confidence_still_reaches_the_complexity_insight(self) -> None:
        """The handler gets past an unstated confidence: a complex choice no principle
        informs earns the insight that reads no confidence, and records none."""
        complex_choice = Choice(
            uid=UID,
            user_uid=USER,
            title="Where to live",
            options=_options(3),
            decision_criteria=("cost", "time", "weather"),
        )
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(complex_choice))
        relationships = MagicMock()
        relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
        insights = MagicMock()
        insights.create_insight = AsyncMock(return_value=Result.ok(True))
        handler = ChoiceEventHandlerService(
            backend=backend, relationship_service=relationships, insight_store=insights
        )

        await handler.handle_choice_made(
            ChoiceMade(choice_uid=UID, user_uid=USER, selected_option="option_0", confidence=None)
        )

        (insight,) = [call.args[0] for call in insights.create_insight.call_args_list]
        assert insight.title == "Complex Decision Without Principle Guidance"
        assert insight.supporting_data["confidence"] is None


# ---------------------------------------------------------------------------
# The decision-pattern reads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDecisionPatternAverages:
    async def test_each_average_covers_the_choices_that_record_it(self) -> None:
        service = _intelligence(
            [
                _decided("c1", decision_confidence=0.9, satisfaction_score=5),
                _decided("c2", decision_confidence=0.5),
                _decided("c3", satisfaction_score=3),
                _choice("c4"),
            ]
        )

        result = await service.get_decision_patterns(USER, days=30)

        assert result.is_ok, result
        quality = result.value["decision_quality"]
        assert quality["average_confidence"] == pytest.approx(0.7)
        assert quality["choices_with_confidence"] == 2
        assert quality["average_satisfaction"] == pytest.approx(0.8)
        assert quality["choices_with_satisfaction"] == 2

    async def test_with_none_recorded_each_average_is_none(self) -> None:
        service = _intelligence([_decided("c1"), _choice("c2")])

        result = await service.get_decision_patterns(USER, days=30)

        assert result.is_ok, result
        quality = result.value["decision_quality"]
        assert quality["average_confidence"] is None
        assert quality["choices_with_confidence"] == 0
        assert quality["average_satisfaction"] is None
        assert quality["choices_with_satisfaction"] == 0

    async def test_an_empty_window_has_no_averages(self) -> None:
        result = await _intelligence([]).get_decision_patterns(USER, days=30)

        assert result.is_ok, result
        quality = result.value["decision_quality"]
        assert quality["average_confidence"] is None
        assert quality["average_satisfaction"] is None


@pytest.mark.asyncio
class TestDomainDecisionQuality:
    async def test_the_average_is_over_the_domains_decided_choices(self) -> None:
        reasoned = _decided("c1", decision_rationale="the house is quiet", domain=Domain.PERSONAL)
        bare = _decided("c2", domain=Domain.PERSONAL)
        undecided = _choice("c3", domain=Domain.PERSONAL)
        pending_only = _choice("c4", domain=Domain.HEALTH)
        service = _intelligence([reasoned, bare, undecided, pending_only])

        result = await service.get_domain_decision_patterns(USER, days=30)

        assert result.is_ok, result
        patterns = result.value["domain_patterns"]
        expected = (reasoned.get_decision_quality_score() + bare.get_decision_quality_score()) / 2
        assert patterns["personal"]["avg_quality_score"] == pytest.approx(expected)
        assert patterns["personal"]["decided_count"] == 2
        assert patterns["personal"]["choice_count"] == 3
        assert patterns["health"]["avg_quality_score"] is None
        assert patterns["health"]["decided_count"] == 0


@pytest.mark.asyncio
class TestQualityCorrelations:
    @pytest.mark.parametrize(
        "choices",
        [
            [],
            [
                _decided("c1", decision_confidence=0.9, satisfaction_score=5),
                _decided("c2", decision_confidence=0.3, satisfaction_score=2),
                _choice("c3"),
            ],
        ],
        ids=["empty", "rated"],
    )
    async def test_no_correlation_is_reported_that_was_not_computed(
        self, choices: list[Choice]
    ) -> None:
        result = await _intelligence(choices).get_choice_quality_correlations(USER, days=30)

        assert result.is_ok, result
        report = result.value
        assert report["correlations"] == {}
        assert "insights" not in report
        assert "recommendations" not in report
        assert report["reason"]
        assert report["total_choices_analyzed"] == len(choices)
        assert report["choices_with_satisfaction"] == (2 if choices else 0)
        assert report["choices_with_confidence"] == (2 if choices else 0)
