"""
Tests for ContextRetriever — partial failure handling in PS bundle loading.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.ps_content.content_chunks import ContentChunkType
from core.services.askesis.context_retriever import ContextRetriever
from core.utils.result_simplified import Errors, Result


def _make_graph_intel(resource_records: list[dict[str, Any]] | None = None) -> MagicMock:
    """Build a mock graph_intel.

    By default, execute_query returns empty results (no cited resources).
    """
    gi = MagicMock()
    gi.execute_query = AsyncMock(return_value=Result.ok(resource_records or []))
    return gi


def _make_user_context(
    active_ls_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a minimal mock UserContext with one active path step."""
    ctx = MagicMock()
    if active_ls_data is None:
        active_ls_data = {
            "entity": {
                "uid": "ps:test_1",
                "title": "Test Step",
                "current_mastery": 0.0,
                "mastery_threshold": 0.7,
                "knowledge_uids": ["ku_lesson_1"],
                "semantic_links": [],
                "intent": "Understand testing",
            },
            "graph_context": {
                "practice_habits": [{"uid": "habit_1"}],
                "practice_tasks": [{"uid": "task_1"}],
                "learning_path": {"uid": "lp:test"},
                "knowledge_relationships": [],
            },
        }
    ctx.active_path_steps_rich = [active_ls_data]
    return ctx


def _make_entity(uid: str, title: str) -> MagicMock:
    """Build a minimal mock entity."""
    entity = MagicMock()
    entity.uid = uid
    entity.title = title
    entity.content = f"Content for {title}"
    entity.learning_objectives = []
    entity.semantic_links = ()
    entity.knowledge_uids = []
    return entity


def _ok_service(entity: Any) -> MagicMock:
    """Service whose get() returns Result.ok(entity)."""
    svc = MagicMock()
    svc.get = AsyncMock(return_value=Result.ok(entity))
    return svc


def _failing_service(error_msg: str = "boom") -> MagicMock:
    """Service whose get() raises an exception."""
    svc = MagicMock()
    svc.get = AsyncMock(side_effect=RuntimeError(error_msg))
    return svc


def _not_found_service() -> MagicMock:
    """Service whose get() returns Result.fail (not_found)."""
    svc = MagicMock()
    svc.get = AsyncMock(return_value=Result.fail(Errors.not_found("entity", "test_uid")))
    return svc


class TestLoadLsBundlePartialFailure:
    """PS bundle loading should survive individual fetch failures."""

    @pytest.mark.anyio
    async def test_all_fetches_succeed(self) -> None:
        """Happy path: all fetches succeed, bundle is fully populated."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_ok_service(ku),
            ku_service=MagicMock(get=AsyncMock()),  # no KU UIDs to fetch
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.path_step.uid == "ps:test_1"
        assert len(bundle.related_steps) == 1
        assert bundle.learning_path is not None
        assert len(bundle.habits) == 1
        assert len(bundle.tasks) == 1

    @pytest.mark.anyio
    async def test_lesson_fetch_raises_bundle_still_built(self) -> None:
        """Lesson fetch crashes — bundle is built with empty lessons."""
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_failing_service("ps service down"),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.path_step.uid == "ps:test_1"
        assert len(bundle.related_steps) == 0  # Failed fetch → empty
        assert bundle.learning_path is not None  # LP succeeded
        assert len(bundle.habits) == 1

    @pytest.mark.anyio
    async def test_lp_fetch_raises_bundle_has_none_lp(self) -> None:
        """LP fetch crashes — bundle is built with learning_path=None."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_ok_service(ku),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_failing_service("lp service down"),
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.learning_path is None  # Failed → default
        assert len(bundle.related_steps) == 1
        assert len(bundle.habits) == 1

    @pytest.mark.anyio
    async def test_all_fetches_raise_minimal_bundle(self) -> None:
        """Every fetch crashes — bundle contains only the PS entity itself."""
        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_failing_service("lessons down"),
            ku_service=_failing_service("kus down"),
            habits_service=_failing_service("habits down"),
            tasks_service=_failing_service("tasks down"),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_failing_service("lp down"),
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.path_step.uid == "ps:test_1"
        assert len(bundle.related_steps) == 0
        assert len(bundle.kus) == 0
        assert bundle.learning_path is None
        assert len(bundle.habits) == 0
        assert len(bundle.tasks) == 0

    @pytest.mark.anyio
    async def test_no_active_ls_returns_not_found(self) -> None:
        """No active PS in context → Result.fail(not_found)."""
        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=MagicMock(),
            ku_service=MagicMock(),
            habits_service=MagicMock(),
            tasks_service=MagicMock(),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=MagicMock(),
        )

        ctx = MagicMock()
        ctx.active_path_steps_rich = []

        result = await retriever.load_ps_bundle("user_1", ctx)
        assert result.is_error

    @pytest.mark.anyio
    async def test_habits_fetch_raises_tasks_still_succeed(self) -> None:
        """Habits crash but tasks succeed — both are independent."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_ok_service(ku),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_failing_service("habits timeout"),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert len(bundle.habits) == 0  # Failed
        assert len(bundle.tasks) == 1  # Succeeded independently
        assert len(bundle.related_steps) == 1

    @pytest.mark.anyio
    async def test_resources_fetched_via_cites_resource(self) -> None:
        """Resources cited by lessons are included in the bundle."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        lp = _make_entity("lp:test", "Test LP")

        # lesson_backend returns a Resource record from get_cited_resources
        resource_record = {
            "resource": {
                "uid": "resource_book_1",
                "title": "Deep Work",
                "entity_type": "resource",
                "author": "Cal Newport",
                "media_type": "book",
            }
        }
        lesson_backend = MagicMock()
        lesson_backend.get_cited_resources = AsyncMock(return_value=Result.ok([resource_record]))

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_ok_service(ku),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=MagicMock(get=AsyncMock()),
            tasks_service=MagicMock(get=AsyncMock()),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
            ps_backend=lesson_backend,
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert len(bundle.resources) == 1
        assert bundle.resources[0].uid == "resource_book_1"
        assert bundle.resources[0].author == "Cal Newport"

    @pytest.mark.anyio
    async def test_resource_fetch_failure_does_not_break_bundle(self) -> None:
        """Resource fetch crash → bundle built with empty resources (no lesson_backend)."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=_ok_service(ku),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=MagicMock(get=AsyncMock()),
            tasks_service=MagicMock(get=AsyncMock()),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
            # No lesson_backend → resource fetch skipped gracefully
        )

        ctx = _make_user_context()
        result = await retriever.load_ps_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert len(bundle.resources) == 0  # Graceful degradation
        assert len(bundle.related_steps) == 1  # Other fetches unaffected


class TestRelationshipNameCitesResource:
    """CITES_RESOURCE exists in RelationshipName enum."""

    def test_cites_resource_enum_exists(self) -> None:
        from core.models.relationship_names import RelationshipName

        assert RelationshipName.CITES_RESOURCE == "CITES_RESOURCE"
        assert RelationshipName.is_valid("CITES_RESOURCE")


class TestIntentToChunkTypes:
    """Intent-aware chunk-type filtering for chunk retrieval.

    Expectations name ``ContentChunkType`` MEMBERS and compare against their
    ``.value``. Hand-writing the strings here is what let the live silent-zero
    bug pass review: the map emitted UPPERCASE member names, the test restated
    them, and both were wrong about the persisted (lowercase) spelling.
    """

    @pytest.mark.parametrize(
        "intent_name,expected",
        [
            ("PREREQUISITE", [ContentChunkType.DEFINITION, ContentChunkType.EXPLANATION]),
            ("PRACTICE", [ContentChunkType.EXERCISE, ContentChunkType.EXAMPLE]),
            ("HIERARCHICAL", [ContentChunkType.DEFINITION, ContentChunkType.EXPLANATION]),
            (
                "EXPLORATORY",
                [
                    ContentChunkType.INTRODUCTION,
                    ContentChunkType.SUMMARY,
                    ContentChunkType.DEFINITION,
                ],
            ),
            ("RELATIONSHIP", [ContentChunkType.EXPLANATION, ContentChunkType.DEFINITION]),
        ],
    )
    def test_mapped_intents_return_chunk_types(
        self, intent_name: str, expected: list[ContentChunkType]
    ) -> None:
        from core.models.query_types import QueryIntent
        from core.services.askesis.context_retriever import _intent_to_chunk_types

        assert _intent_to_chunk_types(QueryIntent[intent_name]) == [t.value for t in expected]

    @pytest.mark.parametrize(
        "intent_name",
        ["AGGREGATION", "SPECIFIC", "GOAL_ACHIEVEMENT"],
    )
    def test_unmapped_intents_return_none(self, intent_name: str) -> None:
        """Unmapped intents fall through to None (no chunk-type filter)."""
        from core.models.query_types import QueryIntent
        from core.services.askesis.context_retriever import _intent_to_chunk_types

        assert _intent_to_chunk_types(QueryIntent[intent_name]) is None


class TestFetchKusEdgeDerived:
    """_fetch_kus derives KUs from graph_context knowledge edges, never UID prefix.

    Both sanctioned KU UID forms (authored ``ku.{ns}.{slug}`` and generated
    ``ku_{slug}_{random}``) must pass through — entity kind comes from the
    MEGA-QUERY's entity_type field (ADR-013 never-sniff rule).
    """

    def _retriever(self, ku_service: Any) -> ContextRetriever:
        return ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=MagicMock(),
            ku_service=ku_service,
            habits_service=MagicMock(),
            tasks_service=MagicMock(),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=MagicMock(),
        )

    @pytest.mark.anyio
    async def test_fetches_ku_typed_entries_both_uid_forms(self) -> None:
        """ku-typed entries are fetched regardless of UID spelling."""
        fetched: list[str] = []

        async def _get(uid: str) -> Result[Any]:
            fetched.append(uid)
            return Result.ok(_make_entity(uid, f"KU {uid}"))

        ku_service = MagicMock(get_ku=AsyncMock(side_effect=_get))
        retriever = self._retriever(ku_service)

        graph_context = {
            "knowledge_relationships": [
                {"uid": "ku.mindfulness.breath", "entity_type": "ku", "rel_type": "USES_KU"},
                {"uid": "ku_functions_a1b2c3", "entity_type": "ku", "rel_type": "TRAINS_KU"},
                {
                    "uid": "ps.mindfulness.posture-basics",
                    "entity_type": "path_step",
                    "rel_type": "ENABLES_KNOWLEDGE",
                },
                # Prerequisite/enabled KU neighbors are context, NOT this
                # step's composed knowledge — must stay out of bundle.kus.
                {
                    "uid": "ku.mindfulness.prereq",
                    "entity_type": "ku",
                    "rel_type": "REQUIRES_KNOWLEDGE",
                },
            ]
        }

        kus = await retriever._fetch_kus(graph_context)

        assert sorted(fetched) == ["ku.mindfulness.breath", "ku_functions_a1b2c3"]
        assert len(kus) == 2

    @pytest.mark.anyio
    async def test_empty_and_malformed_entries_yield_no_kus(self) -> None:
        """No knowledge_relationships, or entries without uid/entity_type → []."""
        ku_service = MagicMock(get_ku=AsyncMock())
        retriever = self._retriever(ku_service)

        assert await retriever._fetch_kus({}) == []
        assert (
            await retriever._fetch_kus(
                {
                    "knowledge_relationships": [
                        {"uid": "ku.no.type", "rel_type": "USES_KU"},  # no entity_type
                        {"entity_type": "ku", "rel_type": "USES_KU"},  # no uid
                        {"uid": "ku.no.rel", "entity_type": "ku"},  # no rel_type
                        "not-a-dict",
                    ]
                }
            )
            == []
        )
        ku_service.get_ku.assert_not_called()

    @pytest.mark.anyio
    async def test_no_ku_service_returns_empty(self) -> None:
        retriever = self._retriever(None)
        assert (
            await retriever._fetch_kus(
                {
                    "knowledge_relationships": [
                        {"uid": "x", "entity_type": "ku", "rel_type": "USES_KU"}
                    ]
                }
            )
            == []
        )


class TestFetchRelatedPathStepsTypeFilter:
    """_fetch_related_path_steps takes only path_step-typed graph entries."""

    @pytest.mark.anyio
    async def test_ku_typed_entries_are_not_fetched_as_path_steps(self) -> None:
        fetched: list[str] = []

        async def _get(uid: str) -> Result[Any]:
            fetched.append(uid)
            return Result.ok(_make_entity(uid, f"PS {uid}"))

        ps_service = MagicMock(get=AsyncMock(side_effect=_get))
        retriever = ContextRetriever(
            graph_intel=_make_graph_intel(),
            embeddings_service=MagicMock(),
            ps_service=ps_service,
            ku_service=MagicMock(),
            habits_service=MagicMock(),
            tasks_service=MagicMock(),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=MagicMock(),
        )

        path_step = _make_entity("ps:test_1", "Primary")
        path_step.knowledge_uids = []
        graph_context = {
            "knowledge_relationships": [
                {"uid": "ku.mindfulness.breath", "entity_type": "ku"},
                {"uid": "ps.mindfulness.posture-basics", "entity_type": "path_step"},
            ]
        }

        steps = await retriever._fetch_related_path_steps(path_step, graph_context)

        assert fetched == ["ps.mindfulness.posture-basics"]
        assert len(steps) == 1


def _make_context_retriever_with_router(router: Any) -> ContextRetriever:
    """Build a minimal ContextRetriever with a post-wired search_router."""
    retriever = ContextRetriever(
        graph_intel=_make_graph_intel(),
        embeddings_service=MagicMock(),
        ps_service=MagicMock(),
        ku_service=MagicMock(),
        habits_service=MagicMock(),
        tasks_service=MagicMock(),
        events_service=MagicMock(),
        principles_service=MagicMock(),
        lp_service=MagicMock(),
    )
    retriever.search_router = router
    return retriever


class TestFindSimilarChunksRouting:
    """_find_similar_chunks routes through SearchRouter and preserves the mapping."""

    @pytest.mark.anyio
    async def test_maps_chunk_hits_to_askesis_dicts(self) -> None:
        """SemanticSearchChunkResult hits map to Askesis dicts (similarity_score→similarity)."""
        hits = [
            {
                "chunk_uid": "chunk_1",
                "chunk_type": ContentChunkType.DEFINITION.value,
                "text": "The body is the seat of awareness.",
                "context_window": "…context…",
                "similarity_score": 0.87,
                "parent_uid": "ku.body.awareness",
                "parent_title": "Body Awareness",
            }
        ]
        router = MagicMock()
        router.retrieve_scoped_chunks = AsyncMock(return_value=Result.ok(hits))
        retriever = _make_context_retriever_with_router(router)

        mapped = await retriever._find_similar_chunks("what is body awareness?", "user_1")

        assert len(mapped) == 1
        row = mapped[0]
        assert row["chunk_uid"] == "chunk_1"
        assert row["similarity"] == 0.87  # similarity_score → similarity
        assert row["parent_uid"] == "ku.body.awareness"
        assert row["parent_title"] == "Body Awareness"
        assert row["context_window"] == "…context…"

    @pytest.mark.anyio
    async def test_search_error_returns_empty(self) -> None:
        """A router error yields an empty list (fail-soft), not a raise."""
        router = MagicMock()
        router.retrieve_scoped_chunks = AsyncMock(
            return_value=Result.fail(Errors.database(operation="x", message="boom"))
        )
        retriever = _make_context_retriever_with_router(router)

        mapped = await retriever._find_similar_chunks("q", "user_1")

        assert mapped == []

    @pytest.mark.anyio
    async def test_scope_threads_nous_facet_into_request(self) -> None:
        """retrieve_relevant_context(scope=SearchRequest(nous=...)) reaches the router."""
        from core.models.query_types import QueryIntent
        from core.models.search_request import SearchRequest

        router = MagicMock()
        router.retrieve_scoped_chunks = AsyncMock(return_value=Result.ok([]))
        retriever = _make_context_retriever_with_router(router)

        ctx = MagicMock()
        ctx.user_uid = "user_1"
        ctx.prerequisites_needed = {}
        ctx.active_moc_uids = []
        ctx.overdue_task_uids = []
        ctx.at_risk_habits_or_empty = MagicMock(return_value=[])

        await retriever.retrieve_relevant_context(
            ctx, "what is the body?", QueryIntent.EXPLORATORY, scope=SearchRequest(nous="body")
        )

        router.retrieve_scoped_chunks.assert_awaited_once()
        sent_request = router.retrieve_scoped_chunks.await_args.args[0]
        assert sent_request.to_property_filters().get("nous") == "body"
        assert sent_request.query_text == "what is the body?"
        assert sent_request.limit == 5
