"""Unit tests for the activity → curriculum origin surfacing (Gap #3).

Spawned activities carry ``source_path_step_uid``; the detail page resolves it
to the source PathStep's title (``fetch_source_pathstep``) and renders a
breadcrumb link (``CurriculumOriginField``) back to ``/explore/ps/{uid}``.
"""

from unittest.mock import AsyncMock

import pytest

from core.utils.connection_fetcher import fetch_source_pathstep
from core.utils.result_simplified import Errors, Result
from ui.activities._shared import CONNECTION_ICONS, CurriculumOriginField


class TestCurriculumOriginField:
    def test_renders_link_to_pathstep_detail(self):
        html = str(CurriculumOriginField("ps:demo:step-1", "Intro to Patterns"))
        assert "/explore/ps/ps:demo:step-1" in html
        assert "Intro to Patterns" in html

    def test_falls_back_to_uid_when_title_empty(self):
        html = str(CurriculumOriginField("ps:demo:step-1", ""))
        assert "ps:demo:step-1" in html

    def test_path_step_icon_links_to_explore_ps(self):
        # The dead "#" href was replaced so path_step badges navigate.
        assert CONNECTION_ICONS["path_step"][1] == "/explore/ps/"


class TestFetchSourcePathstep:
    @pytest.mark.asyncio
    async def test_returns_uid_and_title_on_hit(self):
        backend = AsyncMock()
        backend.execute_query = AsyncMock(
            return_value=Result.ok([{"uid": "ps:demo:step-1", "title": "Intro"}])
        )
        result = await fetch_source_pathstep(backend, "ps:demo:step-1")
        assert result == {"uid": "ps:demo:step-1", "title": "Intro"}

    @pytest.mark.asyncio
    async def test_none_for_empty_uid_without_querying(self):
        backend = AsyncMock()
        backend.execute_query = AsyncMock()
        assert await fetch_source_pathstep(backend, "") is None
        backend.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_when_pathstep_missing(self):
        backend = AsyncMock()
        backend.execute_query = AsyncMock(return_value=Result.ok([]))
        assert await fetch_source_pathstep(backend, "ps:gone") is None

    @pytest.mark.asyncio
    async def test_none_on_query_error(self):
        backend = AsyncMock()
        backend.execute_query = AsyncMock(
            return_value=Result.fail(Errors.database("lookup", "boom"))
        )
        assert await fetch_source_pathstep(backend, "ps:demo:step-1") is None

    @pytest.mark.asyncio
    async def test_falls_back_to_uid_when_title_null(self):
        backend = AsyncMock()
        backend.execute_query = AsyncMock(
            return_value=Result.ok([{"uid": "ps:demo:step-1", "title": None}])
        )
        result = await fetch_source_pathstep(backend, "ps:demo:step-1")
        assert result == {"uid": "ps:demo:step-1", "title": "ps:demo:step-1"}
