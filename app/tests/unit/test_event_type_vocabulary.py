"""
Event-type vocabulary: one lowercase StrEnum, everywhere
========================================================

``EventType`` became a lowercase ``StrEnum`` in ``core/models/enums`` (2026-08),
replacing an UPPERCASE constants bag outside the enums package. Because every
writer spoke UPPERCASE while the search facet and the ranking learning-type set
compared lowercase, no reader could ever match a persisted row. These tests pin
the seams the consolidation converged:

- the recurring-event writer stamps a real member (``"RECURRING"`` was a
  category error — recurrence is ``recurrence_pattern``'s job, one line below);
- the search facet offers exactly the canonical vocabulary (it used to offer
  ActivityType names — milestone/practice/review — no Event ever carried);
- the ranking learning-type set holds only real members, so EVENT_TYPE_PRIORITY
  (weight 0.10) fires for ``learning`` rows and no longer for non-member
  strings like ``"practice"`` that the old ad-hoc set accepted.

Casing canonicalization at ingestion is pinned in
``test_enum_field_registry_and_casing.py`` (event_type joined the registry).
"""

from datetime import date, time, timedelta

import pytest

from core.models.enums import EntityStatus, EventType, RecurrencePattern
from core.models.event.event import Event
from core.models.search.scoring import ScoringComponent, score_event
from core.services.events.events_scheduling_service import EventsSchedulingService
from core.services.user.unified_user_context import UserContext
from core.utils.result_simplified import Result
from ui.search.components import _EVENT_TYPE_OPTIONS


class _CapturingBackend:
    """Records every model handed to ``create``; returns it as the created row."""

    def __init__(self) -> None:
        self.created: list[Event] = []

    async def create(self, model: Event) -> Result[Event]:
        self.created.append(model)
        return Result.ok(model)


class _FixedScheduleService(EventsSchedulingService):
    """Pin the optimizer to two dates so the test drives only the create loop."""

    async def optimize_recurring_schedule(
        self,
        user_uid: str,
        pattern: RecurrencePattern,
        preferred_time: time | None = None,
        days_to_schedule: int = 30,
    ) -> Result[list[date]]:
        return Result.ok([date.today() + timedelta(days=1), date.today() + timedelta(days=2)])


class TestRecurringEventsWriteRealTypes:
    async def test_created_events_carry_a_canonical_member(self) -> None:
        backend = _CapturingBackend()
        service = _FixedScheduleService(backend)  # type: ignore[arg-type]  # boundary: test double

        result = await service.create_recurring_events(
            user_uid="user_demo",
            title="Morning meditation",
            pattern=RecurrencePattern.DAILY,
        )

        assert result.is_ok
        assert backend.created, "the create loop persisted nothing"
        member_values = {member.value for member in EventType}
        for event in backend.created:
            assert event.event_type in member_values, (
                f"event_type {event.event_type!r} is not an EventType member — "
                "recurrence belongs in recurrence_pattern, not event_type"
            )
            assert event.recurrence_pattern == RecurrencePattern.DAILY


class TestSearchFacetVocabulary:
    def test_event_type_facet_offers_exactly_the_canonical_vocabulary(self) -> None:
        values = [value for value, _label in _EVENT_TYPE_OPTIONS if value]
        assert values == [member.value for member in EventType]

    def test_facet_keeps_the_all_sentinel_first(self) -> None:
        assert _EVENT_TYPE_OPTIONS[0] == ("", "All")


def _event(event_type: str) -> Event:
    """An Event as a persisted row carries it: event_type is a plain string."""
    return Event(
        uid="event.scoring_probe",
        user_uid="user_demo",
        title="Scoring probe",
        event_date=date.today() + timedelta(days=2),
        event_type=event_type,
        status=EntityStatus.SCHEDULED,
    )


def _context() -> UserContext:
    return UserContext(user_uid="user_demo", username="test_user")


def _type_component(event_type: str) -> float:
    score = score_event(_event(event_type), _context())
    component = next(
        c for c in score.components if c.component is ScoringComponent.EVENT_TYPE_PRIORITY
    )
    return component.normalized


class TestEventTypePriorityVocabulary:
    def test_practice_is_not_a_learning_type(self) -> None:
        # "practice" sat in the old ad-hoc {"study", "learning", "practice"} set
        # but is not an EventType member — no persisted row may carry it, so it
        # must not earn the learning boost.
        assert _type_component("practice") == 0.5

    def test_learning_member_gets_the_boost(self) -> None:
        assert _type_component(EventType.LEARNING.value) == 1.0

    def test_boost_is_bounded_to_the_component_weight(self) -> None:
        # The revived branch may shift ranking by exactly the component weight
        # spread (0.10 * (1.0 - 0.5)) and never dominate time proximity (0.40).
        context = _context()
        learning = score_event(_event(EventType.LEARNING.value), context)
        social = score_event(_event(EventType.SOCIAL.value), context)
        assert learning.total - social.total == pytest.approx(0.05)
        assert 0.0 <= social.total < learning.total <= 1.0
