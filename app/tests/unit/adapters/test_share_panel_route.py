"""``GET /gradebook/{uid}/share-panel`` honours the ``preselect`` token (Submit & Share arc PR 6c).

The GradeBook nudge opens the entry's page with ``?share=1&preselect=reviewers``;
the Share button forwards the token to the panel load, and the fragment
checks the offered groups the entry was submitted to for feedback.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.user_entry_ui import create_user_entry_ui_routes
from core.utils.result_simplified import Result
from tests.helpers.route_collector import route_collector

_CANDIDATES = {
    "groups": [{"uid": "g_class", "name": "Physics 101"}, {"uid": "g_other", "name": "Chess"}],
    "people": [],
    "shared_group_uids": [],
    "shared_user_uids": [],
    "reviewer_group_uids": ["g_class"],
}


def _request() -> SimpleNamespace:
    request = SimpleNamespace()
    request.session = {"user_uid": "user_owner"}
    request.url = SimpleNamespace(path="/gradebook/ue_1/share-panel")
    request.method = "GET"
    request.cookies = {}
    request.headers = {}
    request.query_params = {}
    return request


@pytest.fixture
def handler():
    rt, registry = route_collector()
    sharing = SimpleNamespace(candidates=AsyncMock(return_value=Result.ok(_CANDIDATES)))
    create_user_entry_ui_routes(
        rt, SimpleNamespace(), orchestrator=SimpleNamespace(), entry_sharing=sharing
    )
    return registry["/gradebook/{uid}/share-panel", "GET"]


def _checkbox(html: str, value: str) -> str:
    match = re.search(rf'<input[^>]*value="{re.escape(value)}"[^>]*>', html)
    assert match, value
    return match.group(0)


@pytest.mark.asyncio
async def test_preselect_reviewers_checks_the_reviewer_group_only(handler) -> None:
    html = to_xml(await handler(_request(), "ue_1", preselect="reviewers"))
    assert "checked" in _checkbox(html, "group:g_class")
    assert "checked" not in _checkbox(html, "group:g_other")
    assert "disabled" not in html


@pytest.mark.asyncio
async def test_without_the_token_nothing_is_preselected(handler) -> None:
    html = to_xml(await handler(_request(), "ue_1"))
    assert "checked" not in html
