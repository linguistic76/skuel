"""
The hub's vector source on a real graph: a hit is a published Ku, never another user's row
=============================================================================================

Method 1 (``get_optimal_next_path_steps``) and the daily plan's learning slot both take
their candidates from ``learning_aware_search`` when the ZPD assessment has nothing, and
name every hit as a Ku. The search is of the ``Ku`` index (``LEARNING_STATE_LABELS``),
which the publication gate scopes — so what the hub can surface is measured here over a
real vector index, two users and three embedded nodes:

- user B's Task, embedded and owned (``:OWNS`` + ``user_uid``, as the create door writes);
- a published Ku — the positive control: the one thing the hub may offer user A;
- a Ku marked draft — in the Ku index, withheld by the publication gate.

The embeddings service answers every text with the same vector, so every embedded node is
a perfect match: whatever the index admits, the hub returns.

The same file measures the published-titles read the ZPD and context sources name their
steps by (``KuBackend.get_published_titles``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from core.config.unified_config import VectorSearchConfig
from core.models.enums.neo_labels import NeoLabel
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
from core.utils.result_simplified import Result
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USER_A = seed_user_uid("hls_reader")
USER_B = seed_user_uid("hls_other")
FOREIGN_TASK = "task.hls-foreign"
FOREIGN_TITLE = "hls B's private plan"
PUBLISHED_KU = "ku.hls.published"
PUBLISHED_TITLE = "hls published concept"
DRAFT_KU = "ku.hls.draft"
DRAFT_TITLE = "hls draft concept"
EMBEDDING = [0.001 * i for i in range(1, 1025)]  # what the embeddings mock answers


async def _seed(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (a:User {uid: $a}) SET a.username = $a, a.title = $a
            MERGE (b:User {uid: $b}) SET b.username = $b, b.title = $b
            MERGE (t:Entity:Task {uid: $task})
            SET t.title = $task_title, t.entity_type = 'task', t.user_uid = $b,
                t.status = 'active', t.embedding = $embedding
            MERGE (b)-[:OWNS]->(t)
            MERGE (k:Entity:Ku {uid: $published})
            SET k.title = $published_title, k.entity_type = 'ku', k.status = 'active',
                k.publication_state = 'published', k.embedding = $embedding
            MERGE (d:Entity:Ku {uid: $draft})
            SET d.title = $draft_title, d.entity_type = 'ku', d.status = 'active',
                d.publication_state = 'draft', d.embedding = $embedding
            """,
            a=USER_A,
            b=USER_B,
            task=FOREIGN_TASK,
            task_title=FOREIGN_TITLE,
            published=PUBLISHED_KU,
            published_title=PUBLISHED_TITLE,
            draft=DRAFT_KU,
            draft_title=DRAFT_TITLE,
            embedding=EMBEDDING,
        )


def _vector_search(driver: AsyncDriver, embeddings: Any) -> Neo4jVectorSearchService:
    return Neo4jVectorSearchService(
        backend=build_production_backends(driver)["vector_search_backend"],
        embeddings_service=embeddings,
        config=VectorSearchConfig(ku_min_score=0.0),
    )


def _hub(vector_search: Neo4jVectorSearchService) -> UserContextIntelligence:
    """The real hub for user A over the real vector search; every other read finds nothing."""

    # Not a spec'd mock: a spec reads the facade's signatures, and this one annotates
    # its constructor with a type imported for type-checking only. The read is
    # name-checked instead — the attribute access raises if the method is renamed.
    _ = ReportRelationshipService.get_pending_submissions
    report = MagicMock()
    report.get_pending_submissions = AsyncMock(return_value=Result.ok([]))

    def _empty(cls: type, *reads: str) -> MagicMock:
        facade = create_autospec(cls, instance=True)
        for name in reads:
            getattr(facade, name).return_value = Result.ok([])
        return facade

    ku = create_autospec(KuService, instance=True)
    ku.get_published_titles.return_value = Result.ok({})
    factory = UserContextIntelligenceFactory(
        tasks=_empty(TasksService, "get_actionable_tasks_for_user", "get_learning_tasks_for_user"),
        goals=_empty(GoalsService, "get_advancing_goals_for_user"),
        habits=_empty(HabitsService, "get_at_risk_habits_for_user"),
        events=_empty(EventsService, "get_upcoming_events_for_user"),
        choices=_empty(ChoicesService, "get_pending_decisions_for_user"),
        principles=_empty(PrinciplesService, "get_aligned_principles_for_user"),
        ku=ku,
        ps=_empty(
            PsService,
            "get_ready_to_learn_for_user",
            "find_habits_reinforcing_knowledge",
            "find_events_applying_knowledge",
        ),
        lp=MagicMock(),
        exercises=_empty(
            ExerciseService, "get_pending_revisions_for_user", "get_actionable_exercises_for_user"
        ),
        report=report,
        calendar=MagicMock(),
        vector_search_service=vector_search,
        zpd_service=None,
    )
    context = RichUserContext(user_uid=USER_A)
    context.available_minutes_daily = 480
    return factory.create(context)


async def test_the_index_admits_every_seeded_node_as_a_perfect_match(
    neo4j_driver: AsyncDriver, clean_neo4j: None, mock_embeddings_service: Any
) -> None:
    """The instrument: the whole-corpus index returns all three, so a node the hub
    does not return was withheld by the hub's own scoping, not by the vector."""
    await _seed(neo4j_driver)

    hits = await _vector_search(neo4j_driver, mock_embeddings_service).find_similar_by_text(
        label=NeoLabel.ENTITY.value, text="anything", limit=10
    )

    assert hits.is_ok, hits
    uids = {hit["node"]["uid"] for hit in hits.value}
    assert {FOREIGN_TASK, PUBLISHED_KU} <= uids
    assert DRAFT_KU not in uids  # the publication gate, at the vector chokepoint


async def test_method_one_offers_the_published_ku_and_never_another_user_s_task(
    neo4j_driver: AsyncDriver, clean_neo4j: None, mock_embeddings_service: Any
) -> None:
    await _seed(neo4j_driver)
    hub = _hub(_vector_search(neo4j_driver, mock_embeddings_service))

    result = await hub.get_optimal_next_path_steps(consider_capacity=False)

    assert result.is_ok, result
    assert [step.ku_uid for step in result.value] == [PUBLISHED_KU]
    assert [step.title for step in result.value] == [PUBLISHED_TITLE]
    rendered = " ".join(f"{step.ku_uid} {step.title}" for step in result.value)
    assert FOREIGN_TASK not in rendered and FOREIGN_TITLE not in rendered
    assert DRAFT_KU not in rendered and DRAFT_TITLE not in rendered


async def test_the_daily_plan_schedules_the_published_ku_and_never_another_user_s_task(
    neo4j_driver: AsyncDriver, clean_neo4j: None, mock_embeddings_service: Any
) -> None:
    await _seed(neo4j_driver)
    hub = _hub(_vector_search(neo4j_driver, mock_embeddings_service))

    result = await hub.get_ready_to_work_on_today()

    assert result.is_ok, result
    assert result.value.learning == (PUBLISHED_KU,)


async def test_the_published_titles_read_answers_the_published_ku_alone(
    neo4j_driver: AsyncDriver, clean_neo4j: None
) -> None:
    await _seed(neo4j_driver)
    backend = build_production_backends(neo4j_driver)["ku_backend"]

    titles = await KuService(backend=backend, graph_intel=MagicMock()).get_published_titles(
        [PUBLISHED_KU, DRAFT_KU, FOREIGN_TASK, "ku.hls.missing"]
    )

    assert titles.is_ok, titles
    assert titles.value == {PUBLISHED_KU: PUBLISHED_TITLE}
