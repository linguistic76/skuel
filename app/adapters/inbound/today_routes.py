"""Today surface routes — post-login landing page + HTMX actions.

Six endpoints, matching ``docs/design-handoff/today/today.md`` §5:

- ``GET /today`` — full page (TodayOrchestrator → TodayPage → BasePage)
- ``GET /today/tasks/{uid}/drawer`` — drawer body fragment
- ``POST /today/tasks/{uid}/complete`` — complete task, 204
- ``POST /today/tasks/{uid}/defer`` — shift due_date by ``span`` (1d|1w), 204
- ``POST /today/tasks/{uid}/star`` — pin/unpin task for user, 204
- ``POST /today/lifepaths/{uid}/wake`` — clear dormancy, 204

All task routes verify ownership — non-owners get 404 (no UID oracle).
Today is a cross-cutting view; routes are registered via the
``create_today_routes`` bootstrap callable, not ``DomainRouteConfig``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories.route_helpers import verify_entity_ownership
from core.models.task.task_update_intent import TaskUpdateIntent
from core.models.type_hints import EntityUID, UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


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

    @rt("/today")
    async def today_page(request: Request) -> Any:
        """Render the Today landing page."""
        user_uid = require_authenticated_user(request)
        from ui.activities.nav import render_activity_sidebar_page
        from ui.today import TodayPage

        ctx_result = await orchestrator.build_context(user_uid)
        if ctx_result.is_error:
            logger.warning(
                "today.build_context failed for user=%s: %s",
                user_uid,
                ctx_result.expect_error().message,
            )
            return Response("Could not build Today context", status_code=500)

        return await render_activity_sidebar_page(
            content=TodayPage(ctx_result.value),
            active="today",
            request=request,
            extra_css=["/static/css/today.css"],
            title="Today",
            active_page="today",
        )

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

    @rt("/today/tasks/{uid}/defer", methods=["POST"])
    @csrf_protected
    async def today_task_defer(request: Request, uid: str) -> Response:
        """Shift a task's due_date by ``span`` (``1d`` or ``1w``). 204 on success."""
        user_uid = require_authenticated_user(request)

        form = await request.form()
        span_raw = form.get("span") or "1d"
        span_key = str(span_raw).strip()
        delta = _DEFER_SPANS.get(span_key)
        if delta is None:
            return Response(f"Invalid span '{span_key}'", status_code=400)

        ownership_error = await verify_entity_ownership(tasks.core, uid, user_uid, "tasks")
        if ownership_error is not None:
            return Response("Task not found", status_code=404)

        task_result = await tasks.get_task(uid)
        if task_result.is_error:
            return Response("Task not found", status_code=404)

        task = task_result.value
        base_due = task.due_date if task.due_date is not None else date.today()
        new_due = base_due + delta

        update = await tasks.update_task(uid, TaskUpdateIntent(due_date=new_due))
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
