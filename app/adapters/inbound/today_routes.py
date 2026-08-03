"""Today surface routes — post-login landing page + HTMX actions.

Matching ``docs/design-handoff/today/today.md`` §5:

- ``GET /today`` — full page (TodayOrchestrator → TodayPage → BasePage)
- ``GET /today/{date_str}`` — the day lens for an arbitrary date (Prev/Next)
- ``GET /today/tasks/{uid}/drawer`` — drawer body fragment
- ``POST /today/tasks/{uid}/complete`` — complete task, 204
- ``POST /today/tasks/quick-add`` — create a task scheduled on the viewed day
  (C6): ``scheduled_date`` only, no ``due_date``; past days refused; HX-Redirect
- ``POST /today/tasks/{uid}/defer`` — source-aware, view-date-anchored defer
  (C7): moves the field(s) the card spoke for to ``view_date + span``, 204
- ``POST /today/tasks/{uid}/star`` — pin/unpin task for user, 204
- ``POST /today/lifepaths/{uid}/wake`` — clear dormancy, 204

All uid-scoped task routes verify ownership — non-owners get 404 (no UID oracle).
The defer guard validates against the SAME membership predicates the lens
renders by (``ui/today/membership.py``) — see C7 in
``docs/roadmap/calendar-act-from-arc.md``.
Today is a cross-cutting view; routes are registered via the
``create_today_routes`` bootstrap callable, not ``DomainRouteConfig``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.enums import EntityStatus
from core.models.sentinels import UNSET
from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import EntityUID, UserUID
from core.utils.logging import get_logger
from core.utils.neo4j_temporal import convert_neo4j_date
from core.utils.result_simplified import Result
from ui.today.membership import (
    DUE_FIELD,
    SCHEDULED_FIELD,
    is_ribbon_member,
    is_triage_member,
    ribbon_date_fields,
)

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services
    from ui.page_contexts import TodayPageContext


logger = get_logger("skuel.routes.today")


_DEFER_SPANS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "1w": timedelta(days=7),
}


def create_today_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register the six Today surface routes."""

    orchestrator = services.today_orchestrator
    tasks = services.tasks
    rels = services.user_relationships
    assert orchestrator is not None, "TodayOrchestrator not wired in Services container"
    assert tasks is not None, "TasksService not wired in Services container"
    assert rels is not None, "UserRelationshipBackend not wired in Services container"

    def _render_today(request: Request, ctx_result: Result[TodayPageContext]) -> Response | FT:
        """Render a built Today context, or a 500 shell on build failure."""
        if ctx_result.is_error:
            logger.warning(
                "today.build_context failed: %s",
                ctx_result.expect_error().message,
            )
            return Response("Could not build Today context", status_code=500)

        from ui.activities.nav import render_activity_sidebar_page
        from ui.today import TodayPage

        return render_activity_sidebar_page(
            content=TodayPage(ctx_result.value),
            active="today",
            request=request,
            extra_css=["/static/css/today.css"],
            title="Today",
            active_page="today",
        )

    # boundary: fasthtml-app — registered route; FastHTML resolves the handler's
    # annotations at registration, so the FT/Response return stays Any here (the
    # concrete Response | FT shape lives on the _render_today helper above). This
    # matches the repo-wide full-page-handler convention (e.g. calendar_week).
    @rt("/today")
    async def today_page(request: Request) -> Any:
        """Render the Today landing page (the live current day)."""
        user_uid = require_authenticated_user(request)
        ctx_result = await orchestrator.build_context(user_uid)
        return _render_today(request, ctx_result)

    @rt("/today/{date_str}")
    async def today_page_dated(request: Request, date_str: str) -> Any:  # boundary: fasthtml-app
        """Render the day lens for an arbitrary date (Prev/Next navigation).

        An unparseable ``date_str`` degrades to the current day rather than 404 —
        the surface is always meaningful for *some* day.
        """
        user_uid = require_authenticated_user(request)
        try:
            view_date = date.fromisoformat(date_str)
        except ValueError:
            view_date = date.today()
        ctx_result = await orchestrator.build_context(user_uid, view_date)
        return _render_today(request, ctx_result)

    @rt("/today/tasks/{uid}/drawer")
    async def today_task_drawer(request: Request, uid: str) -> Any:
        """Return the HTMX fragment body for the drawer."""
        user_uid = require_authenticated_user(request)

        ownership_error = await verify_entity_ownership(tasks.core, uid, user_uid, "tasks")
        if ownership_error is not None:
            return Response("Task not found", status_code=404)

        task_result = await tasks.get_task(uid)
        if task_result.is_error:
            return Response("Task not found", status_code=404)

        from ui.today import render_task_drawer_body

        return render_task_drawer_body(task_result.value)

    @rt("/today/tasks/{uid}/complete", methods=["POST"])
    @csrf_protected
    async def today_task_complete(request: Request, uid: str) -> Response:
        """Complete a task. 204 on success, 404 on unknown/unowned."""
        user_uid = require_authenticated_user(request)

        ownership_error = await verify_entity_ownership(tasks.core, uid, user_uid, "tasks")
        if ownership_error is not None:
            return Response("Task not found", status_code=404)

        result = await tasks.complete_task(uid)
        if result.is_error:
            logger.warning(
                "today.complete failed for task=%s user=%s: %s",
                uid,
                user_uid,
                result.expect_error().message,
            )
            return Response("Complete failed", status_code=500)
        return Response(status_code=204)

    @rt("/today/tasks/quick-add", methods=["POST"])
    @csrf_protected
    async def today_task_quick_add(request: Request) -> Response:
        """Create a task scheduled on the viewed day (day-lens quick-add, C6).

        TASKS ONLY: creates with ``scheduled_date`` = the viewed day and NO
        ``due_date`` ("I'll work on it that day" — a work chip, not a deadline;
        the widened lens membership then renders it on this very day). The viewed
        day must be today or later: a past day is refused 400 — the day lens hides
        the affordance on past days (``can_quick_add``), and this is the
        server-side backstop against a forged/stale past-date POST. On success the
        response redirects the browser back to the day's lens (``HX-Redirect``) so
        the new task renders immediately (and survives a manual refresh — it is
        persisted, not optimistic). Events keep the Create-an-Event page; only
        tasks are the daily-lived quick capture.
        """
        user_uid = require_authenticated_user(request)

        form = await request.form()
        title = str(form.get("title") or "").strip()
        if not title:
            return Response("Task title is required", status_code=400)

        view_date_raw = str(form.get("view_date") or "").strip()
        try:
            view_date = date.fromisoformat(view_date_raw)
        except ValueError:
            return Response(f"Invalid view_date '{view_date_raw}'", status_code=400)

        if view_date < date.today():
            return Response(
                "Cannot add a task to a past day — open today or a future day",
                status_code=400,
            )

        # scheduled_date only (no due_date) → a work chip, per C6. The request
        # model re-runs future-date + length validation; a forged over-long title
        # surfaces as a clean 400 rather than an unhandled 500.
        try:
            create_req = TaskCreateRequest(
                title=title,
                scheduled_date=view_date,
                status=EntityStatus.SCHEDULED,
            )
        except ValidationError as exc:
            logger.info("today.quick_add rejected invalid task for user=%s: %s", user_uid, exc)
            return Response("Invalid task", status_code=400)

        result = await tasks.core.create_task(create_req, user_uid)
        if result.is_error:
            logger.warning(
                "today.quick_add failed for user=%s: %s",
                user_uid,
                result.expect_error().message,
            )
            return Response("Could not add the task — try again", status_code=500)
        # Reload the day's lens so the new work chip renders (and the calendar
        # picks it up on its next fetch). HX-Redirect drives a full navigation.
        return Response(
            status_code=204,
            headers={"HX-Redirect": f"/today/{view_date.isoformat()}"},
        )

    @rt("/today/tasks/{uid}/defer", methods=["POST"])
    @csrf_protected
    async def today_task_defer(request: Request, uid: str) -> Response:
        """Defer a task from a day-lens card, anchored to the day it was asked from.

        The POST carries ``span`` (``1d``|``1w``), ``view_date`` (the lens day
        the card rendered on) and ``source`` (``ribbon``|``triage``). Field
        selection speaks the card's language: triage always moves ``due_date``
        (deadline language — even for a task also scheduled on the viewed
        day); ribbon moves the field(s) equal to ``view_date`` on the freshly
        fetched task (both when both match). The new value is always
        ``view_date + span``, never ``old value + span``.

        The server does not trust the label: the fresh task must still satisfy
        the claimed surface's FULL membership predicate — the same function
        objects ``build_context()`` renders by (``ui/today/membership.py``) —
        and a triage defer additionally requires ``view_date`` to be the
        current day; otherwise 400. Refusals (400, message in body): a move
        pushing the work date past the deadline, or the deadline onto/past
        ``recurrence_end_date`` (mirrors C4's reschedule guards). 204 on
        success, 404 on unknown/unowned.
        """
        user_uid = require_authenticated_user(request)

        form = await request.form()
        span_key = str(form.get("span") or "1d").strip()
        delta = _DEFER_SPANS.get(span_key)
        if delta is None:
            return Response(f"Invalid span '{span_key}'", status_code=400)

        source = str(form.get("source") or "").strip()
        if source not in ("ribbon", "triage"):
            return Response(f"Invalid source '{source}'", status_code=400)

        view_date_raw = str(form.get("view_date") or "").strip()
        try:
            view_date = date.fromisoformat(view_date_raw)
        except ValueError:
            return Response(f"Invalid view_date '{view_date_raw}'", status_code=400)

        ownership_error = await verify_entity_ownership(tasks.core, uid, user_uid, "tasks")
        if ownership_error is not None:
            return Response("Task not found", status_code=404)

        task_result = await tasks.get_task(uid)
        if task_result.is_error:
            return Response("Task not found", status_code=404)
        task = task_result.value

        today = date.today()
        if source == "triage":
            # Triage speaks deadline language and only exists on the live
            # current day — a stale tab or forged POST must not anchor a
            # deadline to an arbitrary day.
            if view_date != today:
                return Response(
                    "Triage defers only apply to the current day — refresh the page",
                    status_code=400,
                )
            if not is_triage_member(task, today):
                return Response("Task is no longer in triage — refresh the page", status_code=400)
            move_fields: tuple[str, ...] = (DUE_FIELD,)
        else:
            # A ribbon card exists via a field match by construction — but the
            # task may have moved or completed since the page loaded, so the
            # match is re-derived from the FRESH task; no match is refused.
            if not is_ribbon_member(task, view_date):
                return Response(
                    "Task is no longer on this day's lens — refresh the page",
                    status_code=400,
                )
            move_fields = ribbon_date_fields(task, view_date)

        # The day lens supports the full date range (its Prev/Next arrows clamp
        # at date.min/date.max), so a card CAN render on a boundary day —
        # view_date + span would raise OverflowError there. Refuse controlled.
        if view_date > date.max - delta:
            return Response(
                "Deferred date would pass the end of the supported date range",
                status_code=400,
            )
        new_value = view_date + delta

        # Moving only the work date must not push it past a standing deadline
        # (creation forbids due_date < scheduled_date and the update path
        # doesn't recheck — same guard family as C4's reschedule). When both
        # fields move they land on the same day, which that ordering allows.
        moves_scheduled_only = SCHEDULED_FIELD in move_fields and DUE_FIELD not in move_fields
        if moves_scheduled_only and task.due_date is not None and new_value > task.due_date:
            return Response(
                f"Work date would pass the task's deadline ({task.due_date.isoformat()})"
                " — edit the task to move the deadline",
                status_code=400,
            )
        if DUE_FIELD in move_fields:
            recurrence_end = convert_neo4j_date(task.recurrence_end_date)
            if recurrence_end is not None and new_value >= recurrence_end:
                # Creation forbids due_date on/after recurrence_end_date and
                # the update path doesn't recheck (C4 guards its reschedule
                # the same way) — refuse rather than persist a recurrence
                # window that ends before it starts.
                return Response(
                    f"New date is not before the recurrence end ({recurrence_end.isoformat()})"
                    " — edit the task to change its recurrence",
                    status_code=400,
                )

        intent = TaskUpdateIntent(
            due_date=new_value if DUE_FIELD in move_fields else UNSET,
            scheduled_date=new_value if SCHEDULED_FIELD in move_fields else UNSET,
        )
        update = await tasks.update_task(uid, intent)
        if update.is_error:
            logger.warning(
                "today.defer failed for task=%s user=%s: %s",
                uid,
                user_uid,
                update.expect_error().message,
            )
            return Response("Defer failed", status_code=500)
        return Response(status_code=204)

    @rt("/today/tasks/{uid}/star", methods=["POST"])
    @csrf_protected
    async def today_task_star(request: Request, uid: str) -> Response:
        """Toggle Today-scope pin-state on a task. 204 on success.

        Uses the :PINNED_TODAY edge, not the global :PINNED edge — starring
        a task in Today must not leak into other surfaces that list the
        user's global pins.
        """
        user_uid = require_authenticated_user(request)

        ownership_error = await verify_entity_ownership(tasks.core, uid, user_uid, "tasks")
        if ownership_error is not None:
            return Response("Task not found", status_code=404)

        pinned_result = await rels.get_today_pinned(user_uid)
        already_pinned = not pinned_result.is_error and uid in pinned_result.value

        entity_uid = EntityUID(uid)
        user_uid_typed = UserUID(user_uid)
        toggle = (
            await rels.unpin_for_today(user_uid_typed, entity_uid)
            if already_pinned
            else await rels.pin_for_today(user_uid_typed, entity_uid)
        )
        if toggle.is_error:
            logger.warning(
                "today.star toggle failed for task=%s user=%s: %s",
                uid,
                user_uid,
                toggle.expect_error().message,
            )
            return Response("Star failed", status_code=500)
        return Response(status_code=204)

    @rt("/today/lifepaths/{uid}/wake", methods=["POST"])
    @csrf_protected
    async def today_lifepath_wake(
        request: Request, uid: str
    ) -> Response:  # skuel-lint: disable=SKUEL029 -- wrapped by @csrf_protected which awaits the handler unconditionally (csrf.py)
        """Clear the dormant flag on a LifePath ribbon.

        There is no server-side dormancy state yet — dormancy is computed
        on each page build from recent activity. This endpoint exists so
        the Alpine optimistic UI can fire-and-forget without a 404. Once
        durable dormancy tracking lands, this will write the wake event.
        """
        user_uid = require_authenticated_user(request)
        logger.info("today.wake lifepath=%s user=%s", uid, user_uid)
        return Response(status_code=204)


__all__ = ["create_today_routes"]
