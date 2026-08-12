"""
Composition guard for the cross-layer weekly life summary.
==========================================================

``AnalyticsAggregationService.aggregate_weekly_life_summary`` put the
``Result[dict]`` objects returned by ``AnalyticsMetricsService.calculate_*_metrics``
straight into ``layer1_domains`` and into the returned summary, unwrapping only
``curriculum_metrics``. Every analysis helper below it indexes and ``.get()``s
those arguments, and ``Result`` supports neither — so the very first membership
test, ``if "total_count" in domains["tasks"]``, raised
``TypeError: argument of type 'Result' is not a container or iterable`` and the
method could not return at all. ``detect_cross_domain_patterns`` carried the
identical defect one method down.

**Why the stubs sit where they do.** The bug is a type-seam bug: it lives
exactly at the boundary between the metrics service and the aggregator. So the
metrics service here is the REAL one — it is what wraps in ``Result``, and it is
what computes every number asserted below from real domain-model instances. The
stubs sit one layer further out, at the six ``get_user_items_in_range``
delegations (``TimeQueryMixin``, declared in ``core/ports/domain_protocols.py``)
and the three Layer-0/2 reads. A test that instead stubbed
``calculate_*_metrics`` to return plain dicts would pass against the bug, which
is the whole reason no existing test caught it.

Neo4j is not involved: the queries underneath those delegations are a different
subject, guarded by ``tests/integration/test_knowledge_metrics_learner_scope.py``
and the per-domain analytics pipelines.

Two defects in ``AnalyticsMetricsService`` had to fall before this path could run
end to end, both unconditional for any user holding the entity in question:
``calculate_principle_metrics`` summed ``PrincipleStrength`` enum members, and
``calculate_event_metrics`` compared ``Event.start_time`` (a ``time``) against
``datetime.now()``. Both are pinned below so they cannot come back.

The last three classes here came from the Codex review on #1032: the seam is now
typed against ``AnalyticsMetricsOperations`` (P1), a week with no activity must
not name a top substance driver (P2), and ``upcoming`` must not count an event
already marked completed (P2).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from core.models.choice.choice import Choice
from core.models.enums import Domain, EntityStatus, PrincipleStrength
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.ports.analytics_protocols import AnalyticsMetricsOperations
from core.services.analytics.analytics_aggregation_service import AnalyticsAggregationService
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
from core.utils.result_simplified import Result

USER = "user_weekly_summary"

# A 7-day window, which is what the journal metric divides entries by.
START_DATE = date(2026, 8, 1)
END_DATE = date(2026, 8, 7)
WINDOW_DAYS = 7


# ============================================================================
# STUBS — one method each, matching the production signature
# ============================================================================


class _StubDomainService:
    """The single method every ``calculate_*_metrics`` call makes on a Layer-1 facade.

    Mirrors ``TimeQueryMixin.get_user_items_in_range``, including the
    ``include_completed`` filtering: ``calculate_goal_metrics`` calls it twice,
    once with each value, and derives ``completion_rate`` from the difference.
    A stub that ignored the flag would make that rate meaningless.
    """

    def __init__(self, items: list[Any]) -> None:
        self._items = items

    async def get_user_items_in_range(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
        date_field: Any = None,
    ) -> Result[list[Any]]:
        if include_completed:
            return Result.ok(list(self._items))
        return Result.ok([i for i in self._items if i.status != EntityStatus.COMPLETED])


class _StubPsService:
    """``PsService``'s three knowledge delegations, as ``AnalyticsMetricsService`` calls them.

    The real Cypher behind these is guarded over a live graph in
    ``tests/integration/test_knowledge_metrics_learner_scope.py`` — including the
    step→Ku resolution that turns a learner's activity channels into the
    per-step scores this hands back ready-made.
    """

    def __init__(
        self, steps: list[PathStep], counts: dict[str, int], substance: dict[str, float]
    ) -> None:
        self._steps = steps
        self._counts = counts
        self._substance = substance

    async def find_engaged_steps_in_window(
        self, user_uid: str, start_date: date, end_date: date, limit: int | None = None
    ) -> Result[list[PathStep]]:
        return Result.ok(list(self._steps))

    async def count_engaged_knowledge(self, user_uid: str) -> Result[dict[str, int]]:
        return Result.ok(dict(self._counts))

    async def get_user_substance_scores(
        self, ps_uids: Any, user_context: Any
    ) -> Result[dict[str, float]]:
        return Result.ok({uid: self._substance[uid] for uid in ps_uids})


class _StubLpService:
    """``LpService.list_by_user`` — the one call ``calculate_curriculum_metrics`` makes."""

    def __init__(self, learning_paths: list[LearningPath]) -> None:
        self._learning_paths = learning_paths

    async def list_by_user(self, user_uid: str, limit: Any = None) -> Result[list[LearningPath]]:
        return Result.ok(list(self._learning_paths))


class _StubCrossDomainBackend:
    """The two cross-domain reads the metrics service makes — ONE object, as in production.

    ``get_journal_entries_in_range`` returns rows shaped as
    ``_get_journal_reports`` reads them.

    ``get_user_knowledge_channels`` is the learner's activity read UNWINDOWED,
    and returns nothing here: the per-step scores this file asserts on are handed
    back ready-made by ``_StubPsService``, and the real channels→scores join is
    guarded over a live graph in
    ``tests/integration/test_knowledge_metrics_learner_scope.py``. What matters
    at this seam is that the metric sources its channels from the BACKEND at all
    — a UserContext's copies are bounded by the planning window and would drop
    older applications.
    """

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    async def get_journal_entries_in_range(
        self, user_uid: str, start_datetime: str, end_datetime: str
    ) -> Result[list[dict[str, Any]]]:
        return Result.ok(list(self._records))

    async def get_user_knowledge_channels(
        self, user_uid: str, activity_types: list[str]
    ) -> Result[list[dict[str, Any]]]:
        return Result.ok([])


# ============================================================================
# SEED — every figure asserted below is derivable from this by hand
# ============================================================================


# What the LEARNER's own activity channels score each step at. Two exact values
# landing in different bands: 0.30 in the 0.3-0.6 "applied" band, 0.90 in the
# 0.8+ "embodied" band, averaging 0.60 — so a metric that collapsed the bands,
# or averaged the wrong field, cannot produce those three numbers together.
PERSONAL_SUBSTANCE = {"ps.applied": 0.30, "ps.embodied": 0.90}


def _seed_path_steps() -> list[PathStep]:
    """Two steps whose NODE counters deliberately disagree with the learner.

    Both carry the full set — habits 0.30 (at cap) + entries 0.20 (capped from
    0.21) + events 0.25 (at cap) + tasks 0.15, and ``_decay_weight`` is
    ``e^(-days/30)`` so a same-day timestamp weighs exactly 1.0 — which is
    ``Curriculum.substance_score() == 0.90`` for BOTH.

    That is the corpus-global figure: `increment_substance` writes those counters
    with no ``user_uid``, so they pool every learner's activity. Since 2026-08-12
    the metric does not read them, and seeding both steps identically high is
    what makes the assertions below discriminate — a global reading yields
    avg 0.90 with embodied=2/applied=0, a personal one avg 0.60 with
    embodied=1/applied=1.
    """
    now = datetime.now(UTC)
    return [
        PathStep(
            uid=uid,
            title=title,
            times_built_into_habits=3,
            last_built_into_habit_date=now,
            times_reflected_in_entries=3,
            last_reflected_date=now,
            times_practiced_in_events=5,
            last_practiced_date=now,
            times_applied_in_tasks=3,
            last_applied_date=now,
        )
        for uid, title in (("ps.applied", "Applied step"), ("ps.embodied", "Embodied step"))
    ]


@pytest.fixture
def metrics() -> AnalyticsMetricsService:
    """The real metrics service over stubbed edges."""
    upcoming = datetime.now() + timedelta(days=2)

    return AnalyticsMetricsService(
        # Layer 1 — 2 tasks, 3 habits, 2 goals, 2 events, 1 choice, 2 principles
        tasks_service=_StubDomainService(
            [
                Task(uid="t1", title="Ship report", user_uid=USER, status=EntityStatus.COMPLETED),
                Task(uid="t2", title="Draft outline", user_uid=USER, status=EntityStatus.ACTIVE),
            ]
        ),
        habits_service=_StubDomainService(
            [
                Habit(uid="h1", title="Morning pages", user_uid=USER),
                Habit(uid="h2", title="Evening walk", user_uid=USER),
                Habit(uid="h3", title="Reading", user_uid=USER),
            ]
        ),
        goals_service=_StubDomainService(
            [
                Goal(uid="g1", title="Learn Cypher", user_uid=USER, status=EntityStatus.ACTIVE),
                Goal(uid="g2", title="Run 10k", user_uid=USER, status=EntityStatus.COMPLETED),
            ]
        ),
        events_service=_StubDomainService(
            [
                Event(
                    uid="e1",
                    title="Retrospective",
                    user_uid=USER,
                    event_date=date(2026, 8, 3),
                    start_time=datetime(2026, 8, 3, 9, 0).time(),
                    duration_minutes=30,
                    status=EntityStatus.COMPLETED,
                ),
                Event(
                    uid="e2",
                    title="Study block",
                    user_uid=USER,
                    event_date=upcoming.date(),
                    start_time=upcoming.time(),
                    duration_minutes=60,
                ),
            ]
        ),
        choices_service=_StubDomainService(
            [Choice(uid="c1", title="Pick a thesis topic", user_uid=USER)]
        ),
        principle_service=_StubDomainService(
            [
                Principle(
                    uid="p1", title="Honesty", user_uid=USER, strength=PrincipleStrength.CORE
                ),
                Principle(
                    uid="p2", title="Curiosity", user_uid=USER, strength=PrincipleStrength.MODERATE
                ),
            ]
        ),
        # Layer 2 — presence is all calculate_journal_metrics checks before
        # reaching for the cross-domain backend.
        content_enrichment=object(),
        # Layer 0
        ku_service=_StubPsService(
            _seed_path_steps(), {"total": 4, "mastered": 1}, PERSONAL_SUBSTANCE
        ),
        lp_service=_StubLpService([LearningPath(uid="lp.python", title="Python Mastery")]),
        cross_domain_backend=_StubCrossDomainBackend(
            [
                {
                    "uid": "rep1",
                    "processed_content": "x" * 1000,
                    "metadata": {"themes": ["learning"], "action_items": ["read chapter 2"]},
                    "created_at": "2026-08-02T10:00:00",
                },
                {
                    "uid": "rep2",
                    "processed_content": "y" * 1000,
                    "metadata": {"themes": ["learning", "rest"], "action_items": []},
                    "created_at": "2026-08-05T10:00:00",
                },
            ]
        ),
    )


@pytest.fixture
def aggregation(metrics: AnalyticsMetricsService) -> AnalyticsAggregationService:
    return AnalyticsAggregationService(metrics_service=metrics)


@pytest.mark.asyncio
class TestWeeklyLifeSummaryComposition:
    """The summary must compose plain dicts carrying the metrics' real values."""

    async def test_metrics_service_still_returns_result(
        self, metrics: AnalyticsMetricsService
    ) -> None:
        """The seam this whole file guards.

        Every assertion below is only evidence because the metrics service hands
        the aggregator a ``Result``. If that contract is ever changed to a plain
        dict, the unwrapping becomes dead and these tests would keep passing for
        the wrong reason — so pin the seam itself, at all three layers.
        """
        assert isinstance(await metrics.calculate_task_metrics(USER, START_DATE, END_DATE), Result)
        assert isinstance(
            await metrics.calculate_knowledge_metrics(USER, START_DATE, END_DATE), Result
        )
        assert isinstance(await metrics.calculate_curriculum_metrics(USER), Result)
        assert isinstance(
            await metrics.calculate_journal_metrics(USER, START_DATE, END_DATE), Result
        )

    async def test_total_activity_score_is_a_number_with_the_derived_value(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """``_calculate_total_activity`` is where the ``Result`` first raised.

        Per-domain scores, each capped at 100 and averaged over the six domains
        that contributed:

            tasks       2 x 10  =  20
            habits      3 x 15  =  45
            goals       1 x 20  =  20   (g2 is COMPLETED, so not active)
            events      1.5h x 2 =  3.0 (30 + 60 minutes scheduled)
            choices     1 x 25  =  25
            principles  2 x 15  =  30
                                --------
                        143 / 6 =  23.8
        """
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)

        total = summary["total_activity_score"]
        assert isinstance(total, float | int)
        assert not isinstance(total, Result)
        assert total == 23.8

    async def test_substance_metrics_is_a_plain_dict_with_real_values(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """Layer 0's ``substance_metrics`` was handed through unwrapped.

        The bands and the average are computed by the real metrics service from
        the LEARNER's scores for the two seeded path steps (0.30 applied, 0.90
        embodied). Both steps' node counters read 0.90 — the corpus-global
        figure — so avg 0.90 with embodied=2 here means the metric went back to
        ``Curriculum.substance_score()``.
        """
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)

        substance = summary["layer_0_knowledge"]["substance_metrics"]
        assert isinstance(substance, dict)
        assert substance["total_knowledge_units"] == 2
        assert substance["avg_substance_score"] == 0.6
        assert substance["theoretical_knowledge"] == 0
        assert substance["applied_knowledge"] == 1
        assert substance["practiced_knowledge"] == 0
        assert substance["embodied_knowledge"] == 1
        assert substance["knowledge_by_domain"] == {
            str(Domain.KNOWLEDGE): {"count": 2, "avg_substance": 0.6}
        }
        assert substance["date_range"] == f"{START_DATE} to {END_DATE}"

    async def test_no_layer_carries_a_result_object(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """All seven unwrap sites, not just the one that happened to raise first.

        ``curriculum_progress`` was the only one already unwrapped; a fix applied
        to ``tasks`` alone (the domain named in the traceback) would leave the
        other five in place, and nothing downstream re-raises on them.
        """
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)

        for domain, payload in summary["layer_1_activities"].items():
            assert isinstance(payload, dict), f"{domain} is {type(payload).__name__}"

        assert isinstance(summary["layer_0_knowledge"]["substance_metrics"], dict)
        assert isinstance(summary["layer_0_knowledge"]["curriculum_progress"], dict)
        assert isinstance(summary["layer_2_reflection"], dict)

    async def test_layer_1_values_reach_the_summary(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """The six domain dicts carry the metrics service's own numbers.

        Asserting the identities, not merely non-emptiness: an aggregator that
        substituted empty dicts for failed layers would satisfy "is a dict".
        """
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)
        layer1 = summary["layer_1_activities"]

        assert layer1["tasks"]["total_count"] == 2
        assert layer1["tasks"]["completed_count"] == 1
        assert layer1["tasks"]["completion_rate"] == 50.0
        assert layer1["habits"]["total_active"] == 3
        assert layer1["goals"]["total_active"] == 1
        assert layer1["goals"]["total_completed"] == 1
        assert layer1["events"]["total_count"] == 2
        assert layer1["events"]["total_hours_scheduled"] == 1.5
        assert layer1["events"]["upcoming_count"] == 1
        assert layer1["choices"]["total_choices"] == 1
        assert layer1["principles"]["active_principles"] == 2
        # CORE (rank 5) and MODERATE (rank 3), as a fraction of CORE: (1.0 + 0.6) / 2
        assert layer1["principles"]["alignment_score"] == 80.0

    async def test_layer_0_and_2_values_reach_the_summary(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """Curriculum progress and journal reflection, likewise by identity."""
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)

        curriculum = summary["layer_0_knowledge"]["curriculum_progress"]
        assert curriculum["active_learning_paths"] == 1
        assert curriculum["completed_learning_paths"] == 0
        # From count_engaged_knowledge, not from the LearningPath objects.
        assert curriculum["total_knowledge_units"] == 4
        assert curriculum["mastered_knowledge_units"] == 1
        assert curriculum["current_focus"] == {
            "lp_uid": "lp.python",
            "lp_title": "Python Mastery",
            "progress": 0.0,
        }

        journal = summary["layer_2_reflection"]
        assert journal["total_entries"] == 2
        assert journal["avg_entry_length"] == 1000
        assert journal["reflection_frequency"] == round(2 / WINDOW_DAYS, 2)
        assert journal["top_themes"] == ["learning", "rest"]
        assert journal["action_items_identified"] == 1

    async def test_cross_layer_insights_render_from_the_unwrapped_dicts(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """The synthesis step is annotated ``dict`` and was handed three ``Result``s.

        Its breakdown line is a percentage split, so it must sum to 100 — the raw
        ``contribution_estimate`` is ``activity_count x weight``, an unbounded
        magnitude that as a bare "%" printed values over 100.
        """
        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)
        correlation = summary["cross_layer_insights"]["knowledge_activity_correlation"]

        # habits 3 x 0.10 = 0.30, tasks 2 x 0.05 = 0.10, events 2 x 0.05 = 0.10
        assert correlation["top_substance_driver"] == "habits"
        assert correlation["avg_substance_score"] == 0.6
        assert "Habits: 60%, Tasks: 20%, Events: 20%" in correlation["insight"]

        assert isinstance(summary["summary"], str)
        assert "Most active domain" in summary["summary"]

    async def test_downstream_reviews_read_the_key_the_summary_writes(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """Monthly/quarterly/yearly all reach into the weekly summary's Layer-1 dict.

        They read it as ``["domains"]``, a key ``aggregate_weekly_life_summary``
        has never returned — a ``KeyError`` that only became reachable once the
        ``Result`` defect stopped raising first. ``layer_1_activities`` is the
        documented shape (``adapters/inbound/analytics_summary_api.py``), so the
        readers move, not the writer.
        """
        monthly = await aggregation.aggregate_monthly_life_review(USER, START_DATE, END_DATE)
        assert monthly["goal_progress_analysis"]["on_track"] == 0
        assert monthly["monthly_trends"]["completion_trends"]["tasks"] == 50.0

        quarterly = await aggregation.aggregate_quarterly_progress(USER, START_DATE, END_DATE)
        assert quarterly["strategic_insights"]["principle_alignment"] == 80.0

        yearly = await aggregation.aggregate_yearly_review(USER, START_DATE, END_DATE)
        assert yearly["year_achievements"]["goals_completed"] == 1
        assert yearly["year_achievements"]["key_decisions"] == 1

    async def test_cross_domain_patterns_unwraps_the_same_way(
        self, aggregation: AnalyticsAggregationService
    ) -> None:
        """The sibling method carried the identical defect — ``Result`` has no ``.get``."""
        patterns = await aggregation.detect_cross_domain_patterns(USER, START_DATE, END_DATE)

        assert patterns["choice_principle_alignment"] == {
            "alignment_score": 80.0,
            "choices_count": 1,
            "principles_count": 2,
        }
        assert patterns["goal_habit_support"]["goals_active"] == 1
        assert patterns["time_allocation"]["total_scheduled_hours"] == 1.5
        assert patterns["domain_balance"]["most_active_domain"] == "habits"

    async def test_a_failed_layer_degrades_to_an_empty_dict(
        self, metrics: AnalyticsMetricsService, aggregation: AnalyticsAggregationService
    ) -> None:
        """The fail-soft half of the contract this file's header states.

        Unwrapping must not turn a failed metric into a raise: the layer renders
        empty and the rest of the summary still composes. Knowledge is the right
        probe — it is the one Layer-0 metric that propagates a read failure
        rather than reporting zeros.
        """
        metrics.ku_service = None  # calculate_knowledge_metrics now returns Result.fail

        summary = await aggregation.aggregate_weekly_life_summary(USER, START_DATE, END_DATE)

        assert summary["layer_0_knowledge"]["substance_metrics"] == {}
        # The surviving layers are untouched.
        assert summary["total_activity_score"] == 23.8
        assert summary["layer_1_activities"]["tasks"]["total_count"] == 2


@pytest.mark.asyncio
class TestNoActivityClaimsNoDriver:
    """A week with nothing in it must not name a top substance driver.

    ``substance_drivers`` always carries all three keys, so ``max()`` never falls
    through to its ``default=(None, {})`` and always returned a domain — at a
    contribution of 0.0. The rendered advice was "Prioritize habits activities to
    make knowledge real" to a learner who logged nothing, and
    ``top_substance_driver`` said "habits", which the weekly summary text repeats.
    The "No significant activity detected" branch existed for exactly this state
    and was unreachable.

    Raised by Codex on #1032 (P2). It is a defect of this PR, not before it: until
    the Result fix the method raised and rendered nothing at all.
    """

    @staticmethod
    def _empty_layer1() -> dict[str, dict[str, Any]]:
        """The shape a zero-activity week produces — also the fail-soft shape."""
        return {
            domain: {} for domain in ("tasks", "habits", "goals", "events", "choices", "principles")
        }

    async def test_zero_activity_names_no_driver(self) -> None:
        service = AnalyticsAggregationService(metrics_service=AnalyticsMetricsService())

        correlation = service._correlate_knowledge_activities({}, self._empty_layer1())

        assert correlation["top_substance_driver"] == "none"
        assert correlation["insight"] == (
            "No significant activity detected for knowledge embodiment"
        )
        # No domain is named anywhere in the rendered line.
        for domain in ("habits", "tasks", "events"):
            assert domain not in correlation["insight"].lower()

    async def test_a_single_active_domain_still_names_it(self) -> None:
        """The guard keys on the total, not on "all three present" — one is enough."""
        layer1 = self._empty_layer1()
        layer1["events"] = {"total_count": 4}

        correlation = AnalyticsAggregationService(
            metrics_service=AnalyticsMetricsService()
        )._correlate_knowledge_activities({}, layer1)

        assert correlation["top_substance_driver"] == "events"
        assert "Events: 100%" in correlation["insight"]

    async def test_the_summary_text_does_not_repeat_a_phantom_driver(self) -> None:
        """``_generate_cross_layer_summary_text`` reads the same key straight through."""
        service = AnalyticsAggregationService(metrics_service=AnalyticsMetricsService())
        insights = service._synthesize_cross_layer_insights(
            layer1_domains=self._empty_layer1(),
            knowledge_metrics={},
            journal_metrics={},
            curriculum_metrics={},
        )

        text = service._generate_cross_layer_summary_text(
            [{"domain": "tasks", "activity_score": 0}], {}, {}, insights
        )

        assert "Top substance driver: none." in text


@pytest.mark.asyncio
class TestUpcomingEventsAgreeWithTheModel:
    """``upcoming`` must not double-count an event that is already completed.

    ``Event.is_upcoming()`` is "in the future and not completed", so without the
    status guard a future-dated COMPLETED event lands in both ``upcoming_count``
    and ``completed_count`` and analytics disagrees with the event views.

    Only the status half of ``is_upcoming()`` is borrowed: it delegates to
    ``is_past()``, which compares whole dates and calls an undated event not-past.
    These tests pin that divergence deliberately — the comparison here stays
    time-precise.

    Raised by Codex on #1032 (P2).
    """

    @staticmethod
    async def _event_metrics(events: list[Event]) -> dict[str, Any]:
        service = AnalyticsMetricsService(events_service=_StubDomainService(events))
        result = await service.calculate_event_metrics(USER, START_DATE, END_DATE)
        assert result.is_ok
        return result.value

    async def test_a_completed_future_event_is_not_upcoming(self) -> None:
        future = datetime.now() + timedelta(days=3)
        metrics = await self._event_metrics(
            [
                Event(
                    uid="e_done",
                    title="Ran early",
                    user_uid=USER,
                    event_date=future.date(),
                    start_time=future.time(),
                    duration_minutes=60,
                    status=EntityStatus.COMPLETED,
                )
            ]
        )

        assert metrics["completed_count"] == 1
        assert metrics["upcoming_count"] == 0

    async def test_an_open_future_event_still_counts(self) -> None:
        future = datetime.now() + timedelta(days=3)
        metrics = await self._event_metrics(
            [
                Event(
                    uid="e_open",
                    title="Study block",
                    user_uid=USER,
                    event_date=future.date(),
                    start_time=future.time(),
                    duration_minutes=60,
                )
            ]
        )

        assert metrics["upcoming_count"] == 1
        assert metrics["completed_count"] == 0

    async def test_earlier_today_is_not_upcoming(self) -> None:
        """The precision ``is_upcoming()`` would have cost: it compares whole dates."""
        earlier = datetime.now() - timedelta(hours=3)
        metrics = await self._event_metrics(
            [
                Event(
                    uid="e_past_today",
                    title="Morning standup",
                    user_uid=USER,
                    event_date=earlier.date(),
                    start_time=earlier.time(),
                    duration_minutes=15,
                )
            ]
        )

        assert metrics["upcoming_count"] == 0


def test_the_real_metrics_service_satisfies_the_protocol() -> None:
    """The seam is now typed, so the runtime and the annotation must agree.

    ``AnalyticsAggregationService.__init__`` typed its collaborator ``Any``, which
    erased the ``Result`` return of all fifteen ``calculate_*_metrics`` calls and
    is why the defect this file guards was invisible to mypy at every site. The
    protocol is ``runtime_checkable``, so this also catches a method being renamed
    out from under the annotation.

    Raised by Codex on #1032 (P1).
    """
    assert isinstance(AnalyticsMetricsService(), AnalyticsMetricsOperations)
