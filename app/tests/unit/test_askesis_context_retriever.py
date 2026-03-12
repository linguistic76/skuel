"""
Tests for ContextRetriever — partial failure handling in LS bundle loading.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.askesis.context_retriever import ContextRetriever
from core.utils.result_simplified import Errors, Result


def _make_user_context(
    active_ls_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a minimal mock UserContext with one active learning step."""
    ctx = MagicMock()
    if active_ls_data is None:
        active_ls_data = {
            "entity": {
                "uid": "ls:test_1",
                "title": "Test Step",
                "current_mastery": 0.0,
                "mastery_threshold": 0.7,
                "primary_knowledge_uids": ["a_article_1"],
                "supporting_knowledge_uids": [],
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
    ctx.active_learning_steps_rich = [active_ls_data]
    return ctx


def _make_entity(uid: str, title: str) -> MagicMock:
    """Build a minimal mock entity."""
    entity = MagicMock()
    entity.uid = uid
    entity.title = title
    entity.content = f"Content for {title}"
    entity.learning_objectives = []
    entity.semantic_links = ()
    entity.primary_knowledge_uids = []
    entity.supporting_knowledge_uids = []
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
        article = _make_entity("a_article_1", "Test Article")
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
            article_service=_ok_service(article),
            ku_service=MagicMock(get=AsyncMock()),  # no KU UIDs to fetch
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ls_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.learning_step.uid == "ls:test_1"
        assert len(bundle.articles) == 1
        assert bundle.learning_path is not None
        assert len(bundle.habits) == 1
        assert len(bundle.tasks) == 1

    @pytest.mark.anyio
    async def test_article_fetch_raises_bundle_still_built(self) -> None:
        """Article fetch crashes — bundle is built with empty articles."""
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
            article_service=_failing_service("article service down"),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ls_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.learning_step.uid == "ls:test_1"
        assert len(bundle.articles) == 0  # Failed fetch → empty
        assert bundle.learning_path is not None  # LP succeeded
        assert len(bundle.habits) == 1

    @pytest.mark.anyio
    async def test_lp_fetch_raises_bundle_has_none_lp(self) -> None:
        """LP fetch crashes — bundle is built with learning_path=None."""
        article = _make_entity("a_article_1", "Test Article")
        habit = _make_entity("habit_1", "Test Habit")
        task = _make_entity("task_1", "Test Task")

        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
            article_service=_ok_service(article),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_ok_service(habit),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_failing_service("lp service down"),
        )

        ctx = _make_user_context()
        result = await retriever.load_ls_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.learning_path is None  # Failed → default
        assert len(bundle.articles) == 1
        assert len(bundle.habits) == 1

    @pytest.mark.anyio
    async def test_all_fetches_raise_minimal_bundle(self) -> None:
        """Every fetch crashes — bundle contains only the LS itself."""
        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
            article_service=_failing_service("articles down"),
            ku_service=_failing_service("kus down"),
            habits_service=_failing_service("habits down"),
            tasks_service=_failing_service("tasks down"),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_failing_service("lp down"),
        )

        ctx = _make_user_context()
        result = await retriever.load_ls_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert bundle.learning_step.uid == "ls:test_1"
        assert len(bundle.articles) == 0
        assert len(bundle.kus) == 0
        assert bundle.learning_path is None
        assert len(bundle.habits) == 0
        assert len(bundle.tasks) == 0

    @pytest.mark.anyio
    async def test_no_active_ls_returns_not_found(self) -> None:
        """No active LS in context → Result.fail(not_found)."""
        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
        )

        ctx = MagicMock()
        ctx.active_learning_steps_rich = []

        result = await retriever.load_ls_bundle("user_1", ctx)
        assert result.is_error

    @pytest.mark.anyio
    async def test_habits_fetch_raises_tasks_still_succeed(self) -> None:
        """Habits crash but tasks succeed — both are independent."""
        article = _make_entity("a_article_1", "Test Article")
        task = _make_entity("task_1", "Test Task")
        lp = _make_entity("lp:test", "Test LP")

        retriever = ContextRetriever(
            graph_intelligence_service=MagicMock(),
            embeddings_service=MagicMock(),
            article_service=_ok_service(article),
            ku_service=MagicMock(get=AsyncMock()),
            habits_service=_failing_service("habits timeout"),
            tasks_service=_ok_service(task),
            events_service=MagicMock(),
            principles_service=MagicMock(),
            lp_service=_ok_service(lp),
        )

        ctx = _make_user_context()
        result = await retriever.load_ls_bundle("user_1", ctx)

        assert result.is_ok
        bundle = result.value
        assert len(bundle.habits) == 0  # Failed
        assert len(bundle.tasks) == 1  # Succeeded independently
        assert len(bundle.articles) == 1
