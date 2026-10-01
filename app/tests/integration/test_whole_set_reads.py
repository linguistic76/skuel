"""
Real-Neo4j guard for reads that mean "everything".
==================================================

``find_by``, ``get_user_entities`` and ``list_by_user`` each return a page of 100
unless the caller writes a limit. A service that counts, averages or lists "the
user's tasks" over such a page answers about a hundred of them.

Every test seeds ``SEEDED`` (> 100) nodes per domain for one user and asserts a
figure equal to ``SEEDED`` — a count, never which rows: the page a bare ``find_by``
returns is unordered, so no assertion here depends on row identity. A second user
owns a handful of rows of each kind, so a read that dropped its owner scope would
overshoot rather than pass.

See: core/services/whole_set_read.py
     tests/unit/services/test_whole_set_read.py (the cap warning, and the census
     of bare reads)
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
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
from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.choice.choice import Choice
from core.models.enums.learning_enums import SELCategory
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.exercises.exercise import Exercise
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.services.activity_domain_config import ACTIVITY_DOMAIN_CONFIGS
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.cross_domain import CrossDomainQueryService
from core.services.events.events_core_service import EventsCoreService
from core.services.events.events_intelligence_service import EventsIntelligenceService
from core.services.exercises.exercise_service import ExerciseService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_scheduling_service import GoalsSchedulingService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.services.principles.principles_core_service import PrinciplesCoreService
from core.services.principles.principles_intelligence_service import (
    PrinciplesIntelligenceService,
)
from core.services.ps.ps_adaptive_service import PsAdaptiveService
from core.services.relationships import UnifiedRelationshipService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

USER = "user_whole_set"
STRANGER = "user_whole_set_stranger"

SEEDED = 130  # past the 100-row page
SEEDED_COMPLETED_TASKS = 39  # 30% of SEEDED
STRANGER_ROWS = 5

GROUP = "group_whole_set"
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
    return CrossDomainQueryService(CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver)))


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
                        uid: $entity_type + '_' + $owner + '_' + toString(i),
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

    async def test_group_exercise_list(self, neo4j_driver, clean_neo4j):
        async with neo4j_driver.session() as session:
            await session.run(
                """
                UNWIND range(1, $count) AS i
                CREATE (:Entity:Exercise {
                    uid: 'exercise_whole_set_' + toString(i),
                    entity_type: 'exercise',
                    title: 'Exercise ' + toString(i),
                    status: 'active',
                    scope: 'assigned',
                    group_uid: $group,
                    created_at: $now,
                    updated_at: $now
                })
                """,
                count=SEEDED,
                group=GROUP,
                now=datetime.now(UTC).isoformat(),
            )
        backend = ExerciseBackend(
            neo4j_driver, NeoLabel.EXERCISE, Exercise, base_label=NeoLabel.ENTITY
        )

        result = await ExerciseService(backend=backend).list_group_exercises(GROUP)

        assert result.is_ok, result
        assert len(result.value) == SEEDED

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
        backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
        # No stored learner: the service falls back to its default intelligence.
        user_service = MagicMock()
        user_service.get_user = AsyncMock(return_value=Result.ok(None))
        adaptive = PsAdaptiveService(backend=backend, user_service=user_service)

        result = await adaptive.get_sel_journey(USER)

        assert result.is_ok, result
        assert result.value.category_progress[SEL_CATEGORY].total_steps == SEEDED
