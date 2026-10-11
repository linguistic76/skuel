"""
Unit Tests — the hub's learning sources: what they search, what they schedule, what they name
==============================================================================================

Method 1 (``get_optimal_next_path_steps``) and the daily plan's learning slot (method 5)
take their candidates from the ZPD assessment, from learning-aware vector search, from
``ps.get_ready_to_learn_for_user`` or from the context. Three things each source must be
true about:

- **The vector source searches the Ku index.** Every hit becomes a step named by its uid
  as a Ku (method 1) or a learning uid in the plan (method 5), so the search is of the
  ``Ku`` label — a published Ku is the only thing it can return. The whole-corpus
  ``Entity`` index holds every user's tasks, goals and entries beside the curriculum.
- **The plan's learning slot takes the top three LEARN actions.** An ``unblock`` action
  carries ``ZPDWeights.UNBLOCK_PRIORITY`` (0.9); a learn action built by the real
  ``ZPDService`` reaches that only with readiness, life-path alignment and behavioural
  readiness all near 1.0, so three blocking gaps would otherwise fill the top three and
  the plan would schedule no learning.
- **A step from the ZPD and context sources carries its Ku's published title**, read in
  one ``KuService.get_published_titles`` batch after the cut. A uid the read withholds
  keeps the placeholder; a failed read fails the answer; the vector and ``ps`` sources,
  whose rows carry a title, make no read.

Every test drives the real ``UserContextIntelligence`` built by its factory over
spec-checked facades.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from core.constants import ZPDWeights
from core.models.context_types import ContextualKnowledge, PathStep
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import EntityUID
from core.models.zpd.zpd_assessment import ZPDAction, ZPDAssessment
from core.services.choices_service import ChoicesService
from core.services.events_service import EventsService
from core.services.exercises.exercise_service import ExerciseService
from core.services.goals_service import GoalsService
from core.services.habits_service import HabitsService
from core.services.ku_service import KuService
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.principles_service import PrinciplesService
from core.services.ps_service import PsService
from core.services.report import ReportRelationshipService
from core.services.tasks_service import TasksService
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import RichUserContext
from core.services.zpd.zpd_service import ZPDService
from core.utils.result_simplified import Errors, Result

pytestmark = pytest.mark.asyncio

USER = "user_test"
READY = ["ku.test.ready_1", "ku.test.ready_2", "ku.test.ready_3", "ku.test.ready_4"]
GAPS = ["ku.test.gap_1", "ku.test.gap_2", "ku.test.gap_3"]
TITLES = {uid: f"Concept {uid.rsplit('_', 1)[-1]}" for uid in READY}


class Hub:
    """The real hub and the facades it was built over."""

    def __init__(
        self,
        intelligence: UserContextIntelligence,
        ku: MagicMock,
        vector_search: MagicMock | None,
    ) -> None:
        self.intelligence = intelligence
        self.ku = ku
        self.vector_search = vector_search


def _hub(
    context: RichUserContext,
    *,
    assessment: ZPDAssessment | None = None,
    vector_rows: list[dict[str, object]] | None = None,
    ready: list[ContextualKnowledge] | None = None,
    titles: Result[dict[str, str]] | None = None,
) -> Hub:
    """Every facade finds nothing unless a source is given; the title read answers ``titles``."""

    # Not a spec'd mock: a spec reads the facade's signatures, and this one annotates
    # its constructor with a type imported for type-checking only. The read is
    # name-checked instead — the attribute access raises if the method is renamed.
    _ = ReportRelationshipService.get_pending_submissions
    report = MagicMock()
    report.get_pending_submissions = AsyncMock(return_value=Result.ok([]))

    def _empty(cls: type, *reads: str) -> MagicMock:
        """A spec-checked facade whose named reads find nothing."""
        facade = create_autospec(cls, instance=True)
        for name in reads:
            getattr(facade, name).return_value = Result.ok([])
        return facade

    ps = _empty(PsService, "find_habits_reinforcing_knowledge", "find_events_applying_knowledge")
    ps.get_ready_to_learn_for_user.return_value = Result.ok(ready or [])
    ku = create_autospec(KuService, instance=True)
    ku.get_published_titles.return_value = titles if titles is not None else Result.ok({})

    vector_search = None
    if vector_rows is not None:
        vector_search = create_autospec(Neo4jVectorSearchService, instance=True)
        vector_search.learning_aware_search.return_value = Result.ok(vector_rows)

    zpd_service = None
    if assessment is not None:
        zpd_service = create_autospec(ZPDService, instance=True)
        zpd_service.assess_zone.return_value = Result.ok(assessment)
        context.zpd_assessment = assessment

    factory = UserContextIntelligenceFactory(
        tasks=_empty(TasksService, "get_actionable_tasks_for_user", "get_learning_tasks_for_user"),
        goals=_empty(GoalsService, "get_advancing_goals_for_user"),
        habits=_empty(HabitsService, "get_at_risk_habits_for_user"),
        events=_empty(EventsService, "get_upcoming_events_for_user"),
        choices=_empty(ChoicesService, "get_pending_decisions_for_user"),
        principles=_empty(PrinciplesService, "get_aligned_principles_for_user"),
        ku=ku,
        ps=ps,
        lp=MagicMock(),
        exercises=_empty(
            ExerciseService, "get_pending_revisions_for_user", "get_actionable_exercises_for_user"
        ),
        report=report,
        calendar=MagicMock(),
        vector_search_service=vector_search,
        zpd_service=zpd_service,
    )
    return Hub(factory.create(context), ku, vector_search)


def _context() -> RichUserContext:
    context = RichUserContext(user_uid=USER)
    context.available_minutes_daily = 480
    context.ready_to_learn_uids = set(READY)
    return context


def _real_actions(*, gaps: list[str], life_path_alignment: float) -> tuple[ZPDAction, ...]:
    """The actions the real ``ZPDService`` builds: every ready unit fully ready and
    behaviourally ready, so a learn action scores as high as the life path lets it."""
    service = ZPDService(backend=MagicMock())
    return tuple(
        service._build_recommended_actions(
            proximal_zone=list(READY),
            readiness_scores=dict.fromkeys(READY, 1.0),
            behavioral_readiness=1.0,
            life_path_alignment=life_path_alignment,
            blocking_gaps=gaps,
        )
    )


def _assessment(
    actions: tuple[ZPDAction, ...], *, proximal: list[str] | None = None
) -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=["ku.test.engaged"],
        proximal_zone=READY if proximal is None else proximal,
        engaged_paths=[],
        readiness_scores=dict.fromkeys(READY, 1.0),
        blocking_gaps=[a.entity_uid for a in actions if a.action_type == "unblock"],
        behavioral_readiness=1.0,
        recommended_actions=actions,
    )


def _vector_rows(uids: list[str]) -> list[dict[str, object]]:
    return [{"node": {"uid": uid, "title": TITLES[uid]}, "score": 0.9} for uid in uids]


# =============================================================================
# The vector source searches the Ku index
# =============================================================================


async def test_method_one_searches_the_ku_index() -> None:
    hub = _hub(_context(), vector_rows=_vector_rows(READY[:2]))

    result = await hub.intelligence.get_optimal_next_path_steps(consider_capacity=False)

    assert result.is_ok, result
    assert [step.ku_uid for step in result.value] == READY[:2]  # the hits are the answer
    assert hub.vector_search is not None
    hub.vector_search.learning_aware_search.assert_awaited_once()
    assert hub.vector_search.learning_aware_search.call_args.kwargs["label"] == NeoLabel.KU.value


async def test_the_daily_plan_searches_the_ku_index() -> None:
    hub = _hub(_context(), vector_rows=_vector_rows(READY[:2]))

    result = await hub.intelligence.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.learning == tuple(READY[:2])  # the hits are the slot
    assert hub.vector_search is not None
    hub.vector_search.learning_aware_search.assert_awaited_once()
    assert hub.vector_search.learning_aware_search.call_args.kwargs["label"] == NeoLabel.KU.value


def test_the_ku_label_is_the_one_the_hub_names() -> None:
    assert NeoLabel.KU.value == "Ku"


# =============================================================================
# The plan's learning slot: the top three LEARN actions
# =============================================================================


def test_a_real_learn_action_scores_below_an_unblock_without_a_life_path() -> None:
    """The probe: fully ready, behaviourally ready, no life path → 0.7 against 0.9."""
    actions = _real_actions(gaps=GAPS, life_path_alignment=0.0)
    learn = [a.priority for a in actions if a.action_type == "learn"]
    unblock = [a.priority for a in actions if a.action_type == "unblock"]
    assert len(unblock) == 3 and set(unblock) == {ZPDWeights.UNBLOCK_PRIORITY}
    assert learn and max(learn) < ZPDWeights.UNBLOCK_PRIORITY


async def test_three_blocking_gaps_do_not_empty_the_plan_s_learning() -> None:
    hub = _hub(
        _context(), assessment=_assessment(_real_actions(gaps=GAPS, life_path_alignment=0.0))
    )

    result = await hub.intelligence.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.learning == tuple(READY[:3])
    assert not set(GAPS) & set(result.value.learning)  # an unblock target is not scheduled


async def test_the_same_learn_actions_are_scheduled_with_no_gap_at_all() -> None:
    """The control: without gaps the slot already held these three."""
    hub = _hub(_context(), assessment=_assessment(_real_actions(gaps=[], life_path_alignment=0.0)))

    result = await hub.intelligence.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.learning == tuple(READY[:3])


def test_top_actions_of_a_type_are_cut_after_the_filter() -> None:
    assessment = _assessment(_real_actions(gaps=GAPS, life_path_alignment=0.0))

    top = assessment.top_recommended_actions(3)
    learn = assessment.top_recommended_actions(3, action_type="learn")

    assert all(a.action_type == "unblock" for a in top)
    assert [a.entity_uid for a in learn] == READY[:3]
    assert all(a.action_type == "learn" for a in learn)


async def test_method_one_takes_its_learn_candidates_the_same_way() -> None:
    hub = _hub(
        _context(), assessment=_assessment(_real_actions(gaps=GAPS, life_path_alignment=0.0))
    )

    result = await hub.intelligence.get_optimal_next_path_steps(
        max_steps=2, consider_capacity=False
    )

    assert result.is_ok, result
    assert [step.ku_uid for step in result.value] == READY[:2]


# =============================================================================
# The ZPD and context sources name their steps
# =============================================================================


def _uids(steps: list[PathStep]) -> list[str]:
    return [step.ku_uid for step in steps]


async def test_zpd_learn_steps_carry_their_published_titles() -> None:
    hub = _hub(
        _context(),
        assessment=_assessment(_real_actions(gaps=[], life_path_alignment=0.0)),
        titles=Result.ok(TITLES),
    )

    result = await hub.intelligence.get_optimal_next_path_steps(
        max_steps=3, consider_capacity=False
    )

    assert result.is_ok, result
    assert [step.title for step in result.value] == [TITLES[uid] for uid in READY[:3]]
    # One read, for the steps that survived the cut and no other.
    hub.ku.get_published_titles.assert_awaited_once_with(READY[:3])


async def test_zpd_proximal_steps_carry_their_published_titles() -> None:
    hub = _hub(_context(), assessment=_assessment((), proximal=READY), titles=Result.ok(TITLES))

    result = await hub.intelligence.get_optimal_next_path_steps(
        max_steps=2, consider_capacity=False
    )

    assert result.is_ok, result
    assert len(result.value) == 2
    assert all(step.title == TITLES[step.ku_uid] for step in result.value)
    hub.ku.get_published_titles.assert_awaited_once_with(_uids(result.value))


async def test_context_fallback_steps_carry_their_published_titles() -> None:
    hub = _hub(_context(), titles=Result.ok(TITLES))

    result = await hub.intelligence.get_optimal_next_path_steps(
        max_steps=2, consider_capacity=False
    )

    assert result.is_ok, result
    assert len(result.value) == 2
    assert all(step.title == TITLES[step.ku_uid] for step in result.value)
    hub.ku.get_published_titles.assert_awaited_once_with(_uids(result.value))


async def test_a_uid_the_read_withholds_keeps_the_placeholder() -> None:
    withheld = READY[1]
    answered = {uid: title for uid, title in TITLES.items() if uid != withheld}
    hub = _hub(
        _context(),
        assessment=_assessment(_real_actions(gaps=[], life_path_alignment=0.0)),
        titles=Result.ok(answered),
    )

    result = await hub.intelligence.get_optimal_next_path_steps(
        max_steps=3, consider_capacity=False
    )

    assert result.is_ok, result
    by_uid = {step.ku_uid: step.title for step in result.value}
    assert by_uid[withheld] == f"Knowledge Unit {withheld}"
    assert by_uid[READY[0]] == TITLES[READY[0]]


async def test_a_failed_title_read_fails_the_answer() -> None:
    refused: Result[dict[str, str]] = Result.fail(
        Errors.database(operation="get_published_titles", message="graph away")
    )
    hub = _hub(
        _context(),
        assessment=_assessment(_real_actions(gaps=[], life_path_alignment=0.0)),
        titles=refused,
    )

    result = await hub.intelligence.get_optimal_next_path_steps(consider_capacity=False)

    assert result.is_error
    assert result.expect_error().category == refused.expect_error().category


async def test_the_vector_source_makes_no_title_read() -> None:
    hub = _hub(_context(), vector_rows=_vector_rows(READY[:2]))

    result = await hub.intelligence.get_optimal_next_path_steps(consider_capacity=False)

    assert result.is_ok, result
    assert [step.title for step in result.value] == [TITLES[uid] for uid in READY[:2]]
    hub.ku.get_published_titles.assert_not_awaited()


async def test_the_ps_source_makes_no_title_read() -> None:
    ready = [
        ContextualKnowledge(uid=uid, title=TITLES[uid], priority_score=0.5, prerequisites_met=True)
        for uid in READY[:2]
    ]
    hub = _hub(_context(), ready=ready)

    result = await hub.intelligence.get_optimal_next_path_steps(consider_capacity=False)

    assert result.is_ok, result
    assert [step.title for step in result.value] == [TITLES[uid] for uid in READY[:2]]
    hub.ku.get_published_titles.assert_not_awaited()


async def test_an_empty_answer_makes_no_title_read() -> None:
    context = _context()
    context.ready_to_learn_uids = set()
    hub = _hub(context, titles=Result.ok(TITLES))

    result = await hub.intelligence.get_optimal_next_path_steps()

    assert result.is_ok, result
    assert result.value == []
    hub.ku.get_published_titles.assert_not_awaited()


# =============================================================================
# The twelfth service is required
# =============================================================================


def test_the_hub_refuses_to_build_without_the_ku_facade() -> None:
    with pytest.raises(ValueError, match="ku"):
        UserContextIntelligenceFactory(
            tasks=MagicMock(),
            goals=MagicMock(),
            habits=MagicMock(),
            events=MagicMock(),
            choices=MagicMock(),
            principles=MagicMock(),
            ku=None,  # type: ignore[arg-type]  # the refusal under test
            ps=MagicMock(),
            lp=MagicMock(),
            exercises=MagicMock(),
            report=MagicMock(),
            calendar=MagicMock(),
        )


def test_an_action_is_what_the_real_builder_makes() -> None:
    """The fixture's actions are the service's own, not hand-typed."""
    (action, *_rest) = _real_actions(gaps=GAPS, life_path_alignment=0.0)
    assert action == ZPDAction(
        entity_uid=EntityUID(GAPS[0]),
        entity_type="path_step",
        action_type="unblock",
        priority=ZPDWeights.UNBLOCK_PRIORITY,
        rationale="blocking gap — unlocks further progress",
        ku_uid=GAPS[0],
    )
