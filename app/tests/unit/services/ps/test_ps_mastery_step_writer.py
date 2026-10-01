"""``PsMasteryService.handle_knowledge_mastered`` — the step's MASTERED edge is written
BEFORE ``PathStepCompleted`` is published, and a write that does not land withholds the
event: the event announces a persisted fact, never an intention."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.events.curriculum_events import PathStepCompleted
from core.events.learning_events import KnowledgeMastered
from core.models.type_hints import UserUID
from core.services.ps.ps_mastery_service import (
    STEP_MASTERY_METHOD,
    STEP_MASTERY_SCORE,
    PsMasteryService,
)
from core.utils.result_simplified import Errors, Result

USER = UserUID("user_1")


@dataclass
class _Trace:
    """One ordered log shared by the backend and the bus, so ordering is provable."""

    steps: list[str] = field(default_factory=list)


@dataclass
class _Backend:
    """The two members the handler reaches on ``PsOperations``."""

    trace: _Trace
    detected: list[str]
    write_result: Result[list[dict[str, object]]] | None = None
    writes: list[tuple[str, str, float, str]] = field(default_factory=list)
    gaps: list[dict[str, str]] = field(default_factory=list)
    failing: set[str] = field(default_factory=set)

    async def find_step_mastery_gaps(self) -> Result[list[dict[str, str]]]:
        self.trace.steps.append("gaps")
        return Result.ok(list(self.gaps))

    async def detect_path_step_completion(
        self, ku_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, object]]]:
        self.trace.steps.append(f"detect:{ku_uid}")
        return Result.ok(
            [{"ps_uid": uid, "ps_title": uid, "all_ku_uids": []} for uid in self.detected]
        )

    async def mark_mastered(
        self, user_uid: UserUID, entity_uid: str, now: str, mastery_score: float, method: str
    ) -> Result[list[dict[str, object]]]:
        self.trace.steps.append(f"write:{entity_uid}")
        self.writes.append((user_uid, entity_uid, mastery_score, method))
        if entity_uid in self.failing:
            return Result.fail(Errors.database("write", f"{entity_uid} down"))
        if self.write_result is not None:
            return self.write_result
        return Result.ok([{"mastery_score": mastery_score, "was_mastered": False}])


@dataclass
class _Bus:
    trace: _Trace
    published: list[object] = field(default_factory=list)

    async def publish_async(self, event: object) -> None:
        self.trace.steps.append(f"publish:{type(event).__name__}")
        self.published.append(event)


def _event() -> KnowledgeMastered:
    return KnowledgeMastered(ku_uid="ku.a", user_uid=USER, mastery_score=0.9)


@pytest.mark.asyncio
async def test_the_edge_is_written_before_the_event_is_published() -> None:
    trace = _Trace()
    backend = _Backend(trace, detected=["ps.one", "ps.two"])
    bus = _Bus(trace)

    await PsMasteryService(backend=backend, event_bus=bus).handle_knowledge_mastered(_event())  # type: ignore[arg-type]

    assert trace.steps == [
        "detect:ku.a",
        "write:ps.one",
        "publish:PathStepCompleted",
        "write:ps.two",
        "publish:PathStepCompleted",
    ]
    assert backend.writes == [
        (USER, "ps.one", STEP_MASTERY_SCORE, STEP_MASTERY_METHOD),
        (USER, "ps.two", STEP_MASTERY_SCORE, STEP_MASTERY_METHOD),
    ]
    assert [e.ps_uid for e in bus.published if isinstance(e, PathStepCompleted)] == [
        "ps.one",
        "ps.two",
    ]


@pytest.mark.asyncio
async def test_a_failed_write_withholds_the_event() -> None:
    trace = _Trace()
    backend = _Backend(
        trace, detected=["ps.one"], write_result=Result.fail(Errors.database("write", "down"))
    )
    bus = _Bus(trace)

    await PsMasteryService(backend=backend, event_bus=bus).handle_knowledge_mastered(_event())  # type: ignore[arg-type]

    assert trace.steps == ["detect:ku.a", "write:ps.one"]
    assert bus.published == []


@pytest.mark.asyncio
async def test_a_write_that_matched_nothing_withholds_the_event() -> None:
    """``mark_mastered`` returns no row when the user or the step is missing."""
    trace = _Trace()
    backend = _Backend(trace, detected=["ps.gone"], write_result=Result.ok([]))
    bus = _Bus(trace)

    await PsMasteryService(backend=backend, event_bus=bus).handle_knowledge_mastered(_event())  # type: ignore[arg-type]

    assert trace.steps == ["detect:ku.a", "write:ps.gone"]
    assert bus.published == []


@pytest.mark.asyncio
async def test_no_completed_step_writes_nothing() -> None:
    trace = _Trace()
    backend = _Backend(trace, detected=[])
    bus = _Bus(trace)

    await PsMasteryService(backend=backend, event_bus=bus).handle_knowledge_mastered(_event())  # type: ignore[arg-type]

    assert trace.steps == ["detect:ku.a"]
    assert backend.writes == []
    assert bus.published == []


@pytest.mark.asyncio
async def test_a_step_already_mastered_is_not_announced_again() -> None:
    """A replayed KnowledgeMastered re-detects the step; its edge exists, so no event."""
    trace = _Trace()
    backend = _Backend(
        trace,
        detected=["ps.one"],
        write_result=Result.ok([{"mastery_score": 1.0, "was_mastered": True}]),
    )
    bus = _Bus(trace)

    await PsMasteryService(backend=backend, event_bus=bus).handle_knowledge_mastered(_event())  # type: ignore[arg-type]

    assert trace.steps == ["detect:ku.a", "write:ps.one"]
    assert bus.published == []


@pytest.mark.asyncio
async def test_reconcile_returns_the_gaps_it_closed() -> None:
    trace = _Trace()
    gaps = [{"user_uid": "user_1", "ps_uid": "ps.one"}, {"user_uid": "user_2", "ps_uid": "ps.two"}]
    backend = _Backend(trace, detected=[], gaps=gaps)
    bus = _Bus(trace)

    result = await PsMasteryService(backend=backend, event_bus=bus).reconcile_step_mastery()  # type: ignore[arg-type]

    assert result.is_ok and result.value == gaps
    assert [e.ps_uid for e in bus.published if isinstance(e, PathStepCompleted)] == [
        "ps.one",
        "ps.two",
    ]


@pytest.mark.asyncio
async def test_reconcile_dry_run_reports_without_writing() -> None:
    trace = _Trace()
    gaps = [{"user_uid": "user_1", "ps_uid": "ps.one"}]
    backend = _Backend(trace, detected=[], gaps=gaps)
    bus = _Bus(trace)

    result = await PsMasteryService(backend=backend, event_bus=bus).reconcile_step_mastery(  # type: ignore[arg-type]
        dry_run=True
    )

    assert result.is_ok and result.value == gaps
    assert trace.steps == ["gaps"]
    assert bus.published == []


@pytest.mark.asyncio
async def test_reconcile_fails_naming_the_gaps_it_could_not_close() -> None:
    """Every gap is attempted; one failed write makes the run a failure, not a clean report."""
    trace = _Trace()
    gaps = [{"user_uid": "user_1", "ps_uid": "ps.one"}, {"user_uid": "user_2", "ps_uid": "ps.two"}]
    backend = _Backend(trace, detected=[], gaps=gaps, failing={"ps.one"})
    bus = _Bus(trace)

    result = await PsMasteryService(backend=backend, event_bus=bus).reconcile_step_mastery()  # type: ignore[arg-type]

    assert result.is_error
    message = str(result.error)
    assert "1 of 2" in message and "user_1→ps.one" in message and "1 closed" in message
    assert trace.steps == ["gaps", "write:ps.one", "write:ps.two", "publish:PathStepCompleted"]
