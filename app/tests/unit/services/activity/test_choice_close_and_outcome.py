"""How a decided choice turned out, a spawned choice's first state, and what reads them.

- ``evaluate_choice_outcome`` plans from the locked choice
  (``ChoicesBackend.rewrite_choice_under_lock``): a choice not yet decided is refused
  and nothing is written; the write carries ``satisfaction_score``, ``actual_outcome``
  and ``lessons_learned`` alone; ``ChoiceOutcomeRecorded`` carries the outcome's quality
  from the satisfaction and the lessons one per line.
- ``outcome_quality`` puts each satisfaction level in its own band of the outcome
  handler, held to the handler itself.
- A choice spawned by a PathStep engagement is an undecided draft with no rationale.
- The two readers that average satisfaction count only the choices that carry one.
- The page: the outcome form's levels are the scale, and the card posts the status its
  choice's state allows.

Closing and reopening through ``update_choice`` are held in
``tests/unit/services/test_completion_stamping.py::TestChoicesChokepoint``; the doors, the
lock and the handler over a real graph in ``tests/integration/test_choice_outcome_door.py``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml

from core.constants import SatisfactionScale
from core.events import BaseEvent, ChoiceOutcomeRecorded
from core.events.embedding_events import ChoiceEmbeddingRequested
from core.models.choice.choice import Choice, outcome_quality
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceEvaluationRequest
from core.models.enums.entity_enums import EntityStatus
from core.models.templates.choice_template import ChoiceTemplate
from core.models.update_contracts import StatusWriteGuard
from core.services.choices.choice_event_handler_service import (
    ChoiceEventHandlerService,
    categorize_outcome_quality,
)
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.cross_domain.cross_domain_types import (
    ChoiceAlignmentDetail,
    ChoicePrincipleAdherence,
)
from core.services.ps_engagement._spawn_orchestrator import CHOICE_SPEC, _build
from core.utils.result_simplified import ErrorCategory, Result
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend
from ui.activities.choices_views import SATISFACTION_LEVELS, ChoiceCard, ChoiceDetailView

USER = "user_choice_outcome"
UID = "choice_1"
DECIDED_AT = datetime(2026, 11, 1, 9, 0)


class _RecordingBus:
    """Records what the service publishes; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _options() -> tuple[ChoiceOption, ...]:
    return (
        ChoiceOption(uid="option_0", title="Mornings"),
        ChoiceOption(uid="option_1", title="Evenings"),
    )


def _choice(uid: str = UID, **fields: Any) -> Choice:  # boundary: Choice field values
    return Choice(uid=uid, user_uid=USER, title="When to practise", options=_options(), **fields)


def _decided(uid: str = UID, **fields: Any) -> Choice:  # boundary: Choice field values
    return _choice(uid, decided_at=DECIDED_AT, selected_option_uid="option_0", **fields)


def _service(
    current: Choice,
) -> tuple[ChoicesCoreService, StatusGuardedWriteRecorder[Choice], _RecordingBus]:
    backend, recorder = guarded_backend(current, current)
    bus = _RecordingBus()
    return ChoicesCoreService(backend=backend, event_bus=bus), recorder, bus


def _evaluation(score: int = 4, *lessons: str) -> ChoiceEvaluationRequest:
    return ChoiceEvaluationRequest(
        satisfaction_score=score, actual_outcome="I kept to it", lessons_learned=list(lessons)
    )


# ---------------------------------------------------------------------------
# evaluate_choice_outcome
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluateChoiceOutcome:
    @pytest.mark.parametrize(
        "current",
        [
            _decided(status=EntityStatus.ACTIVE),
            _decided(status=EntityStatus.COMPLETED),
            _decided(status=EntityStatus.ARCHIVED),
            _choice(status=EntityStatus.COMPLETED),
        ],
        ids=["active-decided", "completed-decided", "archived-decided", "closed-no-decision"],
    )
    async def test_it_writes_the_outcome_fields_alone(self, current: Choice) -> None:
        """Open or closed: the write names no status, so it can neither reopen a closed
        choice nor undo a close made at the same moment."""
        service, recorder, _bus = _service(current)

        result = await service.evaluate_choice_outcome(UID, _evaluation(4, "Start small"))

        assert result.is_ok, result
        assert recorder.last_updates == {
            "satisfaction_score": 4,
            "actual_outcome": "I kept to it",
            "lessons_learned": ["Start small"],
        }
        assert recorder.last_guard == StatusWriteGuard()

    @pytest.mark.parametrize(
        "current",
        [
            _choice(status=EntityStatus.DRAFT),
            _choice(status=EntityStatus.ACTIVE),
            _choice(status=EntityStatus.ARCHIVED),
        ],
        ids=["draft", "active-no-decision", "archived-no-decision"],
    )
    async def test_a_choice_not_yet_decided_is_refused(self, current: Choice) -> None:
        service, recorder, bus = _service(current)

        result = await service.evaluate_choice_outcome(UID, _evaluation())

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.VALIDATION
        assert "Decide this choice before" in result.expect_error().message
        assert recorder.calls == [], "a refusal writes nothing"
        assert bus.events == []

    async def test_the_event_carries_the_quality_and_the_lessons_one_per_line(self) -> None:
        service, _recorder, bus = _service(_decided(status=EntityStatus.ACTIVE))

        result = await service.evaluate_choice_outcome(
            UID, _evaluation(5, "Start small", "Keep a log")
        )

        assert result.is_ok, result
        [event] = bus.of(ChoiceOutcomeRecorded)
        assert event.choice_uid == UID
        assert event.outcome_quality == 1.0
        assert event.lessons_learned == "Start small\nKeep a log"
        assert len(bus.of(ChoiceEmbeddingRequested)) == 1, "actual_outcome is embedded"

    async def test_no_lessons_is_none_on_the_event(self) -> None:
        service, _recorder, bus = _service(_decided(status=EntityStatus.ACTIVE))

        result = await service.evaluate_choice_outcome(UID, _evaluation(2))

        assert result.is_ok, result
        [event] = bus.of(ChoiceOutcomeRecorded)
        assert event.lessons_learned is None
        assert event.outcome_quality == 0.25


# ---------------------------------------------------------------------------
# outcome_quality against the handler that reads it
# ---------------------------------------------------------------------------


class TestOutcomeQuality:
    def test_each_level_lands_in_its_own_band(self) -> None:
        levels = range(SatisfactionScale.LOWEST, SatisfactionScale.HIGHEST + 1)
        assert [categorize_outcome_quality(outcome_quality(level)) for level in levels] == [
            "bad",
            "poor",
            "neutral",
            "good",
            "excellent",
        ]


@pytest.mark.asyncio
class TestOutcomeHandler:
    """The handler's principle-correlation cuts, reached by real ratings."""

    @staticmethod
    def _handler(choice: Choice) -> tuple[ChoiceEventHandlerService, MagicMock]:
        backend = MagicMock()
        backend.get = AsyncMock(return_value=Result.ok(choice))
        relationships = MagicMock()
        relationships.get_related_uids = AsyncMock(return_value=Result.ok(["principle_1"]))
        handler = ChoiceEventHandlerService(backend=backend, relationship_service=relationships)
        logger = MagicMock()
        handler.logger = logger
        return handler, logger

    @staticmethod
    def _logged(logger: MagicMock) -> list[str]:
        return [str(call.kwargs["extra"]["event_type"]) for call in logger.info.call_args_list]

    @pytest.mark.parametrize(
        ("score", "correlation"),
        [
            (1, ["choice.principle_correlation.review_needed"]),
            (2, ["choice.principle_correlation.review_needed"]),
            (3, []),
            (4, ["choice.principle_correlation.positive"]),
            (5, ["choice.principle_correlation.positive"]),
        ],
    )
    async def test_a_principle_aligned_outcome_reaches_its_band(
        self, score: int, correlation: list[str]
    ) -> None:
        handler, logger = self._handler(_decided(status=EntityStatus.ACTIVE))
        event = ChoiceOutcomeRecorded(
            choice_uid=UID,
            user_uid=USER,
            outcome_quality=outcome_quality(score),
            lessons_learned=None,
        )

        await handler.handle_choice_outcome_recorded(event)

        assert self._logged(logger) == ["choice.outcome.analyzed", *correlation]


# ---------------------------------------------------------------------------
# A spawned choice
# ---------------------------------------------------------------------------


class TestSpawnedChoice:
    def test_it_is_an_undecided_draft_without_the_templates_rationale(self) -> None:
        template = ChoiceTemplate(
            uid="ct.when",
            title="When will you practise",
            status=EntityStatus.ACTIVE,  # an engagement spawns only ACTIVE templates
            decision_rationale="the template's reasoning",
            options=_options(),
        )

        choice = _build(
            CHOICE_SPEC, template, USER, "ps.step", DECIDED_AT, {"ct.when": "choice_spawned"}
        )

        assert choice.status is EntityStatus.DRAFT
        assert choice.decision_rationale is None
        assert choice.options == _options(), "the options are the template's"
        assert choice.is_pending()
        assert choice.options_open()

    def test_the_spawn_copies_neither_field(self) -> None:
        assert {"status", "decision_rationale"}.isdisjoint(CHOICE_SPEC.copied_fields())
        assert {"title", "options", "choice_type"} <= CHOICE_SPEC.copied_fields()


# ---------------------------------------------------------------------------
# Readers that average satisfaction
# ---------------------------------------------------------------------------


def _intelligence(backend: object, cross_domain_query: object) -> ChoicesIntelligenceService:
    return ChoicesIntelligenceService(
        backend=backend,  # type: ignore[arg-type]  # a stub with the one read used
        cross_domain_query=cross_domain_query,  # type: ignore[arg-type]
        relationship_service=MagicMock(),
    )


@pytest.mark.asyncio
class TestSatisfactionAverages:
    async def test_decision_patterns_average_the_recorded_ratings(self) -> None:
        backend = MagicMock()
        backend.find_by_date_range = AsyncMock(
            return_value=Result.ok(
                [
                    _decided(uid="c1", satisfaction_score=5),
                    _decided(uid="c2", satisfaction_score=3),
                    _choice(uid="c3"),
                ]
            )
        )
        service = _intelligence(backend, None)
        service._fetch_alignment_links = AsyncMock(return_value=Result.ok(({}, {})))  # type: ignore[method-assign]

        result = await service.get_decision_patterns(USER, days=30)

        assert result.is_ok, result
        assert result.value["decision_quality"]["average_satisfaction"] == pytest.approx(0.8)

    async def test_decision_patterns_with_no_rating_read_zero(self) -> None:
        backend = MagicMock()
        backend.find_by_date_range = AsyncMock(return_value=Result.ok([_choice(uid="c1")]))
        service = _intelligence(backend, None)
        service._fetch_alignment_links = AsyncMock(return_value=Result.ok(({}, {})))  # type: ignore[method-assign]

        result = await service.get_decision_patterns(USER, days=30)

        assert result.is_ok, result
        assert result.value["decision_quality"]["average_satisfaction"] == 0.0

    async def test_principle_adherence_averages_only_the_rated_choices(self) -> None:
        """An unrated choice has no satisfaction, not a zero: 5 and 3 average 4 (0.8),
        whatever unrated choices the principle also informed."""
        cross_domain = MagicMock()
        cross_domain.get_choice_principle_adherence = AsyncMock(
            return_value=Result.ok(
                ChoicePrincipleAdherence(
                    total_choices=3,
                    aligned_count=3,
                    choice_details=(
                        ChoiceAlignmentDetail("c1", ("principle_1",), 5.0),
                        ChoiceAlignmentDetail("c2", ("principle_1",), None),
                        ChoiceAlignmentDetail("c3", ("principle_1",), 3.0),
                    ),
                )
            )
        )
        service = _intelligence(MagicMock(), cross_domain)

        result = await service.analyze_principle_adherence(USER)

        assert result.is_ok, result
        breakdown = result.value["principle_breakdown"]["principle_1"]
        assert breakdown["aligned_count"] == 3
        assert breakdown["avg_satisfaction"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------


def _satisfaction_select(html: str) -> str:
    select = re.search(r'<select[^>]*name="satisfaction_score".*?</select>', html, re.DOTALL)
    assert select is not None
    return select.group(0)


class TestThePage:
    def test_the_outcome_forms_levels_are_the_scale(self) -> None:
        assert [level for level, _label in SATISFACTION_LEVELS] == list(
            range(SatisfactionScale.LOWEST, SatisfactionScale.HIGHEST + 1)
        )

    @pytest.mark.parametrize(
        ("current", "posts", "title"),
        [
            (_choice(status=EntityStatus.DRAFT), "completed", "Mark as completed"),
            (_decided(status=EntityStatus.ACTIVE), "completed", "Mark as completed"),
            (_decided(status=EntityStatus.ARCHIVED), "completed", "Mark as completed"),
            (_decided(status=EntityStatus.COMPLETED), "active", "Reopen"),
            (_choice(status=EntityStatus.COMPLETED), "draft", "Reopen"),
        ],
        ids=["draft", "decided", "archived-decided", "closed-decided", "closed-no-decision"],
    )
    def test_the_card_posts_the_status_its_state_allows(
        self, current: Choice, posts: str, title: str
    ) -> None:
        """A decided choice reopens active, never draft; one closed undecided reopens a draft."""
        html = to_xml(ChoiceCard(current, []))
        button = re.search(r"<button[^>]*data-choice-status[^>]*>", html)
        assert button is not None
        assert f'data-choice-status="{posts}"' in button.group(0)
        assert f'''hx-vals='{{"status": "{posts}"}}\'''' in button.group(0)
        assert f'title="{title}"' in button.group(0)

    def test_an_undecided_choice_has_no_outcome_form(self) -> None:
        assert "data-choice-outcome" not in to_xml(ChoiceDetailView(_choice(), []))

    def test_a_decided_choice_asks_how_it_turned_out(self) -> None:
        html = to_xml(ChoiceDetailView(_decided(status=EntityStatus.ACTIVE), []))
        assert "How did it turn out?" in html
        assert "data-choice-outcome" in html
        assert "<details" not in html, "with no outcome the form stands open"
        assert not re.search(r'<option value="\d" selected', _satisfaction_select(html)), (
            "no level is chosen for the learner"
        )

    def test_a_recorded_outcome_shows_and_fills_the_form_that_updates_it(self) -> None:
        choice = _decided(
            status=EntityStatus.COMPLETED,
            satisfaction_score=4,
            actual_outcome="I kept to it",
            lessons_learned=("Start small", "Keep a log"),
        )
        html = to_xml(ChoiceDetailView(choice, []))
        assert "Update the outcome" in html
        assert "<details" in html
        assert '<option value="4" selected>' in _satisfaction_select(html)
        lessons = re.search(r"<textarea[^>]*lessons_learned[^>]*>(.*?)</textarea>", html, re.DOTALL)
        assert lessons is not None
        assert lessons.group(1) == "Start small\nKeep a log"
        assert "★★★★☆" in html
