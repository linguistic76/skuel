"""A choice's options and its decision are written from the choice as it stands under its lock.

``add_option``, ``remove_option`` and ``make_decision`` each plan their write from the
locked choice (``ChoicesBackend.rewrite_choice_under_lock``): every refusal is read from
that choice and writes nothing, and an option write carries the options alone, never
the status or the decision a whole-entity write would put back.

The fake (``tests.helpers.status_guarded_backend``) plans from the held choice and
records each write; the lock itself is held to a real graph by
``tests/integration/test_choice_decision_door.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from core.events import BaseEvent, ChoiceMade, ChoiceUpdated
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceOptionRequest
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus
from core.services.choices.choices_core_service import ChoicesCoreService
from core.utils.result_simplified import ErrorCategory
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

USER = "user_choice_options"
UID = "choice_1"


class _RecordingBus:
    """Records what the service publishes; ``publish_async`` is the whole contract."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _options(count: int) -> tuple[ChoiceOption, ...]:
    return tuple(ChoiceOption(uid=f"option_{i}", title=f"Option {i}") for i in range(count))


def _choice(**fields: Any) -> Choice:  # boundary: Choice field values of several types
    return Choice(uid=UID, user_uid=USER, title="Where to practise", **fields)


def _service(
    current: Choice,
) -> tuple[ChoicesCoreService, StatusGuardedWriteRecorder[Choice], _RecordingBus]:
    backend, recorder = guarded_backend(current, current)
    bus = _RecordingBus()
    return ChoicesCoreService(backend=backend, event_bus=bus), recorder, bus


# ---------------------------------------------------------------------------
# make_decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMakeDecision:
    async def test_it_writes_the_decision_and_publishes_choice_made(self) -> None:
        service, recorder, bus = _service(_choice(options=_options(2)))

        result = await service.make_decision(UID, "option_1", "closest to hand", confidence=0.7)

        assert result.is_ok
        updates = recorder.last_updates
        assert updates["selected_option_uid"] == "option_1"
        assert updates["decision_rationale"] == "closest to hand"
        assert updates["status"] == EntityStatus.ACTIVE.value
        assert isinstance(datetime.fromisoformat(updates["decided_at"]), datetime)
        made = bus.of(ChoiceMade)
        assert len(made) == 1
        assert made[0].selected_option == "option_1"
        assert made[0].confidence == 0.7
        assert made[0].metadata == {"rationale": "closest to hand"}

    @pytest.mark.parametrize(
        "current",
        [
            _choice(
                options=_options(2), status=EntityStatus.ACTIVE, decided_at=datetime(2026, 11, 1)
            ),
            _choice(options=_options(2), status=EntityStatus.COMPLETED),
            _choice(
                options=_options(2), status=EntityStatus.ARCHIVED, decided_at=datetime(2026, 11, 1)
            ),
        ],
        ids=["active-decided", "completed", "archived-decided"],
    )
    async def test_a_decided_choice_is_not_decided_again(self, current: Choice) -> None:
        service, recorder, bus = _service(current)

        result = await service.make_decision(UID, "option_0")

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.VALIDATION
        assert "already decided" in result.expect_error().message
        assert recorder.calls == []
        assert bus.of(ChoiceMade) == []

    async def test_an_active_choice_no_decision_recorded_can_be_decided(self) -> None:
        """Decided is the record (``decided_at``), not the status: an ACTIVE choice with
        no decision (set so by the status door, or a vault file) is still undecided."""
        service, recorder, _bus = _service(_choice(options=_options(2), status=EntityStatus.ACTIVE))

        result = await service.make_decision(UID, "option_0")

        assert result.is_ok
        assert recorder.last_updates["selected_option_uid"] == "option_0"

    async def test_an_option_the_choice_does_not_hold_is_refused(self) -> None:
        service, recorder, bus = _service(_choice(options=_options(2)))

        result = await service.make_decision(UID, "option_of_another_choice")

        assert result.is_error
        error = result.expect_error()
        assert error.category is ErrorCategory.VALIDATION
        assert error.details["field"] == "selected_option_uid"
        assert recorder.calls == []
        assert bus.of(ChoiceMade) == []

    @pytest.mark.parametrize("count", [0, 1])
    async def test_fewer_than_two_options_is_no_decision(self, count: int) -> None:
        service, recorder, _bus = _service(_choice(options=_options(count)))

        result = await service.make_decision(UID, "option_0")

        assert result.is_error
        assert result.expect_error().details["field"] == "options"
        assert recorder.calls == []


# ---------------------------------------------------------------------------
# add_option
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAddOption:
    async def test_it_appends_and_writes_the_options_alone(self) -> None:
        service, recorder, bus = _service(_choice(options=_options(1)))

        result = await service.add_option(UID, ChoiceOptionRequest(title="Before bed"))

        assert result.is_ok
        assert set(recorder.last_updates) == {"options"}, (
            "an option write must not carry status or decision fields"
        )
        written = recorder.last_updates["options"]
        assert [opt.title for opt in written] == ["Option 0", "Before bed"]
        assert written[1].description == ""
        assert recorder.last_guard.refuse_if_prior_in == frozenset()
        assert len(bus.of(ChoiceUpdated)) == 1

    @pytest.mark.parametrize(
        "current",
        [
            _choice(options=_options(2), status=EntityStatus.ACTIVE),
            _choice(options=_options(2), status=EntityStatus.COMPLETED),
            _choice(options=_options(2), decided_at=datetime(2026, 11, 1)),
        ],
        ids=["active", "completed", "decision-recorded"],
    )
    async def test_a_decided_choice_keeps_its_options(self, current: Choice) -> None:
        service, recorder, bus = _service(current)

        result = await service.add_option(UID, ChoiceOptionRequest(title="Late idea"))

        assert result.is_error
        assert "Decisions are historical records" in result.expect_error().message
        assert recorder.calls == []
        assert bus.of(ChoiceUpdated) == []

    async def test_a_binary_choice_holds_two(self) -> None:
        service, recorder, _bus = _service(
            _choice(options=_options(2), choice_type=ChoiceType.BINARY)
        )

        result = await service.add_option(UID, ChoiceOptionRequest(title="Third way"))

        assert result.is_error
        assert result.expect_error().details["field"] == "choice_type"
        assert recorder.calls == []


# ---------------------------------------------------------------------------
# remove_option
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRemoveOption:
    async def test_it_removes_and_writes_the_options_alone(self) -> None:
        service, recorder, _bus = _service(_choice(options=_options(3)))

        result = await service.remove_option(UID, "option_1")

        assert result.is_ok
        assert set(recorder.last_updates) == {"options"}
        assert [opt.uid for opt in recorder.last_updates["options"]] == ["option_0", "option_2"]

    async def test_a_decided_choice_keeps_its_options(self) -> None:
        service, recorder, _bus = _service(
            _choice(options=_options(3), status=EntityStatus.ACTIVE, selected_option_uid="option_0")
        )

        result = await service.remove_option(UID, "option_2")

        assert result.is_error
        assert "Decisions are historical records" in result.expect_error().message
        assert recorder.calls == []

    async def test_an_option_the_choice_does_not_hold_is_not_found(self) -> None:
        service, recorder, _bus = _service(_choice(options=_options(3)))

        result = await service.remove_option(UID, "option_9")

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.NOT_FOUND
        assert recorder.calls == []

    async def test_two_options_stay_two(self) -> None:
        service, recorder, _bus = _service(_choice(options=_options(2)))

        result = await service.remove_option(UID, "option_0")

        assert result.is_error
        assert result.expect_error().details["field"] == "options"
        assert recorder.calls == []


# ---------------------------------------------------------------------------
# Choice.options_open — the page's predicate and the service's are one
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "is_open"),
    [
        (_choice(status=EntityStatus.DRAFT), True),
        (_choice(status=EntityStatus.ARCHIVED), True),
        (_choice(status=EntityStatus.ACTIVE), False),
        (_choice(status=EntityStatus.COMPLETED), False),
        (_choice(status=EntityStatus.DRAFT, decided_at=datetime(2026, 11, 1)), False),
    ],
)
def test_options_open(current: Choice, is_open: bool) -> None:
    assert current.options_open() is is_open
