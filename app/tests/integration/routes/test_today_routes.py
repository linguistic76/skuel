"""Route tests for the Today surface.

Covers the endpoints registered by ``create_today_routes``:

- GET  /today                              — authed vs. 401, 500-on-context-error
- GET  /today/{date_str}                    — day-lens nav, bad date → today
- GET  /today/tasks/{uid}/drawer           — ownership, fragment shape
- POST /today/tasks/{uid}/complete         — ownership, 204 on success
- POST /today/tasks/{uid}/defer            — source-aware, view-date-anchored
  (C7): field selection per surface, fresh-membership guard, refusals
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

from core.models.enums import EntityStatus
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


def _make_task(
    uid: str = "task_001",
    due: date | None = None,
    scheduled: date | None = None,
    status: EntityStatus = EntityStatus.ACTIVE,
    recurrence_end: date | None = None,
) -> Any:
    """Build a mock Task with the minimal surface the routes read.

    The defer guard reads due/scheduled/status/recurrence_end_date off the
    FRESH task — set them explicitly so MagicMock auto-attributes (always
    truthy) can't satisfy the membership predicate by accident.
    """
    t = MagicMock()
    t.uid = uid
    t.user_uid = "user_mike"
    t.title = "Ship Today surface"
    t.description = "Translate handoff into production."
    t.due_date = due
    t.scheduled_date = scheduled
    t.status = status
    t.recurrence_end_date = recurrence_end
    return t


@pytest.fixture
def mock_services() -> Any:
    services = MagicMock()

    services.tasks = MagicMock()
    services.tasks.core = MagicMock()
    services.tasks.core.verify_ownership = AsyncMock(return_value=Result.ok(_make_task()))
    services.tasks.core.create_task = AsyncMock(return_value=Result.ok(_make_task()))
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
                "heading": "Today",
                "is_today": True,
                "can_quick_add": True,
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


class TestTodayDatedPage:
    async def test_valid_date_builds_context_for_that_day(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        from datetime import date

        request = _make_request()
        response = await handlers["/today/{date_str}"](request=request, date_str="2026-07-21")
        assert response["__base_page__"] is True
        assert response["active_page"] == "today"
        mock_services.today_orchestrator.build_context.assert_awaited_once_with(
            "user_mike", date(2026, 7, 21)
        )

    async def test_bad_date_degrades_to_today(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        from datetime import date

        request = _make_request()
        response = await handlers["/today/{date_str}"](request=request, date_str="not-a-date")
        assert response["__base_page__"] is True
        # Unparseable → current day rather than 404.
        mock_services.today_orchestrator.build_context.assert_awaited_once_with(
            "user_mike", date.today()
        )

    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(user_uid=None)
        with pytest.raises(HTTPException) as exc:
            await handlers["/today/{date_str}"](request=request, date_str="2026-07-21")
        assert exc.value.status_code == 401


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
# POST /today/tasks/quick-add
# ============================================================================


class TestTaskQuickAdd:
    """C6: day-lens quick-add — scheduled_date only, no due_date, past refused."""

    async def test_unauthenticated_raises_401(self, handlers: dict[str, Any]) -> None:
        request = _make_request(
            user_uid=None, form={"title": "x", "view_date": date.today().isoformat()}
        )
        with pytest.raises(HTTPException) as exc:
            await handlers["/today/tasks/quick-add"](request=request)
        assert exc.value.status_code == 401

    async def test_creates_task_scheduled_on_view_date_without_due(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        view = date.today() + timedelta(days=5)
        request = _make_request(form={"title": "  Draft memo  ", "view_date": view.isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 204
        # HX-Redirect reloads the day's lens so the new work chip renders.
        assert response.headers["HX-Redirect"] == f"/today/{view.isoformat()}"
        call = mock_services.tasks.core.create_task.await_args
        req = call.args[0]
        assert req.title == "Draft memo"  # trimmed
        assert req.scheduled_date == view
        assert req.due_date is None  # a work chip, never a deadline
        assert req.status == EntityStatus.SCHEDULED
        assert call.args[1] == "user_mike"

    async def test_today_is_allowed(self, handlers: dict[str, Any], mock_services: Any) -> None:
        request = _make_request(form={"title": "x", "view_date": date.today().isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 204

    async def test_blank_title_returns_400(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        request = _make_request(form={"title": "   ", "view_date": date.today().isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 400
        mock_services.tasks.core.create_task.assert_not_called()

    async def test_past_view_date_refused_400(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """The affordance is hidden on past days; the POST is the backstop against
        a forged/stale past-date request."""
        past = date.today() - timedelta(days=1)
        request = _make_request(form={"title": "late", "view_date": past.isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 400
        mock_services.tasks.core.create_task.assert_not_called()

    @pytest.mark.parametrize("view_date", ["", "not-a-date", "2026-13-40"])
    async def test_bad_view_date_returns_400(
        self, handlers: dict[str, Any], mock_services: Any, view_date: str
    ) -> None:
        request = _make_request(form={"title": "x", "view_date": view_date})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 400
        mock_services.tasks.core.create_task.assert_not_called()

    async def test_create_failure_returns_500(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.core.create_task = AsyncMock(
            return_value=Result.fail(Errors.database(operation="create_task", message="boom"))
        )
        view = date.today() + timedelta(days=1)
        request = _make_request(form={"title": "x", "view_date": view.isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 500


# ============================================================================
# POST /today/tasks/{uid}/defer
# ============================================================================


def _defer_form(
    span: str = "1d", source: str | None = "ribbon", view_date: date | str | None = None
) -> dict[str, str]:
    """C7 defer form: span + source + view_date (view_date defaults to today)."""
    form = {"span": span}
    if source is not None:
        form["source"] = source
    if view_date is not None:
        form["view_date"] = view_date if isinstance(view_date, str) else view_date.isoformat()
    else:
        form["view_date"] = date.today().isoformat()
    return form


class TestTaskDefer:
    """C7: source-aware, view-date-anchored defer with the full guard set."""

    # ---- field selection -----------------------------------------------------

    async def test_triage_defer_anchors_due_to_view_date_not_old_due(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """A 7-days-overdue 'Defer tomorrow' lands TOMORROW, never six-days-ago."""
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today - timedelta(days=7)))
        )
        request = _make_request(form=_defer_form(span="1d", source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[0] == "task_001"
        assert call.args[1] == TaskUpdateIntent(due_date=today + timedelta(days=1))

    async def test_triage_defer_1w_anchors_to_view_date(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today - timedelta(days=2)))
        )
        request = _make_request(form=_defer_form(span="1w", source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(due_date=today + timedelta(days=7))

    async def test_ribbon_scheduled_only_moves_scheduled_never_invents_due(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Ribbon defer of a scheduled-only task moves scheduled_date to
        view_date + span; due_date stays UNSET — no deadline is invented."""
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task(scheduled=view)))
        request = _make_request(form=_defer_form(span="1d", source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(scheduled_date=view + timedelta(days=1))

    async def test_ribbon_due_match_moves_due(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(return_value=Result.ok(_make_task(due=view)))
        request = _make_request(form=_defer_form(span="1w", source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(due_date=view + timedelta(days=7))

    async def test_ribbon_both_fields_match_moves_both(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=view, scheduled=view))
        )
        request = _make_request(form=_defer_form(span="1d", source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(
            due_date=view + timedelta(days=1), scheduled_date=view + timedelta(days=1)
        )

    async def test_triage_defer_on_dual_membership_task_moves_only_due(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Overdue AND scheduled today: triage speaks deadline language — the
        work date must NOT move (view-date matching alone would move it and
        bounce the task back into triage on refresh)."""
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today - timedelta(days=3), scheduled=today))
        )
        request = _make_request(form=_defer_form(span="1d", source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(due_date=today + timedelta(days=1))

    # ---- request validation ----------------------------------------------------

    async def test_invalid_span_returns_400(self, handlers: dict[str, Any]) -> None:
        request = _make_request(form=_defer_form(span="forever"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400

    @pytest.mark.parametrize("source", [None, "", "drawer", "RIBBON"])
    async def test_missing_or_unknown_source_returns_400(
        self, handlers: dict[str, Any], mock_services: Any, source: str | None
    ) -> None:
        request = _make_request(form=_defer_form(source=source))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    @pytest.mark.parametrize("view_date", ["", "not-a-date", "2026-13-40"])
    async def test_missing_or_bad_view_date_returns_400(
        self, handlers: dict[str, Any], mock_services: Any, view_date: str
    ) -> None:
        request = _make_request(form=_defer_form(view_date=view_date))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    async def test_non_owner_returns_404(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        mock_services.tasks.core.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="Task", identifier="task_999"))
        )
        request = _make_request(form=_defer_form())
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_999")
        assert response.status_code == 404
        mock_services.tasks.update_task.assert_not_called()

    # ---- fresh-membership guard (server does not trust the label) --------------

    async def test_triage_defer_with_stale_view_date_returns_400(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """A stale tab (yesterday's lens) must not anchor a deadline to an
        arbitrary day — triage requires view_date == the current day."""
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today - timedelta(days=7)))
        )
        request = _make_request(
            form=_defer_form(source="triage", view_date=today - timedelta(days=1))
        )
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    async def test_triage_defer_for_non_overdue_task_returns_400(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """A forged 'triage' defer on a task with a future deadline is refused —
        the fresh task must satisfy triage's full membership predicate."""
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today + timedelta(days=3)))
        )
        request = _make_request(form=_defer_form(source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    @pytest.mark.parametrize("source", ["ribbon", "triage"])
    async def test_task_completed_after_page_load_returns_400(
        self, handlers: dict[str, Any], mock_services: Any, source: str
    ) -> None:
        """A completed task's dates still pass the date checks — the shared
        status predicate must refuse the defer on EITHER surface."""
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(
                _make_task(
                    due=today - timedelta(days=2),
                    scheduled=today,
                    status=EntityStatus.COMPLETED,
                )
            )
        )
        request = _make_request(form=_defer_form(source=source))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    async def test_ribbon_defer_with_no_field_match_returns_400(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Defensive: a ribbon card exists via a field match by construction;
        if the fresh task no longer matches the claimed view_date, refuse."""
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=view + timedelta(days=5)))
        )
        request = _make_request(form=_defer_form(source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    async def test_defer_at_date_max_boundary_returns_400_not_500(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """The day lens supports date.max (its nav arrows clamp there), so a
        ribbon card can exist on the boundary day — view_date + span must be
        refused controlled, not raise OverflowError."""
        boundary = date.max
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(scheduled=boundary))
        )
        request = _make_request(form=_defer_form(span="1d", source="ribbon", view_date=boundary))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        mock_services.tasks.update_task.assert_not_called()

    # ---- date-ordering refusals (C4's guard family) -----------------------------

    async def test_ribbon_defer_pushing_scheduled_past_due_is_refused(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=view + timedelta(days=2), scheduled=view))
        )
        request = _make_request(form=_defer_form(span="1w", source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        assert "deadline" in response.body.decode()
        mock_services.tasks.update_task.assert_not_called()

    async def test_ribbon_defer_landing_scheduled_on_due_is_allowed(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        """Work ON the deadline day is legal — creation forbids only
        due < scheduled (strict), mirroring C4's `>` comparison."""
        view = date(2026, 8, 10)
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=view + timedelta(days=1), scheduled=view))
        )
        request = _make_request(form=_defer_form(span="1d", source="ribbon", view_date=view))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 204
        call = mock_services.tasks.update_task.await_args
        assert call.args[1] == TaskUpdateIntent(scheduled_date=view + timedelta(days=1))

    @pytest.mark.parametrize("days_to_end", [1, 3])  # onto (==) and past (>)
    async def test_due_defer_onto_or_past_recurrence_end_is_refused(
        self, handlers: dict[str, Any], mock_services: Any, days_to_end: int
    ) -> None:
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(
                _make_task(
                    due=today - timedelta(days=1),
                    recurrence_end=today + timedelta(days=days_to_end),
                )
            )
        )
        # 1w defer → new due = today + 7, on/after both parametrized ends.
        request = _make_request(form=_defer_form(span="1w", source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 400
        assert "recurrence end" in response.body.decode()
        mock_services.tasks.update_task.assert_not_called()

    # ---- failure propagation ----------------------------------------------------

    async def test_update_failure_returns_500(
        self, handlers: dict[str, Any], mock_services: Any
    ) -> None:
        today = date.today()
        mock_services.tasks.get_task = AsyncMock(
            return_value=Result.ok(_make_task(due=today - timedelta(days=1)))
        )
        mock_services.tasks.update_task = AsyncMock(
            return_value=Result.fail(Errors.database(operation="update_task", message="boom"))
        )
        request = _make_request(form=_defer_form(source="triage"))
        response = await handlers["/today/tasks/{uid}/defer"](request=request, uid="task_001")
        assert response.status_code == 500


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

    async def test_quick_add_without_csrf_token_is_forbidden(
        self, handlers: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # quick-add takes no uid path param — verify its own CSRF guard.
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
        request = _make_request(form={"title": "x", "view_date": date.today().isoformat()})
        response = await handlers["/today/tasks/quick-add"](request=request)
        assert response.status_code == 403
