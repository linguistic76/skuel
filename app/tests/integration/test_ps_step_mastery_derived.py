"""A PathStep's MASTERED edge is derived — written the moment its last Ku is mastered.

Drives the live door end to end against real Neo4j: ``PsMasteryService.mark_mastered``
(the report-approval writer) publishes ``KnowledgeMastered``; the same service's
``handle_knowledge_mastered`` is subscribed, detects the step whose Kus are now all
mastered, writes ``(User)-[:MASTERED]->(PathStep)`` through the one ``mark_mastered``
backend writer, and only then publishes ``PathStepCompleted``.

What the edge must look like is the Ku edge's shape — ``mastered_at`` as a zoned
datetime, ``mastery_score`` / ``confidence`` at 1.0, ``method = 'derived'`` — so every
numeric reader sees one vocabulary. Mastery is terminal, so the step's IN_PROGRESS
(enrollment) edge is gone afterwards and the enrollment cap no longer counts it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.events.curriculum_events import PathStepCompleted
from core.events.learning_events import KnowledgeMastered
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.models.type_hints import UserUID
from core.services.ps.ps_mastery_service import (
    STEP_MASTERY_METHOD,
    STEP_MASTERY_SCORE,
    LearningState,
    PsMasteryService,
)

USER = UserUID("user_step_mastery_derived")
STEP = "ps.probe.two-kus"
STEP_EMPTY = "ps.probe.zero-kus"
KU_A = "ku.probe.a"
KU_B = "ku.probe.b"


@pytest_asyncio.fixture
async def backend(neo4j_driver, clean_neo4j) -> PsBackend:
    """One step teaching two Kus (the learner is enrolled in it) — and pointing a
    composition edge at a second step that teaches none. Only Kus count toward
    the tally: the step-to-step edge, which the edge writer permits, must not
    hold the parent back (a step's mastery is never a KnowledgeMastered)."""
    async with neo4j_driver.session() as session:
        await session.run("MERGE (u:User {uid: $u})", u=USER)
        await session.run(
            """
            MATCH (u:User {uid: $u})
            CREATE (ps:Entity:PathStep {uid: $step, entity_type: 'path_step',
                                        title: 'Two Kus', status: 'active'})
            CREATE (empty:Entity:PathStep {uid: $empty, entity_type: 'path_step',
                                           title: 'No Kus', status: 'active'})
            CREATE (a:Entity:Ku {uid: $a, entity_type: 'ku', title: 'A'})
            CREATE (b:Entity:Ku {uid: $b, entity_type: 'ku', title: 'B'})
            CREATE (ps)-[:USES_KU]->(a)
            CREATE (ps)-[:USES_KU]->(b)
            CREATE (ps)-[:USES_KU]->(empty)
            CREATE (u)-[:IN_PROGRESS {started_at: datetime()}]->(ps)
            """,
            u=USER,
            step=STEP,
            empty=STEP_EMPTY,
            a=KU_A,
            b=KU_B,
        )
    return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)


@pytest.fixture
def bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest_asyncio.fixture
async def mastery(backend: PsBackend, bus: InMemoryEventBus) -> PsMasteryService:
    """The service wired as ``services_bootstrap/_event_wiring.py`` wires it."""
    service = PsMasteryService(backend=backend, event_bus=bus)
    bus.subscribe(KnowledgeMastered, service.handle_knowledge_mastered)
    return service


async def _step_edges(neo4j_driver, step_uid: str) -> list[dict]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (:User {uid: $u})-[m:MASTERED]->(ps:Entity {uid: $step})
            RETURN properties(m) AS props, valueType(m.mastered_at) AS stamp_type
            """,
            u=USER,
            step=step_uid,
        )
        return [dict(r) async for r in result]


async def _enrolled(neo4j_driver, step_uid: str) -> bool:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "RETURN EXISTS { (:User {uid: $u})-[:IN_PROGRESS]->(:Entity {uid: $step}) } AS on",
            u=USER,
            step=step_uid,
        )
        return bool((await result.single())["on"])


def _completions(bus: InMemoryEventBus) -> list[PathStepCompleted]:
    return [e for e in bus.get_event_history() if isinstance(e, PathStepCompleted)]


@pytest.mark.asyncio
async def test_the_step_is_mastered_only_when_its_last_ku_is(
    neo4j_driver, backend, bus, mastery
) -> None:
    assert (await mastery.mark_mastered(USER, KU_A, 0.9)).is_ok

    assert await _step_edges(neo4j_driver, STEP) == [], (
        "one of two Kus mastered — the step must not be"
    )
    assert _completions(bus) == []
    assert await _enrolled(neo4j_driver, STEP), "an unfinished step keeps its enrollment"

    assert (await mastery.mark_mastered(USER, KU_B, 0.9)).is_ok

    edges = await _step_edges(neo4j_driver, STEP)
    assert len(edges) == 1
    props = edges[0]["props"]
    assert props["mastery_score"] == STEP_MASTERY_SCORE
    assert props["confidence"] == STEP_MASTERY_SCORE
    assert props["method"] == STEP_MASTERY_METHOD
    assert edges[0]["stamp_type"].startswith("ZONED DATETIME"), edges[0]["stamp_type"]
    assert set(props) == {"mastered_at", "mastery_score", "confidence", "method"}, (
        "the step edge carries the Ku writer's shape and nothing else"
    )

    completed = _completions(bus)
    assert [e.ps_uid for e in completed] == [STEP]
    assert completed[0].user_uid == USER


@pytest.mark.asyncio
async def test_mastery_is_terminal_for_the_enrollment(neo4j_driver, backend, bus, mastery) -> None:
    assert (await mastery.count_in_progress_steps(USER)).value == 1

    assert (await mastery.mark_mastered(USER, KU_A, 0.9)).is_ok
    assert (await mastery.mark_mastered(USER, KU_B, 0.9)).is_ok

    assert not await _enrolled(neo4j_driver, STEP)
    assert (await mastery.count_in_progress_steps(USER)).value == 0, (
        "a mastered step must not hold an enrollment-cap slot"
    )
    # The step was never VIEWED — the detail page's state read must still see
    # the mastery (the user is bound once in get_learning_state_raw).
    state = await mastery.get_learning_state(USER, STEP)
    assert state.is_ok and state.value.state is LearningState.MASTERED
    assert state.value.mastered_at is not None
    batch = await mastery.get_learning_states_batch(USER, [STEP, KU_A])
    assert batch.is_ok and set(batch.value.values()) == {LearningState.MASTERED}


def _ku_masteries(bus: InMemoryEventBus) -> list[KnowledgeMastered]:
    return [e for e in bus.get_event_history() if isinstance(e, KnowledgeMastered)]


@pytest.mark.asyncio
async def test_a_repeat_mastery_is_not_a_transition(neo4j_driver, backend, bus, mastery) -> None:
    assert (await mastery.mark_mastered(USER, KU_A, 0.9)).is_ok
    assert (await mastery.mark_mastered(USER, KU_B, 0.9)).is_ok
    first = (await _step_edges(neo4j_driver, STEP))[0]["props"]["mastered_at"]
    assert len(_ku_masteries(bus)) == 2

    # Re-approval raises the stored score; the edge existed, so nothing is announced.
    assert (await mastery.mark_mastered(USER, KU_B, 0.95)).is_ok
    assert len(_ku_masteries(bus)) == 2, "a repeat write on a mastered Ku is not an event"

    # A replayed KnowledgeMastered re-detects the step; the MERGE leaves one edge
    # and the step's own transition is not announced twice.
    await bus.publish_async(KnowledgeMastered(ku_uid=KU_B, user_uid=USER, mastery_score=0.95))

    edges = await _step_edges(neo4j_driver, STEP)
    assert len(edges) == 1, "MERGE — never a second MASTERED edge on the step"
    assert edges[0]["props"]["mastered_at"] == first, "the first mastery instant survives"
    assert len(_completions(bus)) == 1, "PathStepCompleted announces the transition only"


@pytest.mark.asyncio
async def test_a_step_teaching_no_ku_is_never_derived(neo4j_driver, backend, bus, mastery) -> None:
    assert (await mastery.mark_mastered(USER, KU_A, 0.9)).is_ok
    assert (await mastery.mark_mastered(USER, KU_B, 0.9)).is_ok

    assert await _step_edges(neo4j_driver, STEP_EMPTY) == []
    assert all(e.ps_uid != STEP_EMPTY for e in _completions(bus))


@pytest.mark.asyncio
async def test_reconcile_closes_a_gap_the_handler_left(neo4j_driver, backend, bus, mastery) -> None:
    """Ku masteries written with no handler running (a failed derivation, or a graph
    that predates the writer) leave a gap the graph shows; the reconciler closes it
    through the same writer and announces the transition once."""
    now = datetime.now(UTC).isoformat()
    # Both Kus mastered straight at the backend: no KnowledgeMastered, no derivation.
    assert (await backend.mark_mastered(USER, KU_A, now, 0.9, "report_approval")).is_ok
    assert (await backend.mark_mastered(USER, KU_B, now, 0.9, "report_approval")).is_ok
    assert await _step_edges(neo4j_driver, STEP) == []

    preview = await mastery.reconcile_step_mastery(dry_run=True)
    assert preview.is_ok and preview.value == [{"user_uid": USER, "ps_uid": STEP}]
    assert await _step_edges(neo4j_driver, STEP) == [], "a dry run writes nothing"
    assert _completions(bus) == []

    closed = await mastery.reconcile_step_mastery()
    assert closed.is_ok and closed.value == [{"user_uid": USER, "ps_uid": STEP}]
    edges = await _step_edges(neo4j_driver, STEP)
    assert len(edges) == 1 and edges[0]["props"]["method"] == STEP_MASTERY_METHOD
    assert [e.ps_uid for e in _completions(bus)] == [STEP]
    assert not await _enrolled(neo4j_driver, STEP)

    again = await mastery.reconcile_step_mastery()
    assert again.is_ok and again.value == [], "idempotent — a second run finds no gap"
    assert len(_completions(bus)) == 1
    assert all(e.ps_uid != STEP_EMPTY for e in _completions(bus)), "a zero-Ku step is no gap"
