"""
Route tests for the entity picker.

Covers GET /api/picker/search:
- Auth required (raises when no session user)
- Empty q → list_recent_for_user with the 10-item default
- Non-empty q → search_for_user with the query
- exclude_uid → propagates to the search service's exclude set
- exclude_descendants_of → calls backend.get_descendant_uids and unions the result
- Unknown type → returns a disabled "Unsupported" option, no service call
- Service error → returns a disabled "Search failed" option

No Neo4j required: services are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml
from starlette.exceptions import HTTPException

from core.utils.result_simplified import Errors, Result


def _make_request(user_uid: str | None = "user_mike") -> Any:
    """Build a minimal request-like object the auth helper accepts."""
    session = {"user_uid": user_uid} if user_uid is not None else {}
    return SimpleNamespace(
        session=session,
        url=SimpleNamespace(path="/api/picker/search"),
        query_params={},
    )


def _make_entity(uid: str, title: str) -> Any:
    e = MagicMock()
    e.uid = uid
    e.title = title
    return e


@pytest.fixture
def mock_services() -> Any:
    """All six activity-domain facades, each with a `.search` sub-service."""
    services = MagicMock()

    for facade_name in ("tasks", "goals", "habits", "events", "choices", "principles"):
        facade = MagicMock()
        facade.search = MagicMock()
        facade.search.list_recent_for_user = AsyncMock(return_value=Result.ok([]))
        facade.search.search_for_user = AsyncMock(return_value=Result.ok([]))
        facade.search.backend = MagicMock()
        facade.search.backend.get_descendant_uids = AsyncMock(return_value=Result.ok(set()))
        setattr(services, facade_name, facade)

    return services


@pytest.fixture
def handler(mock_services: Any) -> Any:
    """Register the picker route and return the handler callable."""
    from adapters.inbound.picker_routes import create_picker_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_picker_routes(MagicMock(), rt_collector, mock_services)
    return registered["/api/picker/search"]


def render(fragment: Any) -> str:
    return to_xml(fragment)


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_raises(self, handler: Any) -> None:
        with pytest.raises(HTTPException):
            await handler(_make_request(user_uid=None), type="goal", q="")


class TestEmptyQuery:
    @pytest.mark.asyncio
    async def test_dispatches_to_list_recent(self, handler: Any, mock_services: Any) -> None:
        await handler(_make_request(), type="goal", q="")
        mock_services.goals.search.list_recent_for_user.assert_awaited_once()
        kwargs = mock_services.goals.search.list_recent_for_user.await_args.kwargs
        assert kwargs.get("user_uid") == "user_mike"
        assert kwargs.get("limit") == 10
        mock_services.goals.search.search_for_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_renders_recent_titles(self, handler: Any, mock_services: Any) -> None:
        mock_services.goals.search.list_recent_for_user.return_value = Result.ok(
            [_make_entity("goal:1", "Get fit"), _make_entity("goal:2", "Read more")]
        )
        result = await handler(_make_request(), type="goal", q="")
        html = render(result)
        assert "Get fit" in html
        assert "Read more" in html
        assert 'data-uid="goal:1"' in html
        assert 'data-title="Read more"' in html


class TestNonEmptyQuery:
    @pytest.mark.asyncio
    async def test_dispatches_to_search(self, handler: Any, mock_services: Any) -> None:
        await handler(_make_request(), type="task", q="ship")
        mock_services.tasks.search.search_for_user.assert_awaited_once()
        kwargs = mock_services.tasks.search.search_for_user.await_args.kwargs
        assert kwargs.get("query") == "ship"
        assert kwargs.get("user_uid") == "user_mike"
        mock_services.tasks.search.list_recent_for_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_whitespace_only_q_treated_as_empty(
        self, handler: Any, mock_services: Any
    ) -> None:
        await handler(_make_request(), type="task", q="   ")
        mock_services.tasks.search.list_recent_for_user.assert_awaited_once()
        mock_services.tasks.search.search_for_user.assert_not_awaited()


class TestTypeRouting:
    """Each supported type dispatches to its own activity-domain facade."""

    @pytest.mark.parametrize(
        ("target_type", "facade_name"),
        [
            ("task", "tasks"),
            ("goal", "goals"),
            ("habit", "habits"),
            ("event", "events"),
            ("choice", "choices"),
            ("principle", "principles"),
        ],
    )
    @pytest.mark.asyncio
    async def test_type_routes_to_facade(
        self, handler: Any, mock_services: Any, target_type: str, facade_name: str
    ) -> None:
        facade = getattr(mock_services, facade_name)
        facade.search.list_recent_for_user.return_value = Result.ok(
            [_make_entity(f"{target_type}:1", f"A {target_type}")]
        )
        result = await handler(_make_request(), type=target_type, q="")
        facade.search.list_recent_for_user.assert_awaited_once()
        html = render(result)
        assert f"A {target_type}" in html
        assert f'data-uid="{target_type}:1"' in html


class TestExclusions:
    @pytest.mark.asyncio
    async def test_exclude_uid_only(self, handler: Any, mock_services: Any) -> None:
        await handler(
            _make_request(),
            type="task",
            q="",
            exclude_uid="task:abc",
        )
        kwargs = mock_services.tasks.search.list_recent_for_user.await_args.kwargs
        assert kwargs.get("exclude") == {"task:abc"}
        mock_services.tasks.search.backend.get_descendant_uids.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exclude_descendants_includes_self_and_subtree(
        self, handler: Any, mock_services: Any
    ) -> None:
        mock_services.tasks.search.backend.get_descendant_uids.return_value = Result.ok(
            {"task:child1", "task:child2"}
        )
        await handler(
            _make_request(),
            type="task",
            q="",
            exclude_descendants_of="task:abc",
        )
        kwargs = mock_services.tasks.search.list_recent_for_user.await_args.kwargs
        assert kwargs.get("exclude") == {"task:abc", "task:child1", "task:child2"}

    @pytest.mark.asyncio
    async def test_descendants_lookup_failure_falls_back_to_self_only(
        self, handler: Any, mock_services: Any
    ) -> None:
        mock_services.tasks.search.backend.get_descendant_uids.return_value = Result.fail(
            Errors.database(operation="get_descendant_uids", message="boom")
        )
        await handler(
            _make_request(),
            type="task",
            q="",
            exclude_descendants_of="task:abc",
        )
        kwargs = mock_services.tasks.search.list_recent_for_user.await_args.kwargs
        assert kwargs.get("exclude") == {"task:abc"}


class TestUnsupportedType:
    @pytest.mark.asyncio
    async def test_unknown_type_returns_disabled_option(
        self, handler: Any, mock_services: Any
    ) -> None:
        result = await handler(_make_request(), type="dragon", q="")
        html = render(result)
        assert "Unsupported picker type" in html
        # No backend service should be called.
        mock_services.tasks.search.list_recent_for_user.assert_not_awaited()
        mock_services.goals.search.list_recent_for_user.assert_not_awaited()
        mock_services.habits.search.list_recent_for_user.assert_not_awaited()


class TestBackendError:
    @pytest.mark.asyncio
    async def test_search_failure_returns_disabled_option(
        self, handler: Any, mock_services: Any
    ) -> None:
        mock_services.goals.search.list_recent_for_user.return_value = Result.fail(
            Errors.database(operation="list_recent_for_user", message="db down")
        )
        result = await handler(_make_request(), type="goal", q="")
        html = render(result)
        assert "Search failed" in html


class TestEmptyResults:
    @pytest.mark.asyncio
    async def test_no_matches_renders_no_matches(self, handler: Any, mock_services: Any) -> None:
        mock_services.goals.search.search_for_user.return_value = Result.ok([])
        result = await handler(_make_request(), type="goal", q="nonexistent")
        html = render(result)
        assert "No matches" in html
