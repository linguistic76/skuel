"""The prerequisite gate, and the doors that start a step through it.

A learner starts a step only once every published prerequisite in its chain is
mastered (``PsPrerequisiteGate``). ``PsMasteryService.mark_in_progress`` is the one
writer that starts a step, and answers its refusals in one order: a uid that is not a
published step, then the prerequisites, then a step already completed, then the
enrollment cap. Mark as read and Review again start nothing, so they act only on a step
the learner holds in progress. Engaging a step asks the same gate first.

Each fake records what it was asked, so a refusal is shown to stop before any write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from core.events.curriculum_events import PathStepEnrolled
from core.models.type_hints import UserUID
from core.ports.query_types import PsPrerequisiteStatusRow, StepHoldRow, StepStartRow
from core.services.ps.ps_mastery_service import (
    ENROLLMENT_CAP,
    ENROLLMENT_CAP_RULE,
    PsMasteryService,
)
from core.services.ps.ps_prerequisite_gate import (
    PREREQUISITE_GATE_DEPTH,
    PREREQUISITES_UNMET_RULE,
    PsPrerequisiteGate,
)
from core.services.ps_engagement import PsEngagementService
from core.utils.result_simplified import ErrorCategory, Errors, Result

USER = UserUID("user_gate")
STEP = "ps.gate.step"


def _row(uid: str, *, completed: bool, distance: int = 1) -> PsPrerequisiteStatusRow:
    return {
        "uid": uid,
        "title": uid.rsplit(".", 1)[-1].title(),
        "domain": "",
        "entity_type": "path_step",
        "distance": distance,
        "completed": completed,
    }


def _the_step() -> set[str]:
    return {STEP}


@dataclass
class _IntelligenceBackend:
    """The two reads the gate makes."""

    published: set[str] = field(default_factory=_the_step)
    chain: list[PsPrerequisiteStatusRow] = field(default_factory=list)
    chain_result: Result[list[PsPrerequisiteStatusRow]] | None = None
    chain_reads: list[tuple[str, str | None, int]] = field(default_factory=list)

    async def is_published_step(self, ps_uid: str) -> Result[bool]:
        return Result.ok(ps_uid in self.published)

    async def fetch_prerequisite_statuses(
        self, ps_uid: str, user_uid: str | None, depth: int
    ) -> Result[list[PsPrerequisiteStatusRow]]:
        self.chain_reads.append((ps_uid, user_uid, depth))
        return self.chain_result or Result.ok(self.chain)


@dataclass
class _StepBackend:
    """The learner-state members ``PsMasteryService`` reaches on ``PsOperations``."""

    in_progress: set[str] = field(default_factory=set)
    mastered: set[str] = field(default_factory=set)
    held_elsewhere: int = 0
    writes: list[str] = field(default_factory=list)
    caps: list[int] = field(default_factory=list)

    async def get_learning_state_raw(
        self, user_uid: str, ku_uid: str
    ) -> Result[list[dict[str, bool]]]:
        return Result.ok(
            [
                {
                    "has_in_progress": ku_uid in self.in_progress,
                    "has_mastered": ku_uid in self.mastered,
                }
            ]
        )

    async def mark_in_progress(
        self, user_uid: str, ku_uid: str, now: str, cap: int
    ) -> Result[list[StepStartRow]]:
        """The statement's verdict, decided as the backend decides it under the lock."""
        self.caps.append(cap)
        mastered = ku_uid in self.mastered
        held = ku_uid in self.in_progress
        capped = not mastered and not held and self.held_elsewhere + len(self.in_progress) >= cap
        if not (mastered or capped):
            self.writes.append("IN_PROGRESS")
        started = not (mastered or held or capped)
        return Result.ok(
            [{"mastered": mastered, "held": held, "started": started, "capped": capped}]
        )

    async def mark_as_read(self, user_uid: str, ku_uid: str) -> Result[list[StepHoldRow]]:
        return self._held_write("MARKED_AS_READ", ku_uid)

    async def mark_as_learning(self, user_uid: str, ku_uid: str) -> Result[list[StepHoldRow]]:
        return self._held_write("REVIEW_AGAIN", ku_uid)

    def _held_write(self, name: str, ku_uid: str) -> Result[list[StepHoldRow]]:
        if ku_uid != STEP:
            return Result.ok([])
        held = ku_uid in self.in_progress
        if held:
            self.writes.append(name)
        return Result.ok([{"held": held, "mastered": ku_uid in self.mastered}])


@dataclass
class _Bus:
    published: list[object] = field(default_factory=list)

    async def publish_async(self, event: object) -> None:
        self.published.append(event)


def _service(
    intelligence: _IntelligenceBackend | None = None, steps: _StepBackend | None = None
) -> tuple[PsMasteryService, _IntelligenceBackend, _StepBackend, _Bus]:
    intelligence = intelligence or _IntelligenceBackend()
    steps = steps or _StepBackend()
    bus = _Bus()
    service = PsMasteryService(
        backend=steps,  # type: ignore[arg-type]
        prerequisite_gate=PsPrerequisiteGate(intelligence),  # type: ignore[arg-type]
        event_bus=bus,
    )
    return service, intelligence, steps, bus


def _rule[T](result: Result[T]) -> object:
    return result.expect_error().details.get("rule")


# --------------------------------------------------------------------------- the gate


async def test_a_uid_that_is_not_a_published_step_is_missing_before_its_prerequisites() -> None:
    """A draft does not tell a learner what it requires."""
    backend = _IntelligenceBackend(published=set(), chain=[_row("ps.gate.first", completed=False)])

    result = await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    assert backend.chain_reads == []


async def test_an_unmet_prerequisite_anywhere_in_the_chain_refuses_naming_it() -> None:
    backend = _IntelligenceBackend(
        chain=[
            _row("ps.gate.near", completed=True),
            _row("ps.gate.far", completed=False, distance=2),
        ]
    )

    result = await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    error = result.expect_error()
    assert error.category == ErrorCategory.BUSINESS
    assert error.details["rule"] == PREREQUISITES_UNMET_RULE
    assert error.details["unmet_uids"] == ["ps.gate.far"]
    assert error.message == "Master Far before starting this step."


async def test_the_chain_is_read_for_the_learner_at_the_gate_depth() -> None:
    """The depth the PathStep page and the chain door read by default."""
    backend = _IntelligenceBackend()

    await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    assert backend.chain_reads == [(STEP, USER, PREREQUISITE_GATE_DEPTH)]


async def test_a_chain_wholly_mastered_admits() -> None:
    backend = _IntelligenceBackend(
        chain=[_row("ps.gate.near", completed=True), _row("ps.gate.far", completed=True)]
    )

    result = await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    assert result.is_ok


async def test_a_failed_chain_read_refuses_rather_than_admits() -> None:
    backend = _IntelligenceBackend(
        chain_result=Result.fail(Errors.database(operation="chain", message="down"))
    )

    result = await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    assert result.expect_error().category == ErrorCategory.DATABASE


async def test_a_long_list_names_three_and_counts_the_rest() -> None:
    backend = _IntelligenceBackend(chain=[_row(f"ps.gate.p{i}", completed=False) for i in range(5)])

    result = await PsPrerequisiteGate(backend).admit(USER, STEP)  # type: ignore[arg-type]

    assert (
        result.expect_error().message == "Master P0, P1, P2 and 2 more before starting this step."
    )


# ------------------------------------------------------------------- starting a step


async def test_an_unmet_prerequisite_refuses_the_start_before_any_write() -> None:
    service, _, steps, bus = _service(
        _IntelligenceBackend(chain=[_row("ps.gate.first", completed=False)])
    )

    result = await service.mark_in_progress(USER, STEP)

    assert _rule(result) == PREREQUISITES_UNMET_RULE
    assert steps.writes == []
    assert bus.published == []


async def test_the_prerequisites_answer_before_the_enrollment_cap() -> None:
    service, _, steps, _ = _service(
        _IntelligenceBackend(chain=[_row("ps.gate.first", completed=False)]),
        _StepBackend(held_elsewhere=ENROLLMENT_CAP),
    )

    result = await service.mark_in_progress(USER, STEP)

    assert _rule(result) == PREREQUISITES_UNMET_RULE
    assert steps.writes == []


async def test_a_full_enrollment_refuses_a_new_step_naming_mastery() -> None:
    """Marking a step as read keeps it in progress, so the refusal never offers it."""
    service, _, steps, bus = _service(steps=_StepBackend(held_elsewhere=ENROLLMENT_CAP))

    result = await service.mark_in_progress(USER, STEP)

    assert _rule(result) == ENROLLMENT_CAP_RULE
    message = result.expect_error().message
    assert "master one to start another" in message
    assert "read" not in message
    assert steps.writes == []
    assert bus.published == []


async def test_a_step_already_held_is_no_new_slot() -> None:
    service, _, steps, _ = _service(
        steps=_StepBackend(in_progress={STEP}, held_elsewhere=ENROLLMENT_CAP - 1)
    )

    result = await service.mark_in_progress(USER, STEP)

    assert result.is_ok
    assert steps.writes == ["IN_PROGRESS"]


async def test_a_mastered_step_is_not_started_again() -> None:
    service, _, steps, bus = _service(steps=_StepBackend(mastered={STEP}))

    result = await service.mark_in_progress(USER, STEP)

    assert _rule(result) == "ps_already_mastered"
    assert steps.writes == []
    assert bus.published == []


async def test_the_start_asks_the_write_for_the_cap() -> None:
    """The cap is decided by the statement: the service hands it ``ENROLLMENT_CAP`` and
    reads no learner state of its own before it (the fake has no tally to read)."""
    service, _, steps, _ = _service(steps=_StepBackend(held_elsewhere=ENROLLMENT_CAP - 1))

    result = await service.mark_in_progress(USER, STEP)

    assert result.is_ok
    assert steps.caps == [ENROLLMENT_CAP]


async def test_an_admitted_start_writes_and_announces() -> None:
    service, _, steps, bus = _service(
        _IntelligenceBackend(chain=[_row("ps.gate.first", completed=True)])
    )

    result = await service.mark_in_progress(USER, STEP)

    assert result.is_ok
    assert steps.writes == ["IN_PROGRESS"]
    assert [type(event) for event in bus.published] == [PathStepEnrolled]


async def test_a_draft_is_missing_at_the_start() -> None:
    service, _, steps, _ = _service(_IntelligenceBackend(published=set()))

    result = await service.mark_in_progress(USER, STEP)

    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    assert steps.writes == []


# --------------------------------------------------- doors that start nothing


@pytest.mark.parametrize("door", ["mark_as_read", "mark_as_learning"])
async def test_a_step_never_started_is_left_alone(door: str) -> None:
    """A direct POST cannot start a step past the gate and the cap by marking it read."""
    service, _, steps, _ = _service()

    result = await getattr(service, door)(USER, STEP)

    assert _rule(result) == "ps_not_started"
    assert steps.writes == []


@pytest.mark.parametrize("door", ["mark_as_read", "mark_as_learning"])
async def test_a_mastered_step_is_left_alone(door: str) -> None:
    """Mastery retired the hold; Review again would put a cap slot back beside it."""
    service, _, steps, _ = _service(steps=_StepBackend(mastered={STEP}))

    result = await getattr(service, door)(USER, STEP)

    assert _rule(result) == "ps_already_mastered"
    assert steps.writes == []


@pytest.mark.parametrize(
    ("door", "write"), [("mark_as_read", "MARKED_AS_READ"), ("mark_as_learning", "REVIEW_AGAIN")]
)
async def test_a_step_held_in_progress_takes_the_write(door: str, write: str) -> None:
    service, intelligence, steps, bus = _service(steps=_StepBackend(in_progress={STEP}))

    result = await getattr(service, door)(USER, STEP)

    assert result.is_ok
    assert steps.writes == [write]
    # Starting nothing, it asks no gate and announces nothing.
    assert intelligence.chain_reads == []
    assert bus.published == []


@pytest.mark.parametrize("door", ["mark_as_read", "mark_as_learning"])
async def test_any_other_uid_is_missing(door: str) -> None:
    service, _, _, _ = _service()

    result = await getattr(service, door)(USER, "ps.gate.elsewhere")

    assert result.expect_error().category == ErrorCategory.NOT_FOUND


# --------------------------------------------------------------- require_held


@pytest.mark.parametrize(
    ("published", "steps", "expected"),
    [
        (set(), _StepBackend(in_progress={STEP}), "not_found"),
        ({STEP}, _StepBackend(), "ps_not_started"),
        ({STEP}, _StepBackend(mastered={STEP}), "ps_already_mastered"),
        ({STEP}, _StepBackend(in_progress={STEP}), "held"),
    ],
    ids=["draft", "never-started", "mastered", "held"],
)
async def test_require_held_admits_only_a_published_step_in_progress(
    published: set[str], steps: _StepBackend, expected: str
) -> None:
    service, _, _, _ = _service(_IntelligenceBackend(published=published), steps)

    result = await service.require_held(USER, STEP)

    if expected == "held":
        assert result.is_ok
    elif expected == "not_found":
        assert result.expect_error().category == ErrorCategory.NOT_FOUND
    else:
        assert _rule(result) == expected


# ------------------------------------------------------------------- engaging


async def test_engaging_asks_the_gate_before_anything_else() -> None:
    """A refused engagement opens no edge and spawns nothing."""
    engagement_backend = MagicMock()
    template_and_instance_backends = {
        name: MagicMock()
        for name in (
            "task_template_backend",
            "goal_template_backend",
            "habit_template_backend",
            "event_template_backend",
            "choice_template_backend",
            "principle_template_backend",
            "tasks_backend",
            "goals_backend",
            "habits_backend",
            "events_backend",
            "choices_backend",
            "principles_backend",
        )
    }
    service = PsEngagementService(
        backend=engagement_backend,
        event_bus=MagicMock(),
        prerequisite_gate=PsPrerequisiteGate(  # type: ignore[arg-type]
            _IntelligenceBackend(chain=[_row("ps.gate.first", completed=False)])
        ),
        **template_and_instance_backends,
    )

    result = await service.engage_pathstep(USER, STEP)

    assert _rule(result) == PREREQUISITES_UNMET_RULE
    assert engagement_backend.method_calls == []
    for backend in template_and_instance_backends.values():
        assert backend.method_calls == []
