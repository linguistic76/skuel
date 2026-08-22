"""Canonical completion fields — the write-path truth pass (completion-stamping arc, PR-1).

Editing a long-completed activity must never re-date its completion, so every
domain gets a canonical completion field that only completion writes touch:
Task ``completion_date`` (established), Goal ``achieved_date`` (canonical on
the model since #725, but the intent + ``complete_goal`` kept writing the
legacy ``completion_date`` alias until this pass), Event/Habit/Choice
``completed_at`` (datetime lifecycle stamp).

These tests pin the PR-1 contract:

- ``GoalUpdateIntent`` carries ``achieved_date`` and the legacy
  ``completion_date`` field is GONE (an alias that resurrects re-splits the
  writers from the readers — ``migrate_activity_completion_aliases.py`` exists
  precisely because it did).
- ``complete_goal`` stamps ``achieved_date`` through the intent.
- Event/Choice carry ``completed_at`` across all four layers
  (model / DTO / intent / request), round-tripping the writer storage shape
  (ISO-8601 strings on the node — fixtures mirror writer shapes, #1116).
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.models.choice.choice import Choice
from core.models.choice.choice_dto import ChoiceDTO
from core.models.choice.choice_request import ChoiceUpdateRequest
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.event.event_request import EventUpdateRequest
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.goal.goal_request import GoalUpdateRequest
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.sentinels import UNSET
from core.services.goals.goals_core_service import GoalsCoreService
from core.utils.result_simplified import Result

STAMP = datetime(2026, 8, 22, 10, 30, tzinfo=UTC)


class TestGoalAchievedDateIntent:
    """The intent speaks the canonical Goal vocabulary — no legacy alias."""

    def test_intent_has_achieved_date_not_completion_date(self):
        names = {f.name for f in fields(GoalUpdateIntent)}
        assert "achieved_date" in names
        assert "completion_date" not in names, (
            "GoalUpdateIntent grew the legacy `completion_date` alias back — "
            "the canonical Goal field is `achieved_date` (One Path Forward; "
            "see scripts/migrate_activity_completion_aliases.py)"
        )

    def test_to_changes_carries_achieved_date(self):
        changes = GoalUpdateIntent(achieved_date=date(2026, 8, 22)).to_changes()
        assert changes == {"achieved_date": date(2026, 8, 22)}

    def test_to_changes_downcasts_datetime_achieved_date(self):
        # 766-class guard: a stray datetime in a date column must lose its time.
        changes = GoalUpdateIntent(achieved_date=datetime(2026, 8, 22, 9, 30)).to_changes()
        assert changes["achieved_date"] == date(2026, 8, 22)
        assert not isinstance(changes["achieved_date"], datetime)

    def test_update_request_still_carries_no_completion_field(self):
        # The generic update door doesn't set completion — that authority stays
        # with complete_goal / the auto-achieve paths (and PR-2's stamp helper).
        assert "achieved_date" not in GoalUpdateRequest.model_fields
        assert "completion_date" not in GoalUpdateRequest.model_fields


@pytest.mark.asyncio
class TestCompleteGoalWriter:
    """``complete_goal`` stamps ``achieved_date`` — never the legacy alias."""

    def _service(self) -> tuple[GoalsCoreService, AsyncMock]:
        class _InertBackend:
            """Construction-only collaborator — update_goal is patched below."""

            def __getattr__(self, name: str) -> Any:
                return self

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return self

        service = GoalsCoreService(backend=_InertBackend(), event_bus=None)
        update_goal = AsyncMock(return_value=Result.ok(True))
        service.update_goal = update_goal  # type: ignore[method-assign]
        return service, update_goal

    async def test_defaults_achieved_date_to_today(self):
        service, update_goal = self._service()

        result = await service.complete_goal("goal_x")

        assert result.is_ok
        intent = update_goal.call_args.args[1]
        assert intent.status == EntityStatus.COMPLETED.value
        assert intent.progress_percentage == 100.0
        assert intent.achieved_date == date.today()

    async def test_explicit_iso_date_is_parsed(self):
        service, update_goal = self._service()

        await service.complete_goal("goal_x", achieved_date="2026-08-01")

        intent = update_goal.call_args.args[1]
        assert intent.achieved_date == date(2026, 8, 1)


class TestEventCompletedAt:
    """Event ``completed_at`` exists on all four layers and round-trips."""

    def test_model_accepts_completed_at(self):
        event = Event(uid="event_c1", user_uid="user_t", title="Retro", completed_at=STAMP)
        assert event.completed_at == STAMP

    def test_dto_roundtrips_writer_storage_shape(self):
        # Writers store ISO strings on the node (mapper .isoformat()) — the DTO
        # must parse that shape back and emit it again.
        dto = EventDTO.from_dict(
            {
                "uid": "event_c2",
                "title": "Retro",
                "entity_type": "event",
                "user_uid": "user_t",
                "completed_at": STAMP.isoformat(),
            }
        )
        assert dto.completed_at == STAMP
        assert (
            EventDTO.create_event("user_t", "Retro", completed_at=STAMP).to_dict()["completed_at"]
            == STAMP.isoformat()
        )

    def test_intent_carries_completed_at_untouched(self):
        # A datetime lifecycle stamp — to_changes must NOT date-downcast it.
        changes = EventUpdateIntent(completed_at=STAMP).to_changes()
        assert changes == {"completed_at": STAMP}
        assert EventUpdateIntent().to_changes() == {}

    def test_intent_none_is_an_explicit_clear(self):
        assert EventUpdateIntent(completed_at=None).to_changes() == {"completed_at": None}

    def test_request_to_intent_partial_patch_semantics(self):
        assert EventUpdateRequest().to_intent().completed_at is UNSET
        assert EventUpdateRequest(completed_at=STAMP).to_intent().completed_at == STAMP
        # Explicitly-sent null = reopen clears the stamp.
        assert EventUpdateRequest(completed_at=None).to_intent().completed_at is None


class TestChoiceCompletedAt:
    """Choice ``completed_at`` exists on all four layers and round-trips."""

    def test_model_accepts_completed_at_distinct_from_decided_at(self):
        choice = Choice(
            uid="choice_c1",
            user_uid="user_t",
            title="Pick a stack",
            decided_at=datetime(2026, 8, 1, tzinfo=UTC),
            completed_at=STAMP,
        )
        assert choice.completed_at == STAMP
        assert choice.decided_at != choice.completed_at

    def test_dto_roundtrips_writer_storage_shape(self):
        dto = ChoiceDTO.from_dict(
            {
                "uid": "choice_c2",
                "title": "Pick a stack",
                "entity_type": "choice",
                "user_uid": "user_t",
                "completed_at": STAMP.isoformat(),
            }
        )
        assert dto.completed_at == STAMP
        assert (
            ChoiceDTO.create_choice("user_t", "Pick a stack", completed_at=STAMP).to_dict()[
                "completed_at"
            ]
            == STAMP.isoformat()
        )

    def test_intent_carries_completed_at_untouched(self):
        changes = ChoiceUpdateIntent(completed_at=STAMP).to_changes()
        assert changes == {"completed_at": STAMP}
        assert ChoiceUpdateIntent().to_changes() == {}

    def test_request_to_intent_partial_patch_semantics(self):
        assert ChoiceUpdateRequest().to_intent().completed_at is UNSET
        assert ChoiceUpdateRequest(completed_at=STAMP).to_intent().completed_at == STAMP
        assert ChoiceUpdateRequest(completed_at=None).to_intent().completed_at is None
