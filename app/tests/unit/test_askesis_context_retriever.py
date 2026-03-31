"""
Tests for ContextRetriever — partial failure handling in LS bundle loading.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.askesis.context_retriever import ContextRetriever
from core.utils.result_simplified import Errors, Result


def _make_graph_intel(resource_records: list[dict[str, Any]] | None = None) -> MagicMock:
    """Build a mock graph_intelligence_service.

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
    """LS bundle loading should survive individual fetch failures."""

    @pytest.mark.anyio
    async def test_all_fetches_succeed(self) -> None:
        """Happy path: all fetches succeed, bundle is fully populated."""
        ku = _make_entity("ku_lesson_1", "Test KU")
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intelligence_service=_make_graph_intel(),
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
            graph_intelligence_service=_make_graph_intel(),
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
            graph_intelligence_service=_make_graph_intel(),
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
        """Every fetch crashes — bundle contains only the LS itself."""
        retriever = ContextRetriever(
            graph_intelligence_service=_make_graph_intel(),
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
        """No active LS in context → Result.fail(not_found)."""
        retriever = ContextRetriever(
            graph_intelligence_service=_make_graph_intel(),
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
            graph_intelligence_service=_make_graph_intel(),
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
            graph_intelligence_service=_make_graph_intel(),
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
            graph_intelligence_service=_make_graph_intel(),
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
