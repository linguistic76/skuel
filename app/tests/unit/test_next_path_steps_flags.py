"""
Unit Tests — ``get_optimal_next_path_steps``: what its two flags mean
=====================================================================

The method answers from one of five candidate shapes — the ZPD assessment's learn
actions, its proximal zone, vector search, ``ps.get_ready_to_learn_for_user`` and the
context's own ready-to-learn list. The flags mean the same thing in each:

- ``consider_goals`` — a step serving a goal scores higher by
  ``NextStepRanking.GOAL_WEIGHT_PER_GOAL`` per goal, up to ``GOAL_WEIGHT_MAX``. Off,
  goal alignment changes no score and moves no step; ``aligns_with_goals`` is filled
  either way.
- ``consider_capacity`` — the returned steps fit ``available_minutes_daily`` together.
  Off, no step is dropped, and time changes no score in either run.

Each test ranks one fixture twice, flag on and flag off, through the real
``UserContextIntelligence`` built by its factory over spec-checked facades.
"""

from collections.abc import Callable
from unittest.mock import MagicMock, create_autospec

import pytest

from core.constants import NextStepRanking
from core.models.context_types import ContextualKnowledge, PathStep
from core.models.type_hints import EntityUID
from core.models.zpd.zpd_assessment import ZPDAction, ZPDAssessment
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.ps_service import PsService
from core.services.tasks_service import TasksService
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.services.zpd.zpd_service import ZPDService
from core.utils.result_simplified import Result

FIRST = "ku.test.first"
SECOND = "ku.test.second"
THIRD = "ku.test.third"  # the lowest-scored candidate, and the one three goals need
CANDIDATES = [FIRST, SECOND, THIRD]

# What each source scores the three candidates before a flag acts.
SOURCE_SCORES = {FIRST: 0.6, SECOND: 0.5, THIRD: 0.4}

GOALS = ["goal_a", "goal_b", "goal_c"]
EXPECTED_GOAL_WEIGHT = min(
    NextStepRanking.GOAL_WEIGHT_MAX, len(GOALS) * NextStepRanking.GOAL_WEIGHT_PER_GOAL
)


def _context() -> RichUserContext:
    """Three goals need THIRD; FIRST and SECOND are the last thing blocking other items."""
    context = RichUserContext(user_uid="user_test")
    context.learning_goals = list(GOALS)
    # Each goal waits on THIRD and on one more unit, so no goal counts as unlocked by THIRD.
    context.prerequisites_needed = {goal: [THIRD, "ku.test.elsewhere"] for goal in GOALS}
    context.prerequisites_needed["item_1"] = [FIRST]
    context.prerequisites_needed["item_2"] = [FIRST]
    context.prerequisites_needed["item_3"] = [SECOND]
    context.next_recommended_knowledge = list(CANDIDATES)
    return context


def _intelligence(
    context: RichUserContext,
    *,
    ready: list[ContextualKnowledge] | None = None,
    vector_rows: list[dict[str, object]] | None = None,
    assessment: ZPDAssessment | None = None,
) -> UserContextIntelligence:
    """The real hub over facades that find no application of any unit."""
    ps = create_autospec(PsService, instance=True)
    ps.get_ready_to_learn_for_user.return_value = Result.ok(ready or [])
    ps.find_habits_reinforcing_knowledge.return_value = Result.ok([])
    ps.find_events_applying_knowledge.return_value = Result.ok([])

    tasks = create_autospec(TasksService, instance=True)
    tasks.get_learning_tasks_for_user.return_value = Result.ok([])

    vector_search = None
    if vector_rows is not None:
        vector_search = create_autospec(Neo4jVectorSearchService, instance=True)
        vector_search.learning_aware_search.return_value = Result.ok(vector_rows)

    zpd_service = None
    if assessment is not None:
        zpd_service = create_autospec(ZPDService, instance=True)
        zpd_service.assess_zone.return_value = Result.ok(assessment)

    factory = UserContextIntelligenceFactory(
        tasks=tasks,
        goals=MagicMock(),
        habits=MagicMock(),
        events=MagicMock(),
        choices=MagicMock(),
        principles=MagicMock(),
        ps=ps,
        lp=MagicMock(),
        exercises=MagicMock(),
        report=MagicMock(),
        calendar=MagicMock(),
        vector_search_service=vector_search,
        zpd_service=zpd_service,
    )
    return factory.create(context)


def _assessment(
    *,
    proximal: list[str],
    readiness: dict[str, float] | None = None,
    actions: tuple[ZPDAction, ...] = (),
) -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=["ku.test.engaged"],
        proximal_zone=proximal,
        engaged_paths=[],
        readiness_scores=readiness or {},
        blocking_gaps=[],
        behavioral_readiness=0.0,
        recommended_actions=actions,
    )


def _learn_action(ku_uid: str, priority: float) -> ZPDAction:
    return ZPDAction(
        entity_uid=EntityUID(ku_uid),
        entity_type="path_step",
        action_type="learn",
        priority=priority,
        rationale="ready to learn",
        ku_uid=ku_uid,
    )


def _zpd_actions(context: RichUserContext) -> UserContextIntelligence:
    actions = tuple(_learn_action(uid, SOURCE_SCORES[uid]) for uid in CANDIDATES)
    return _intelligence(context, assessment=_assessment(proximal=CANDIDATES, actions=actions))


def _zpd_proximal(context: RichUserContext) -> UserContextIntelligence:
    # No life-path or behavioural term in this fixture: priority is readiness alone.
    readiness = {FIRST: 1.0, SECOND: 0.8, THIRD: 0.6}
    return _intelligence(context, assessment=_assessment(proximal=CANDIDATES, readiness=readiness))


def _vector(context: RichUserContext) -> UserContextIntelligence:
    rows: list[dict[str, object]] = [
        {"node": {"uid": uid, "title": uid}, "score": SOURCE_SCORES[uid]} for uid in CANDIDATES
    ]
    return _intelligence(context, vector_rows=rows)


def _ps(context: RichUserContext) -> UserContextIntelligence:
    ready = [
        ContextualKnowledge(
            uid=uid, title=uid, priority_score=SOURCE_SCORES[uid], prerequisites_met=True
        )
        for uid in CANDIDATES
    ]
    return _intelligence(context, ready=ready)


def _context_fallback(context: RichUserContext) -> UserContextIntelligence:
    # Neither optional service is wired and ps finds nothing: the context answers.
    return _intelligence(context)


Arrange = Callable[[RichUserContext], UserContextIntelligence]

SOURCES = [
    pytest.param(_zpd_actions, id="zpd-learn-actions"),
    pytest.param(_zpd_proximal, id="zpd-proximal-zone"),
    pytest.param(_vector, id="vector-search"),
    pytest.param(_ps, id="ps-ready-to-learn"),
    pytest.param(_context_fallback, id="context-fallback"),
]


async def _steps(
    intelligence: UserContextIntelligence, *, consider_goals: bool, consider_capacity: bool
) -> list[PathStep]:
    result = await intelligence.get_optimal_next_path_steps(
        max_steps=5, consider_goals=consider_goals, consider_capacity=consider_capacity
    )
    assert result.is_ok
    return list(result.value)


def _uids(steps: list[PathStep]) -> list[str]:
    return [step.ku_uid for step in steps]


def _scores(steps: list[PathStep]) -> dict[str, float]:
    return {step.ku_uid: step.priority_score for step in steps}


# =============================================================================
# consider_goals
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_goals_off_ranks_by_the_source_score_alone(arrange: Arrange) -> None:
    steps = await _steps(arrange(_context()), consider_goals=False, consider_capacity=False)

    assert _uids(steps) == [FIRST, SECOND, THIRD]


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_goals_on_adds_the_goal_weight_to_the_aligned_step_and_no_other(
    arrange: Arrange,
) -> None:
    off = await _steps(arrange(_context()), consider_goals=False, consider_capacity=False)
    on = await _steps(arrange(_context()), consider_goals=True, consider_capacity=False)

    off_scores, on_scores = _scores(off), _scores(on)
    assert on_scores[THIRD] == pytest.approx(off_scores[THIRD] + EXPECTED_GOAL_WEIGHT)
    assert on_scores[FIRST] == off_scores[FIRST]
    assert on_scores[SECOND] == off_scores[SECOND]
    # Three goals lift the lowest-scored candidate past the other two.
    assert _uids(on) == [THIRD, FIRST, SECOND]


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_goals_flag_changes_nothing_but_score_and_order(arrange: Arrange) -> None:
    off = await _steps(arrange(_context()), consider_goals=False, consider_capacity=False)
    on = await _steps(arrange(_context()), consider_goals=True, consider_capacity=False)

    def without_score(steps: list[PathStep]) -> dict[str, tuple[object, ...]]:
        return {
            step.ku_uid: (
                step.title,
                step.rationale,
                step.prerequisites_met,
                step.aligns_with_goals,
                step.unlocks_count,
                step.estimated_time_minutes,
                step.application_opportunities,
            )
            for step in steps
        }

    assert without_score(on) == without_score(off)
    # The goals are named on the step whether or not they are weighed.
    assert {step.ku_uid: step.aligns_with_goals for step in off}[THIRD] == tuple(GOALS)


@pytest.mark.asyncio
async def test_goal_weight_stops_at_its_maximum() -> None:
    context = _context()
    many_goals = [f"goal_{n}" for n in range(8)]
    context.learning_goals = many_goals
    for goal in many_goals:
        context.prerequisites_needed[goal] = [THIRD, "ku.test.elsewhere"]

    off = await _steps(_ps(context), consider_goals=False, consider_capacity=False)
    on = await _steps(_ps(context), consider_goals=True, consider_capacity=False)

    assert _scores(on)[THIRD] == pytest.approx(
        _scores(off)[THIRD] + NextStepRanking.GOAL_WEIGHT_MAX
    )


@pytest.mark.asyncio
async def test_goal_weight_never_lowers_a_vector_score_above_one() -> None:
    rows: list[dict[str, object]] = [
        {"node": {"uid": THIRD, "title": THIRD}, "score": 1.12},
        {"node": {"uid": FIRST, "title": FIRST}, "score": 1.05},
    ]
    on = await _steps(
        _intelligence(_context(), vector_rows=rows), consider_goals=True, consider_capacity=False
    )

    assert _scores(on) == {THIRD: 1.12, FIRST: 1.05}
    assert _uids(on) == [THIRD, FIRST]


@pytest.mark.asyncio
async def test_empty_proximal_zone_hands_the_caller_s_goals_flag_to_the_next_source() -> None:
    """A non-empty assessment with no candidates falls through; the flag goes with it."""
    context = _context()
    intelligence = _intelligence(context, assessment=_assessment(proximal=[]))

    off = await _steps(intelligence, consider_goals=False, consider_capacity=False)
    on = await _steps(intelligence, consider_goals=True, consider_capacity=False)

    assert _uids(off) == [FIRST, SECOND, THIRD]
    assert _uids(on) == [THIRD, FIRST, SECOND]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("consider_goals", "names_goals"), [(True, True), (False, False)], ids=["on", "off"]
)
async def test_vector_query_names_goals_only_when_goals_are_considered(
    consider_goals: bool, names_goals: bool
) -> None:
    intelligence = _vector(_context())

    await _steps(intelligence, consider_goals=consider_goals, consider_capacity=False)

    query = intelligence.vector_search.learning_aware_search.call_args.kwargs["text"]
    assert ("goal-aligned learning" in query) is names_goals


@pytest.mark.asyncio
async def test_learn_actions_are_taken_by_priority_not_by_position() -> None:
    """With more learn actions than candidates are read, the best one is still read."""
    filler = tuple(_learn_action(f"ku.test.filler_{n}", 0.1) for n in range(4))
    actions = (*filler, _learn_action(FIRST, 0.9))
    intelligence = _intelligence(
        _context(), assessment=_assessment(proximal=[FIRST], actions=actions)
    )

    result = await intelligence.get_optimal_next_path_steps(
        max_steps=2, consider_goals=False, consider_capacity=False
    )

    assert _uids(list(result.value))[0] == FIRST


# =============================================================================
# consider_capacity
# =============================================================================


def _timed_context() -> RichUserContext:
    """60 minutes in the day; FIRST and SECOND take 40 each, THIRD takes 20."""
    context = _context()
    context.available_minutes_daily = 60
    context.estimated_time_to_mastery = {FIRST: 40, SECOND: 40, THIRD: 20}
    return context


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_capacity_on_returns_steps_that_fit_the_day_together(arrange: Arrange) -> None:
    steps = await _steps(arrange(_timed_context()), consider_goals=False, consider_capacity=True)

    # SECOND does not fit after FIRST; THIRD, ranked below it, does.
    assert _uids(steps) == [FIRST, THIRD]
    assert sum(step.estimated_time_minutes for step in steps) <= 60


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_capacity_off_drops_no_step(arrange: Arrange) -> None:
    steps = await _steps(arrange(_timed_context()), consider_goals=False, consider_capacity=False)

    assert _uids(steps) == [FIRST, SECOND, THIRD]


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_capacity_flag_changes_no_score(arrange: Arrange) -> None:
    off = await _steps(arrange(_timed_context()), consider_goals=False, consider_capacity=False)
    on = await _steps(arrange(_timed_context()), consider_goals=False, consider_capacity=True)

    off_scores = _scores(off)
    assert _scores(on) == {uid: off_scores[uid] for uid in _uids(on)}


@pytest.mark.asyncio
@pytest.mark.parametrize("arrange", SOURCES)
async def test_capacity_is_spent_in_the_order_the_goal_weight_ranks(arrange: Arrange) -> None:
    """Both flags on: the goal-aligned step is ranked first, so it is fitted first."""
    steps = await _steps(arrange(_timed_context()), consider_goals=True, consider_capacity=True)

    assert _uids(steps) == [THIRD, FIRST]
