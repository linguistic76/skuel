"""
Real-Neo4j guard for reads that mean "everything".
==================================================

``find_by``, ``get_user_entities``, ``list_by_user`` and ``list`` each return a page
of 100 unless the caller writes a limit. A service that counts, averages or lists
"the user's tasks" over such a page answers about a hundred of them, and a read
that means "all of them" under any fixed limit short of ``QueryLimit.MAXIMUM``
answers about that many.

A count test seeds more rows than the bound it guards — ``SEEDED`` (> 100) per
domain for one user, ``LARGE_SET`` (> 500) or ``INVOICES`` (> 1000) for the reads
with a larger page in reach — and asserts a figure equal to the seeded count: a
count, never which rows, since the page a bare ``find_by`` returns is unordered.
A second user owns a handful of rows of each kind, so a read that dropped its
owner scope would overshoot rather than pass.

See: core/services/whole_set_read.py
     tests/unit/services/test_whole_set_read.py (the cap warning, and the census
     of bare reads)
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.activity_backends import (
    ChoicesBackend,
    EventsBackend,
    GoalsBackend,
    HabitsBackend,
    PrinciplesBackend,
    TasksBackend,
)
from core.models.choice.choice import Choice
from core.models.enums.habit_enums import HabitCategory
from core.models.enums.learning_enums import SELCategory
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.principle_enums import AlignmentLevel
from core.models.event.event import Event
from core.models.finance.invoice import InvoicePure, InvoiceType
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.principle.principle_types import AlignmentAssessment
from core.models.task.task import Task
from core.services.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.cross_domain import CrossDomainQueryService
from core.services.events.events_core_service import EventsCoreService
from core.services.events.events_habit_integration_service import EventsHabitIntegrationService
from core.services.events.events_intelligence_service import EventsIntelligenceService
from core.services.events.events_learning_service import EventsLearningService
from core.services.finance.finance_invoice_service import FinanceInvoiceService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_scheduling_service import GoalsSchedulingService
from core.services.habits._orchestration_mixin import _OrchestrationMixin
from core.services.habits.habits_completion_service import HabitsCompletionService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.services.habits.habits_scheduling_service import HabitsSchedulingService
from core.services.habits.habits_search_service import HabitsSearchService
from core.services.principles._embodiment_mixin import _EmbodimentMixin
from core.services.principles.principles_alignment_service import PrinciplesAlignmentService
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles.principles_intelligence_service import (
    PrinciplesIntelligenceService,
)
from core.services.ps.ps_adaptive_service import PsAdaptiveService
from core.services.relationships import UnifiedRelationshipService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.services.user import UserContext
from core.services.user.intelligence.perception_intelligence import PerceptionIntelligenceMixin
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService

USER = seed_user_uid("whole_set")
STRANGER = seed_user_uid("whole_set_stranger")
# The middle segment of each owner's seeded uids: ``{entity_type}.{tag}-{i}``.
TAGS: dict[str, str] = {USER: "whole-set", STRANGER: "whole-set-stranger"}


def _seeded_uid(entity_type: str, owner: str, i: int) -> str:
    return f"{entity_type}.{TAGS[owner]}-{i}"


SEEDED = 130  # past the 100-row page
SEEDED_COMPLETED_TASKS = 39  # 30% of SEEDED
STRANGER_ROWS = 5

SEL_CATEGORY = SELCategory.SELF_AWARENESS

type ActivityBackend = (
    TasksBackend | GoalsBackend | HabitsBackend | EventsBackend | ChoicesBackend | PrinciplesBackend
)
type ActivityCore = (
    TasksCoreService
    | GoalsCoreService
    | HabitsCoreService
    | EventsCoreService
    | ChoicesCoreService
    | PrinciplesCoreService
)
type ActivityModel = Task | Goal | Habit | Event | Choice | Principle


@dataclass(frozen=True)
class OwnedDomain:
    """One Activity domain's label, classes, and the name of its core's owner read."""

    label: NeoLabel
    entity_type: str
    backend_class: type[ActivityBackend]
    model: type[ActivityModel]
    core_class: type[ActivityCore]
    owner_read: str


ACTIVITY_DOMAINS: dict[str, OwnedDomain] = {
    "tasks": OwnedDomain(
        NeoLabel.TASK, "task", TasksBackend, Task, TasksCoreService, "get_user_tasks"
    ),
    "goals": OwnedDomain(
        NeoLabel.GOAL, "goal", GoalsBackend, Goal, GoalsCoreService, "get_user_goals"
    ),
    "habits": OwnedDomain(
        NeoLabel.HABIT, "habit", HabitsBackend, Habit, HabitsCoreService, "get_user_habits"
    ),
    "events": OwnedDomain(
        NeoLabel.EVENT, "event", EventsBackend, Event, EventsCoreService, "get_user_events"
    ),
    "choices": OwnedDomain(
        NeoLabel.CHOICE, "choice", ChoicesBackend, Choice, ChoicesCoreService, "get_user_choices"
    ),
    "principles": OwnedDomain(
        NeoLabel.PRINCIPLE,
        "principle",
        PrinciplesBackend,
        Principle,
        PrinciplesCoreService,
        "get_user_principles",
    ),
}
DOMAIN_NAMES = sorted(ACTIVITY_DOMAINS)


def _backend(neo4j_driver: AsyncDriver, domain: str) -> ActivityBackend:
    spec = ACTIVITY_DOMAINS[domain]
    return spec.backend_class(neo4j_driver, spec.label, spec.model, base_label=NeoLabel.ENTITY)


def _core(neo4j_driver: AsyncDriver, domain: str) -> ActivityCore:
    return ACTIVITY_DOMAINS[domain].core_class(backend=_backend(neo4j_driver, domain))


def _relationships(
    backend: ActivityBackend, domain: str
) -> UnifiedRelationshipService[Any, Any, Any]:
    return UnifiedRelationshipService(
        backend=backend, config=ACTIVITY_DOMAIN_CONFIGS[domain].relationship_config
    )


def _cross_domain(neo4j_driver: AsyncDriver) -> CrossDomainQueryService:
    return CrossDomainQueryService(build_production_backends(neo4j_driver)["cross_domain_backend"])


@pytest_asyncio.fixture
async def seeded(neo4j_driver, clean_neo4j):
    """SEEDED nodes of each Activity kind for USER, STRANGER_ROWS for STRANGER."""
    now = datetime.now(UTC)
    async with neo4j_driver.session() as session:
        await session.run("MERGE (:User {uid: $u})", u=USER)
        await session.run("MERGE (:User {uid: $u})", u=STRANGER)
        for spec in ACTIVITY_DOMAINS.values():
            for owner, count in ((USER, SEEDED), (STRANGER, STRANGER_ROWS)):
                await session.run(
                    f"""
                    MATCH (u:User {{uid: $owner}})
                    UNWIND range(1, $count) AS i
                    CREATE (n:Entity:{spec.label} {{
                        uid: $entity_type + '.' + $tag + '-' + toString(i),
                        user_uid: $owner,
                        entity_type: $entity_type,
                        title: $entity_type + ' ' + toString(i),
                        status: CASE
                            WHEN $entity_type = 'task' AND i <= $completed THEN 'completed'
                            ELSE 'active'
                        END,
                        created_at: $now,
                        updated_at: $now
                    }})
                    CREATE (u)-[:OWNS]->(n)
                    """,
                    owner=owner,
                    tag=TAGS[owner],
                    count=count,
                    entity_type=spec.entity_type,
                    completed=SEEDED_COMPLETED_TASKS,
                    now=now.isoformat(),
                )
        # An event's analytics window is cut on its calendar day, in the zone the
        # service reads today in.
        await session.run(
            "MATCH (e:Event) SET e.event_date = date($today)",
            today=today_in(current_zone()).isoformat(),
        )


@pytest.mark.asyncio
class TestOwnerReadsReturnEveryRow:
    """The three owner reads of each Activity domain return the user's whole set."""

    @pytest.mark.parametrize("domain", DOMAIN_NAMES)
    async def test_get_all_for_user(self, neo4j_driver, seeded, domain):
        result = await _core(neo4j_driver, domain).get_all_for_user(USER)

        assert result.is_ok, result
        assert len(result.value) == SEEDED

    @pytest.mark.parametrize("domain", DOMAIN_NAMES)
    async def test_core_owner_list(self, neo4j_driver, seeded, domain):
        owner_read = getattr(_core(neo4j_driver, domain), ACTIVITY_DOMAINS[domain].owner_read)

        result = await owner_read(USER)

        assert result.is_ok, result
        assert len(result.value) == SEEDED

    @pytest.mark.parametrize("domain", DOMAIN_NAMES)
    async def test_backend_owner_list(self, neo4j_driver, seeded, domain):
        owner_read = getattr(_backend(neo4j_driver, domain), ACTIVITY_DOMAINS[domain].owner_read)

        result = await owner_read(USER)

        assert result.is_ok, result
        assert len(result.value) == SEEDED

    async def test_an_owner_list_cut_by_its_limit_is_logged(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "tasks")
        backend.logger = Mock()

        result = await backend.list_by_user(USER, limit=5)

        assert result.is_ok, result
        assert len(result.value) == 5
        backend.logger.warning.assert_called_once()
        assert backend.logger.warning.call_args.args[1:3] == (5, SEEDED)

    async def test_a_whole_owner_list_is_not_logged(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "tasks")
        backend.logger = Mock()

        result = await backend.list_by_user(USER, limit=SEEDED)

        assert result.is_ok, result
        assert len(result.value) == SEEDED
        backend.logger.warning.assert_not_called()


@pytest.mark.asyncio
class TestFiguresCountEveryRow:
    """A figure computed from the user's set is computed from all of it."""

    async def test_task_list_stats(self, services, seeded):
        result = await services.tasks.get_filtered_context(USER, status_filter="all")

        assert result.is_ok, result
        stats = result.value["stats"]
        assert stats["total"] == SEEDED
        assert stats["completed"] == SEEDED_COMPLETED_TASKS

    async def test_task_performance_analytics(self, neo4j_driver, seeded):
        intelligence = TasksIntelligenceService(backend=_backend(neo4j_driver, "tasks"))

        result = await intelligence.get_performance_analytics(USER, period_days=30)

        assert result.is_ok, result
        metrics = result.value["metrics"]
        assert metrics["total_tasks"] == SEEDED
        assert metrics["completed_tasks"] == SEEDED_COMPLETED_TASKS
        assert metrics["completion_rate"] == 30.0

    async def test_task_trend_counts_completed_tasks(self, neo4j_driver, seeded):
        """The trend's rate is the metrics' rate: both count COMPLETED tasks."""
        intelligence = TasksIntelligenceService(backend=_backend(neo4j_driver, "tasks"))

        result = await intelligence.get_performance_analytics(USER, period_days=30)

        assert result.is_ok, result
        trends = result.value["trends"]
        assert trends["tasks_analyzed"] == SEEDED
        assert trends["completion_rate"] == 30.0

    async def test_goal_load_by_timeframe(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "goals")
        scheduling = GoalsSchedulingService(backend=backend, core=GoalsCoreService(backend=backend))

        result = await scheduling.get_goal_load_by_timeframe(USER)

        assert result.is_ok, result
        assert result.value["active_goal_count"] == SEEDED

    async def test_habit_performance_analytics(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "habits")
        intelligence = HabitsIntelligenceService(
            backend=backend,
            relationship_service=_relationships(backend, "habits"),
            cross_domain_query=_cross_domain(neo4j_driver),
        )

        result = await intelligence.get_performance_analytics(USER)

        assert result.is_ok, result
        assert result.value["total_habits"] == SEEDED

    async def test_event_performance_analytics(self, neo4j_driver, seeded):
        intelligence = EventsIntelligenceService(backend=_backend(neo4j_driver, "events"))

        result = await intelligence.get_performance_analytics(USER, period_days=30)

        assert result.is_ok, result
        assert result.value["total_events"] == SEEDED

    async def test_choice_performance_analytics(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "choices")
        intelligence = ChoicesIntelligenceService(
            backend=backend,
            cross_domain_query=_cross_domain(neo4j_driver),
            relationship_service=_relationships(backend, "choices"),
        )

        result = await intelligence.get_performance_analytics(USER)

        assert result.is_ok, result
        assert result.value["total_choices"] == SEEDED

    async def test_principle_performance_analytics(self, neo4j_driver, seeded):
        backend = _backend(neo4j_driver, "principles")
        intelligence = PrinciplesIntelligenceService(
            backend=backend, relationship_service=_relationships(backend, "principles")
        )

        result = await intelligence.get_performance_analytics(USER)

        assert result.is_ok, result
        assert result.value["total_principles"] == SEEDED


@pytest.mark.asyncio
class TestCurriculumSetsAreWhole:
    """A corpus read scoped by a filter returns every node the filter matches."""

    async def test_sel_category_step_total(self, neo4j_driver, clean_neo4j):
        """The category's ``total_steps`` is the progress denominator."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                UNWIND range(1, $count) AS i
                CREATE (:Entity:PathStep {
                    uid: 'ps.whole-set.step-' + toString(i),
                    entity_type: 'path_step',
                    title: 'Step ' + toString(i),
                    status: 'active',
                    sel_category: $category,
                    created_at: $now,
                    updated_at: $now
                })
                """,
                count=SEEDED,
                category=SEL_CATEGORY.value,
                now=datetime.now(UTC).isoformat(),
            )
        backend = build_production_backends(neo4j_driver)["ps_backend"]
        # No stored learner: the service falls back to its default intelligence.
        user_service = MagicMock()
        user_service.get_user = AsyncMock(return_value=Result.ok(None))
        adaptive = PsAdaptiveService(backend=backend, user_service=user_service)

        result = await adaptive.get_sel_journey(USER)

        assert result.is_ok, result
        assert result.value.category_progress[SEL_CATEGORY].total_steps == SEEDED


# ============================================================================
# Whole-set reads whose question is about everything the user has
# ============================================================================


class _HabitsOrchestration(_OrchestrationMixin):
    """The habit facade's orchestration methods, over a real backend."""

    def __init__(self, backend: HabitsBackend) -> None:
        self.backend = backend
        self.relationships = _relationships(backend, "habits")
        self.logger = Mock()


class _PrincipleEmbodiment(_EmbodimentMixin):
    """The principle facade's portfolio read, over a real backend."""

    def __init__(self, backend: PrinciplesBackend) -> None:
        self.backend = backend
        self.logger = Mock()


class _Perception(PerceptionIntelligenceMixin):
    """The hub's perception synthesis over real Goal / Habit / Principle backends."""

    def __init__(self, neo4j_driver: AsyncDriver) -> None:
        self.context = RichUserContext(user_uid=USER)
        self.goals = cast("GoalsService", SimpleNamespace(backend=_backend(neo4j_driver, "goals")))
        self.habits = cast(
            "HabitsService", SimpleNamespace(backend=_backend(neo4j_driver, "habits"))
        )
        self.principles = cast(
            "PrinciplesService", SimpleNamespace(backend=_backend(neo4j_driver, "principles"))
        )


def _scheduling(neo4j_driver: AsyncDriver) -> HabitsSchedulingService:
    backend = _backend(neo4j_driver, "habits")
    return HabitsSchedulingService(backend=backend, core=HabitsCoreService(backend=backend))


async def _set_on_users_nodes(
    neo4j_driver: AsyncDriver, label: NeoLabel, assignments: str, **params: Any
) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            f"MATCH (n:{label} {{user_uid: $user}}) SET {assignments}", user=USER, **params
        )


async def _copy_property_from(
    neo4j_driver: AsyncDriver, label: NeoLabel, source_uid: str, prop: str
) -> None:
    """Give every USER node of ``label`` the property one door-written node holds."""
    async with neo4j_driver.session() as session:
        await session.run(
            f"""
            MATCH (src:{label} {{uid: $src}})
            MATCH (n:{label} {{user_uid: $user}})
            SET n.{prop} = src.{prop}
            """,
            src=source_uid,
            user=USER,
        )


@pytest.mark.asyncio
class TestWrittenCapsReadEveryRow:
    """Each figure is computed over every row of the user's set."""

    async def test_habit_capacity(self, neo4j_driver, seeded):
        result = await _scheduling(neo4j_driver).check_habit_capacity(USER)

        assert result.is_ok, result
        assert result.value["current_habit_count"] == SEEDED

    async def test_habit_load_by_day(self, neo4j_driver, seeded):
        result = await _scheduling(neo4j_driver).get_habit_load_by_day(USER)

        assert result.is_ok, result
        assert result.value["active_habit_count"] == SEEDED

    async def test_habit_frequency_suggestion(self, neo4j_driver, seeded):
        await _set_on_users_nodes(
            neo4j_driver,
            NeoLabel.HABIT,
            "n.habit_category = $category",
            category=HabitCategory.HEALTH.value,
        )

        result = await _scheduling(neo4j_driver).suggest_habit_frequency(USER, HabitCategory.HEALTH)

        assert result.is_ok, result
        assert result.value["category_habits_count"] == SEEDED

    async def test_habit_stacking_ranks_every_established_habit(self, neo4j_driver, seeded):
        """The answer is a top five; the log line counts what was ranked."""
        await _set_on_users_nodes(neo4j_driver, NeoLabel.HABIT, "n.current_streak = 7")
        scheduling = _scheduling(neo4j_driver)
        scheduling.logger = Mock()

        result = await scheduling.suggest_habit_stacking(USER)

        assert result.is_ok, result
        assert len(result.value) == 5
        ranked = [
            call.args[0]
            for call in scheduling.logger.info.call_args_list
            if "habit stacking options" in str(call.args[0])
        ]
        assert ranked == [f"Found {SEEDED} habit stacking options for user {USER}"]

    async def test_skills_developed_by_habits(self, neo4j_driver, seeded):
        result = await _HabitsOrchestration(
            _backend(neo4j_driver, "habits")
        ).get_skills_developed_by_habits(USER)

        assert result.is_ok, result
        assert result.value["habit_count"] == SEEDED

    async def test_habit_badge_progress(self, neo4j_driver, seeded):
        await _set_on_users_nodes(neo4j_driver, NeoLabel.HABIT, "n.total_completions = 1")
        completions = build_production_backends(neo4j_driver)["habit_completions_backend"]
        service = HabitsCompletionService(
            habits_backend=_backend(neo4j_driver, "habits"), completions_backend=completions
        )

        result = await service.get_badge_progress(USER)

        assert result.is_ok, result
        assert result.value["completions"]["total_completions"] == SEEDED

    async def test_principle_average_alignment(self, neo4j_driver, seeded):
        """30 principles read ALIGNED, 100 DRIFTING: no 100 of them average like all 130."""
        backend = _backend(neo4j_driver, "principles")
        aligned_uids = [_seeded_uid("principle", USER, i) for i in range(1, 31)]
        for uid, level in (
            (aligned_uids[0], AlignmentLevel.ALIGNED),
            (_seeded_uid("principle", USER, 31), AlignmentLevel.DRIFTING),
        ):
            record = AlignmentAssessment(
                assessed_date=today_in(current_zone()), alignment_level=level, evidence="seen"
            ).to_record()
            written = await backend.update(uid, {"alignment_history": [record]})
            assert written.is_ok, written
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (aligned:Principle {uid: $aligned}), (drifting:Principle {uid: $drifting})
                MATCH (p:Principle {user_uid: $user})
                SET p.alignment_history = CASE
                    WHEN p.uid IN $aligned_uids THEN aligned.alignment_history
                    ELSE drifting.alignment_history
                END
                """,
                aligned=aligned_uids[0],
                drifting=_seeded_uid("principle", USER, 31),
                aligned_uids=aligned_uids,
                user=USER,
            )
        service = PrinciplesAlignmentService(
            backend=backend, cross_domain_query=_cross_domain(neo4j_driver)
        )

        result = await service.calculate_average_alignment(USER)

        assert result.is_ok, result
        expected = (
            30 * AlignmentLevel.ALIGNED.to_score() + 100 * AlignmentLevel.DRIFTING.to_score()
        ) / SEEDED
        assert result.value == pytest.approx(expected)

    async def test_cross_domain_perception(self, neo4j_driver, seeded):
        for domain, label in (
            ("goals", NeoLabel.GOAL),
            ("habits", NeoLabel.HABIT),
            ("principles", NeoLabel.PRINCIPLE),
        ):
            source = _seeded_uid(ACTIVITY_DOMAINS[domain].entity_type, USER, 1)
            appended = await _backend(neo4j_driver, domain).atomic_append_dual_track_checkin(
                source,
                {"gap_direction": "user_higher", "perception_gap": 0.25},
                history_limit=10,
            )
            assert appended.is_ok, appended
            await _copy_property_from(neo4j_driver, label, source, "dual_track_checkins")

        result = await _Perception(neo4j_driver).get_cross_domain_perception_analysis()

        assert result.is_ok, result
        for domain in ("goals", "habits", "principles"):
            assert result.value["per_domain"][domain]["assessed_count"] == SEEDED

    async def test_principle_portfolio(self, neo4j_driver, seeded):
        result = await _PrincipleEmbodiment(
            _backend(neo4j_driver, "principles")
        ).get_user_principle_portfolio(USER)

        assert result.is_ok, result
        assert result.value["count"] == SEEDED


@pytest.mark.asyncio
class TestHabitsNeedingAttentionAreTheOwners:
    """``get_needing_attention`` reads one user's whole set — never another user's."""

    async def test_every_habit_of_the_owner_and_none_of_the_strangers(self, neo4j_driver, seeded):
        search = HabitsSearchService(backend=_backend(neo4j_driver, "habits"))

        result = await search.get_needing_attention(USER, limit=SEEDED + STRANGER_ROWS + 1)

        assert result.is_ok, result
        assert {habit.user_uid for habit in result.value} == {USER}
        assert len(result.value) == SEEDED

    async def test_the_stranger_reads_their_own(self, neo4j_driver, seeded):
        search = HabitsSearchService(backend=_backend(neo4j_driver, "habits"))

        result = await search.get_needing_attention(STRANGER)

        assert result.is_ok, result
        assert {habit.user_uid for habit in result.value} == {STRANGER}
        assert len(result.value) == STRANGER_ROWS


@pytest.mark.asyncio
class TestEventWindowsAreWhole:
    """The event reads through ``list(filters=…)`` read every event in the window."""

    @pytest_asyncio.fixture
    async def habit_events(self, neo4j_driver, seeded):
        """Every USER event is scheduled today, a retention check, and reinforces its own habit.

        ``event_date`` is the ISO string the create door's mapper writes — the window
        filters compare it as stored.
        """
        await _set_on_users_nodes(
            neo4j_driver,
            NeoLabel.EVENT,
            "n.status = 'scheduled', n.knowledge_retention_check = true, n.event_date = $today",
            today=today_in(current_zone()).isoformat(),
        )
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (e:Event {user_uid: $user})
                MATCH (h:Habit {uid: replace(e.uid, 'event.', 'habit.')})
                CREATE (e)-[:REINFORCES_HABIT]->(h)
                """,
                user=USER,
            )

    def _habit_integration(self, neo4j_driver: AsyncDriver) -> EventsHabitIntegrationService:
        backend = _backend(neo4j_driver, "events")
        return EventsHabitIntegrationService(backend=backend, core=EventsCoreService(backend))

    async def test_learning_events(self, neo4j_driver, habit_events):
        service = EventsLearningService(backend=_backend(neo4j_driver, "events"))

        result = await service.get_learning_events(USER, days_ahead=7)

        assert result.is_ok, result
        assert len(result.value) == SEEDED

    async def test_upcoming_event_analysis(self, neo4j_driver, habit_events):
        intelligence = EventsIntelligenceService(
            backend=_backend(neo4j_driver, "events"),
            cross_domain_query=_cross_domain(neo4j_driver),
        )

        result = await intelligence.analyze_upcoming_events(USER, days_ahead=7)

        assert result.is_ok, result
        assert result.value["total_upcoming_events"] == SEEDED

    async def test_habit_reinforcement_events(self, neo4j_driver, habit_events):
        result = await self._habit_integration(neo4j_driver).get_habit_reinforcement_events(
            UserContext(user_uid=USER)
        )

        assert result.is_ok, result
        assert sum(len(events) for events in result.value.values()) == SEEDED

    async def test_at_risk_habit_events(self, neo4j_driver, habit_events):
        result = await self._habit_integration(neo4j_driver).get_at_risk_habit_events(
            UserContext(user_uid=USER)
        )

        assert result.is_ok, result
        assert len(result.value) == SEEDED

    async def test_next_habit_events(self, neo4j_driver, habit_events):
        result = await self._habit_integration(neo4j_driver).get_next_habit_events(
            UserContext(user_uid=USER)
        )

        assert result.is_ok, result
        assert len(result.value) == SEEDED


# ============================================================================
# Whole sets past 500 and 1000 rows
# ============================================================================

LARGE_SET = 510  # past the 500-row caps
INVOICES = 1001  # past the 1000-row cap


async def _seed_due_habits(neo4j_driver: AsyncDriver) -> None:
    """LARGE_SET never-completed daily habits for USER, STRANGER_ROWS for STRANGER."""
    now = datetime.now(UTC).isoformat()
    async with neo4j_driver.session() as session:
        for owner, count in ((USER, LARGE_SET), (STRANGER, STRANGER_ROWS)):
            await session.run(
                """
                MERGE (u:User {uid: $owner})
                WITH u
                UNWIND range(1, $count) AS i
                CREATE (h:Entity:Habit {
                    uid: 'habit.' + $tag + '-due-' + toString(i),
                    user_uid: $owner,
                    entity_type: 'habit',
                    title: 'habit ' + toString(i),
                    status: 'active',
                    recurrence_pattern: 'daily',
                    created_at: $now,
                    updated_at: $now
                })
                CREATE (u)-[:OWNS]->(h)
                """,
                owner=owner,
                tag=TAGS[owner],
                count=count,
                now=now,
            )


async def _seed_curriculum(neo4j_driver: AsyncDriver, label: NeoLabel, entity_type: str) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            f"""
            UNWIND range(1, $count) AS i
            CREATE (:Entity:{label} {{
                uid: $prefix + '.whole-set.n-' + toString(i),
                entity_type: $entity_type,
                title: $entity_type + ' ' + toString(i),
                status: 'active',
                tags: ['whole-set'],
                created_at: $now,
                updated_at: $now
            }})
            """,
            count=LARGE_SET,
            prefix="ps" if label == NeoLabel.PATH_STEP else "lp",
            entity_type=entity_type,
            now=datetime.now(UTC).isoformat(),
        )


@pytest.mark.asyncio
class TestLargeCapsReadEveryRow:
    async def test_habits_due_today(self, neo4j_driver, clean_neo4j):
        await _seed_due_habits(neo4j_driver)
        search = HabitsSearchService(backend=_backend(neo4j_driver, "habits"))

        result = await search.get_user_due_today(USER)

        assert result.is_ok, result
        assert {habit.user_uid for habit in result.value} == {USER}
        assert len(result.value) == LARGE_SET

    async def test_habits_due_today_for_every_user(self, neo4j_driver, clean_neo4j):
        await _seed_due_habits(neo4j_driver)
        search = HabitsSearchService(backend=_backend(neo4j_driver, "habits"))

        result = await search.get_all_due_today()

        assert result.is_ok, result
        assert len(result.value) == LARGE_SET + STRANGER_ROWS

    async def test_path_step_list_stats(self, services, clean_neo4j):
        await _seed_curriculum(services.ps.repo.driver, NeoLabel.PATH_STEP, "path_step")

        result = await services.ps.get_filtered_context(USER)

        assert result.is_ok, result
        assert result.value["stats"]["total"] == LARGE_SET

    async def test_path_step_tags(self, services, clean_neo4j):
        await _seed_curriculum(services.ps.repo.driver, NeoLabel.PATH_STEP, "path_step")

        result = await services.ps.list_step_tags()

        assert result.is_ok, result
        assert result.value == [{"tag": "whole-set", "count": LARGE_SET}]

    async def test_learning_path_list_stats(self, services, clean_neo4j):
        await _seed_curriculum(services.ps.repo.driver, NeoLabel.LEARNING_PATH, "learning_path")

        result = await services.lp.get_filtered_context(USER)

        assert result.is_ok, result
        assert result.value["stats"]["total"] == LARGE_SET

    async def test_invoice_stats(self, neo4j_driver, clean_neo4j):
        backend = build_production_backends(neo4j_driver)["invoice_backend"]
        created = await backend.create(
            InvoicePure(
                uid="invoice.whole-set",
                user_uid=USER,
                invoice_type=InvoiceType.OUTGOING,
                counterparty="Counterparty",
                invoice_date=today_in(current_zone()),
            )
        )
        assert created.is_ok, created
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (src:Invoice {uid: 'invoice.whole-set'})
                UNWIND range(2, $count) AS i
                CREATE (n:Invoice)
                SET n = properties(src), n.uid = src.uid + '-' + toString(i)
                """,
                count=INVOICES,
            )
        service = FinanceInvoiceService(backend=backend, renderer=Mock())

        result = await service.get_invoice_stats()

        assert result.is_ok, result
        assert result.value["total_count"] == INVOICES
