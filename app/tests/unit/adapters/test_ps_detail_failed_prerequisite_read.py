"""A failed prerequisite read must not tell a learner nothing blocks the step.

The accordion's empty state says exactly that, so the page's route leaves the section
out when it cannot read the prerequisites. Driven through the real route.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.learning_loop_routes as routes
from core.utils.result_simplified import Errors, Result

_UID = "ps.test.step"


def _client(
    monkeypatch: pytest.MonkeyPatch, statuses: Result[list[dict[str, object]]]
) -> TestClient:
    monkeypatch.setattr(routes, "get_current_user", _signed_out)
    step = SimpleNamespace(
        title="A step", description="", estimated_time_minutes=None, tags=(), content=None
    )
    orchestrator = MagicMock()
    orchestrator.get_ps_with_content = AsyncMock(return_value=Result.ok((step, "")))
    orchestrator.get_exercises_for_path_step = AsyncMock(return_value=Result.ok([]))
    orchestrator.get_used_kus = AsyncMock(return_value=Result.ok([]))
    orchestrator.get_cited_resources = AsyncMock(return_value=Result.ok([]))
    orchestrator.get_ps_prerequisite_statuses = AsyncMock(return_value=statuses)
    app, rt = fast_app(pico=False, default_hdrs=False, secret_key="ps-detail-test")
    routes.create_learning_loop_detail_routes(
        rt,
        orchestrator=orchestrator,
        user_service=MagicMock(),
        context_intelligence=MagicMock(),
    )
    return TestClient(app)


def _signed_out(_request: object) -> None:
    return None


def test_a_failed_read_leaves_the_section_out(monkeypatch: pytest.MonkeyPatch) -> None:
    failed: Result[list[dict[str, object]]] = Result.fail(Errors.database("read", "down"))

    page = _client(monkeypatch, failed).get(f"/explore/ps/{_UID}/content")

    assert page.status_code == 200
    assert "A step" in page.text
    assert "Blocking dependencies" not in page.text
    assert "nothing blocks this step" not in page.text


def test_a_read_finding_nothing_shows_the_section(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _client(monkeypatch, Result.ok([])).get(f"/explore/ps/{_UID}/content")

    assert page.status_code == 200
    assert "Blocking dependencies" in page.text
