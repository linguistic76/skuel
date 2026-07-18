"""Route tests for the Today surface.

Covers the six endpoints registered by ``create_today_routes``:

- GET  /today                              — authed vs. 401, 500-on-context-error
- GET  /today/tasks/{uid}/drawer           — ownership, fragment shape
- POST /today/tasks/{uid}/complete         — ownership, 204 on success
- POST /today/tasks/{uid}/defer            — span=1d|1w, invalid span → 400
- POST /today/tasks/{uid}/star             — pin/unpin toggle, 204
- POST /today/lifepaths/{uid}/wake         — no-op 204 (optimistic stub)

No Neo4j required: services are mocked. BasePage is monkey-patched to an
async identity stub so we can inspect what the route hands it.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.exceptions import HTTPException

from core.models.task.task_update_intent import TaskUpdateIntent
from core.utils.result_simplified import Errors, Result


def _make_request(
    user_uid: str | None = "user_mike",
    form: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    method: str = "POST",
) -> Any:
    """Build a minimal request-like object for session-backed auth.

    Carries ``method`` because the POST routes are now ``@csrf_protected`` and
    the wrapper reads ``request.method``. CSRF verification itself is disabled
    for this module (see ``_disable_csrf_enforcement``) — these tests cover
    handler logic, not the CSRF layer (that has its own tests).
    """
    session = {"user_uid": user_uid} if user_uid is not None else {}
    form_data = form or {}

    async def _form() -> dict[str, str]:
        return form_data

    return SimpleNamespace(
        method=method,
        session=session,
        url=SimpleNamespace(path="/today"),
        query_params=query or {},
        form=_form,
        cookies={},
    )


@pytest.fixture(autouse=True)
def _disable_csrf_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the ``@csrf_protected`` POST wrappers pass through to the handler.

    The request stubs here are ``SimpleNamespace`` objects without cookies, so
    real CSRF verification can't run; with enforcement off the wrapper falls
    straight through after the method check, preserving the 401/404/204
    assertions below.
    """
    monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")


def _make_task(uid: str = "task_001", due: date | None = None) -> Any:
    """Build a mock Task with the minimal surface the routes read."""
    t = MagicMock()
    t.uid = uid
    t.user_uid = "user_mike"
    t.title = "Ship Today surface"
    t.description = "Translate handoff into production."
    t.due_date = due
    return t


@pytest.fixture
def mock_services() -> Any:
    services = MagicMock()

    services.tasks = MagicMock()
    services.tasks.core = MagicMock()
    services.tasks.core.verify_ownership = AsyncMock(return_value=Result.ok(_make_task()))
    services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task()))
    services.tasks.update_task = AsyncMock(return_value=Result.ok(_make_task()))
    services.tasks.complete_task = AsyncMock(return_value=Result.ok(_make_task()))

    services.user_relationships = MagicMock()
    services.user_relationships.get_today_pinned = AsyncMock(return_value=Result.ok(set()))
    services.user_relationships.pin_for_today = AsyncMock(return_value=Result.ok(True))
    services.user_relationships.unpin_for_today = AsyncMock(return_value=Result.ok(True))

    services.today_orchestrator = MagicMock()
    services.today_orchestrator.build_context = AsyncMock(
        return_value=Result.ok(
            {
                "today_iso": "2027-04-23",
                "date_label": "Saturday · April 23",
                "now_hhmm": "09:00",
                "stats": {"nodes": 0, "committed_min": 0, "done": 0},
                "triage": [],
                "lifepaths": [],
                "principles": [],
                "goals": [],
                "tasks": [],
                "rituals": [],
                "kinds": {},
            }
        )
    )
    return services


@pytest.fixture
def handlers(mock_services: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Register /today routes and return path → handler."""

    def fake_base_page(**kwargs: Any) -> dict[str, Any]:
        return {"__base_page__": True, **kwargs}

    import ui.patterns.sidebar as sidebar_module

    monkeypatch.setattr(sidebar_module, "BasePage", fake_base_page)

    from adapters.inbound.today_routes import create_today_routes

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    create_today_routes(MagicMock(), rt_collector, mock_services)
    return registered


# ============================================================================
# GET /today
# ============================================================================


class TestTodayPage:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/today"](request=request)
        assert exc.value.status_code == 401

    async def test_authenticated_renders_page(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request()
        response = await handlers["/today"](request=request)
        assert response["__base_page__"] is True
        assert response["title"] == "Today"
        assert response["active_page"] == "today"
        mock_services.today_orchestrator.build_context.assert_awaited_once_with("user_mike")

    async def test_context_error_returns_500(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.today_orchestrator.build_context = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="build_today_context", message="boom")
            )
        )
        request = _make_request()
        response = await handlers["/today"](request=request)
        assert response.status_code == 500


# ============================================================================
# GET /today/tasks/{uid}/drawer
# ============================================================================


class TestTaskDrawer:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/today/tasks/{uid}/drawer"](request=request, uid="task_001")
        assert exc.value.status_code == 401

    async def test_non_owner_gets_404(self, handlers: dict[str, Any], mock_services: Any) -> None:
        mock_services.tasks.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_999"))
        )
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/drawer"](request=request, uid="task_999")
        assert response.status_code == 404

    async def test_owner_gets_fragment(self, handlers: dict[str, Any], mock_services: Any) -> None:
        from starlette.responses import Response

        request = _make_request()
        response = await handlers["/today/tasks/{uid}/drawer"](request=request, uid="task_001")
        # Fragment is an FT (FastHTML component), not a Starlette Response
        assert response is not None
        assert not isinstance(response, Response)
        mock_services.tasks.get_task.assert_awaited_once_with("task_001")


# ============================================================================
# POST /today/tasks/{uid}/complete
# ============================================================================


class TestTaskComplete:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/today/tasks/{uid}/complete"](request=request, uid="task_001")
        assert exc.value.status_code == 401

    async def test_success_returns_204(self, handlers: dict[str, Any], mock_services: Any) -> None:
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/complete"](request=request, uid="task_001")
        assert response.status_code == 204
        mock_services.tasks.complete_task.assert_awaited_once_with("task_001")

    async def test_non_owner_returns_404(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_999"))
        )
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/complete"](request=request, uid="task_999")
        assert response.status_code == 404
        mock_services.tasks.complete_task.assert_not_called()

    async def test_service_failure_returns_500(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.complete_task = AsyncMock(
            return_value=Result.fail(Errors.database(operation="complete_task", message="boom"))
        )
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/complete"](request=request, uid="task_001")
        assert response.status_code == 500


# ============================================================================
# POST /today/tasks/{uid}/defer
# ============================================================================


class TestTaskDefer:
    async def test_default_span_1d_shifts_due_date_by_one_day(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        today = date(2026, 4, 23)
        mock_services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task(due=today)))

        request = _make_request(form={"span": "1d"})
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")

        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[0] == "task_001"
        assert call.args[1] == TaskUpdateIntent(due_date=today + timedelta(days=1))

    async def test_span_1w_shifts_by_seven_days(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        today = date(2026, 4, 23)
        mock_services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task(due=today)))

        request = _make_request(form={"span": "1w"})
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")

        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(due_date=today + timedelta(days=7))

    async def test_invalid_span_returns_400(self, handlers: dict[str, Any]) -> None:
        request = _make_request(form={"span": "forever"})
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400

    async def test_non_owner_returns_404(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_999"))
        )
        request = _make_request(form={"span": "1d"})
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_999")
        assert response.status_code == 404
        mock_services.tasks.update_task.assert_not_called()

    async def test_task_without_due_date_falls_back_to_today(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """A task with no due_date still defers — base falls back to today."""
        mock_services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task(due=None)))
        request = _make_request(form={"span": "1d"})
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        # Whatever the base, the update should happen
        mock_services.tasks.update_task.assert_awaited_once()


# ============================================================================
# POST /today/tasks/{uid}/star
# ============================================================================


class TestTaskStar:
    async def test_unpinned_task_gets_pinned(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.user_relationships.get_today_pinned = AsyncMock(return_value=Result.ok(set()))
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/star"](request=request, uid="task_001")
        assert response.status_code == 204
        mock_services.user_relationships.pin_for_today.assert_awaited_once()
        mock_services.user_relationships.unpin_for_today.assert_not_called()

    async def test_pinned_task_gets_unpinned(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.user_relationships.get_today_pinned = AsyncMock(
            return_value=Result.ok({"task_001"})
        )
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/star"](request=request, uid="task_001")
        assert response.status_code == 204
        mock_services.user_relationships.unpin_for_today.assert_awaited_once()
        mock_services.user_relationships.pin_for_today.assert_not_called()

    async def test_non_owner_returns_404(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_999"))
        )
        request = _make_request()
        response = await handlers["/today/tasks/{uid}/star"](request=request, uid="task_999")
        assert response.status_code == 404


# ============================================================================
# POST /today/lifepaths/{uid}/wake
# ============================================================================


class TestLifepathWake:
    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/today/lifepaths/{uid}/wake"](request=request, uid="lp_001")
        assert exc.value.status_code == 401

    async def test_authenticated_returns_204(self, handlers: dict[str, Any]) -> None:
        request = _make_request()
        response = await handlers["/today/lifepaths/{uid}/wake"](request=request, uid="lp_001")
        assert response.status_code == 204


# ============================================================================
# CSRF protection (Finding 2 — Codex P2)
# ============================================================================


class TestCsrfProtection:
    """The mutating Today POST routes must reject tokenless requests when CSRF
    enforcement is on. Guards against the ``@csrf_protected`` decorator being
    dropped (the other tests run with enforcement disabled)."""

    @pytest.mark.parametrize(
        "path",
        [
            "/today/tasks/{uid}/complete",
            "/today/tasks/{uid}/defer",
            "/today/tasks/{uid}/star",
            "/today/lifepaths/{uid}/wake",
        ],
    )
    async def test_post_without_csrf_token_is_forbidden(
        self, handlers: dict[str, Any], monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")  # override the module-wide disable
        request = _make_request()  # authenticated, but carries no CSRF cookie/token
        response = await handlers[path](request=request, uid="x_001")
        assert response.status_code == 403
