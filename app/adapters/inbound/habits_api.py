"""Habits API routes.

Provides JSON endpoints for habit status/priority updates, completion tracking,
lifecycle data, reminders, and daily-scheduling queries.

Routes
------
Status (existing):
    POST /api/habits/set-status        — HTMX status card update

Completion tracking:
    POST /api/habits/track             — Record a completion
    POST /api/habits/untrack           — Remove a completion entry
    POST /api/habits/bulk-complete     — Mark multiple habits complete at once

Completion data (ownership-verified):
    GET  /api/habits/streak            — Current + best streak
    GET  /api/habits/progress          — Stats for week/month/year
    GET  /api/habits/history           — Completion history (last N days)
    GET  /api/habits/completion-calendar — Calendar grid for a month

User stats (no per-habit uid required):
    GET  /api/habits/badge-progress    — Gamification badge progress
    GET  /api/habits/due-today         — Habits due for today
    GET  /api/habits/completed-today-count — How many completed today

Reminders:
    POST /api/habits/reminder          — Set a reminder
    GET  /api/habits/reminder          — Get reminders for a habit
    POST /api/habits/reminder/delete   — Delete a reminder

Export:
    GET  /api/habits/export            — Download completion history (CSV/JSON)

Hierarchy (ownership-verified):
    GET  /api/habits/children     — Direct subhabits of a parent habit
    GET  /api/habits/parent       — Immediate parent of a subhabit
    GET  /api/habits/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/habits/remove-child — Remove a subhabit relationship
    POST /api/habits/add-child    — Add a subhabit relationship

Cross-domain links:
    POST /api/habits/link-knowledge    — Link habit to the knowledge/skill it develops
    POST /api/habits/link-principle    — Link habit to the principle/value it embodies

Knowledge intelligence:
    GET  /api/habits/knowledge-patterns — Detected learning patterns across user habits
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler, result_to_response
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    FieldUpdateSpec,
    create_activity_field_api_routes,
    parse_int_query_param,
    verify_entity_ownership,
)
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkHabitToKnowledgeRequest,
    LinkHabitToPrincipleRequest,
    RemoveHierarchyChildRequest,
)
from core.models.habit.habit import Habit
from core.models.habit.habit_request import (
    BulkCompleteHabitsRequest,
    DeleteHabitReminderRequest,
    SetHabitReminderRequest,
    TrackHabitRequest,
    UntrackHabitRequest,
)
from core.models.habit.habit_update_intent import HabitUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.habits_views import HabitCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.habits_service import HabitsService
    from core.services.principles_service import PrinciplesService


def create_habits_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
    principles_service: PrinciplesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Habits API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Habit]:
        # ADR-066: facade + typed intent (no .core.update(dict) — the last activity
        # *_api.py to converge onto the One-Path typed update contract).
        return await habits_service.update_habit(uid, HabitUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Habit]:
        return await habits_service.update_habit(uid, HabitUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="habits",
            singular="habit",
            service=habits_service,
            card_fn=HabitCard,
            fields=(
                FieldUpdateSpec(field="status", apply=update_status),
                FieldUpdateSpec(
                    field="priority", apply=update_priority, allowed_values=PRIORITY_VALUES
                ),
            ),
        ),
    )

    # ================================================================
    # COMPLETION TRACKING
    # ================================================================

    @rt("/api/habits/track", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def habit_track(request: Request) -> Result[dict[str, Any]]:
        """Record a habit completion for the authenticated user."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, TrackHabitRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        result = await habits_service.track_habit(req)
        if result.is_error:
            return Result.fail(result)
        c = result.value
        return Result.ok(
            {
                "uid": c.uid,
                "habit_uid": c.habit_uid,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                "quality": c.quality,
            }
        )

    @rt("/api/habits/untrack", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_untrack(request: Request) -> Result[dict[str, Any]]:
        """Remove a completion entry for the authenticated user."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, UntrackHabitRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        result = await habits_service.untrack_habit(req)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/habits/bulk-complete", methods=["POST"])
    @csrf_protected
    @boundary_handler(success_status=201)
    async def habit_bulk_complete(request: Request) -> Result[dict[str, Any]]:
        """Mark multiple habits complete at once."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, BulkCompleteHabitsRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        for habit_uid in parsed.value.habit_uids:
            ownership_error = await verify_entity_ownership(
                habits_service, habit_uid, user_uid, "habit"
            )
            if ownership_error:
                return ownership_error
        result = await habits_service.completions.record_completions_bulk(
            parsed.value.habit_uids, user_uid
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"completed": len(result.value)})

    # ================================================================
    # COMPLETION DATA (per-habit, ownership-verified)
    # ================================================================

    @rt("/api/habits/streak")
    @boundary_handler()
    async def habit_streak(request: Request) -> Result[dict[str, Any]]:
        """Current and best streak for a habit."""
        user_uid = require_authenticated_user(request)
        habit_uid = request.query_params.get("uid", "")
        if not habit_uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))

        ownership_error = await verify_entity_ownership(
            habits_service, habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.get_habit_streak(habit_uid)

    @rt("/api/habits/progress")
    @boundary_handler()
    async def habit_progress(request: Request) -> Result[dict[str, Any]]:
        """Completion stats for a habit over week/month/year."""
        user_uid = require_authenticated_user(request)
        habit_uid = request.query_params.get("uid", "")
        period = request.query_params.get("period", "month")
        if not habit_uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        if period not in ("week", "month", "year"):
            return Result.fail(
                Errors.validation(message="period must be week, month, or year", field="period")
            )

        ownership_error = await verify_entity_ownership(
            habits_service, habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.get_habit_progress(habit_uid, period)

    @rt("/api/habits/history")
    @boundary_handler()
    async def habit_history(request: Request) -> Result[list[dict[str, Any]]]:
        """Completion history for a habit (last N days, default 90)."""
        user_uid = require_authenticated_user(request)
        habit_uid = request.query_params.get("uid", "")
        if not habit_uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        days = parse_int_query_param(
            request.query_params, "days", default=90, minimum=1, maximum=365
        )

        ownership_error = await verify_entity_ownership(
            habits_service, habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.get_habit_history(habit_uid, days)

    @rt("/api/habits/completion-calendar")
    @boundary_handler()
    async def habit_completion_calendar(request: Request) -> Result[dict[str, Any]]:
        """Calendar grid of completions for a habit (defaults to current month)."""
        user_uid = require_authenticated_user(request)
        habit_uid = request.query_params.get("uid", "")
        if not habit_uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        year = parse_int_query_param(request.query_params, "year", default=0) or None
        month = parse_int_query_param(request.query_params, "month", default=0) or None

        ownership_error = await verify_entity_ownership(
            habits_service, habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.get_completion_calendar(habit_uid, year, month)

    # ================================================================
    # USER STATS
    # ================================================================

    @rt("/api/habits/badge-progress")
    @boundary_handler()
    async def habit_badge_progress(request: Request) -> Result[dict[str, Any]]:
        """Gamification badge progress for the authenticated user."""
        user_uid = require_authenticated_user(request)
        return await habits_service.completions.get_badge_progress(user_uid)

    @rt("/api/habits/due-today")
    @boundary_handler()
    async def habits_due_today(request: Request) -> Result[list[dict[str, Any]]]:
        """Habits scheduled for today for the authenticated user."""
        user_uid = require_authenticated_user(request)
        result = await habits_service.get_habits_due_today(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "uid": h.uid,
                    "title": h.title,
                    "recurrence_pattern": h.recurrence_pattern.value
                    if h.recurrence_pattern
                    else None,
                }
                for h in result.value
            ]
        )

    @rt("/api/habits/completed-today-count")
    @boundary_handler()
    async def habits_completed_today_count(request: Request) -> Result[dict[str, Any]]:
        """How many habits the authenticated user completed today."""
        user_uid = require_authenticated_user(request)
        result = await habits_service.completions.calculate_completed_today_count(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"count": result.value})

    # ================================================================
    # REMINDERS
    # ================================================================

    @rt("/api/habits/reminder", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_set_reminder(request: Request) -> Result[dict[str, Any]]:
        """Set a reminder for a habit."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, SetHabitReminderRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.set_habit_reminder(req)

    @rt("/api/habits/reminder", methods=["GET"])
    @boundary_handler()
    async def habit_get_reminders(request: Request) -> Result[list[dict[str, Any]]]:
        """Get reminders for a habit."""
        user_uid = require_authenticated_user(request)
        habit_uid = request.query_params.get("uid", "")
        if not habit_uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))

        ownership_error = await verify_entity_ownership(
            habits_service, habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        return await habits_service.get_habit_reminders(habit_uid)

    @rt("/api/habits/reminder/delete", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_delete_reminder(request: Request) -> Result[dict[str, Any]]:
        """Delete a reminder for a habit."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, DeleteHabitReminderRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        result = await habits_service.delete_habit_reminder(req)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"deleted": result.value})

    # ================================================================
    # EXPORT
    # ================================================================

    @rt("/api/habits/export")
    async def habit_export(request: Request) -> Any:
        """Download completion history as CSV or JSON.

        Query params:
            format: "csv" (default) or "json"
            start_date: ISO date string (optional)
            end_date: ISO date string (optional)
        """
        from datetime import date

        user_uid = require_authenticated_user(request)
        fmt = request.query_params.get("format", "csv")
        start_raw = request.query_params.get("start_date")
        end_raw = request.query_params.get("end_date")

        start_date: date | None = None
        end_date: date | None = None
        try:
            if start_raw:
                start_date = date.fromisoformat(start_raw)
            if end_raw:
                end_date = date.fromisoformat(end_raw)
        except ValueError:
            from starlette.responses import JSONResponse

            return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status_code=400)

        result = await habits_service.completions.export_completion_history(
            user_uid, start_date=start_date, end_date=end_date, format=fmt
        )
        if result.is_error:
            return result_to_response(result)

        content_type = "text/csv" if fmt == "csv" else "application/json"
        filename = f"habit-completions.{fmt}"
        return Response(
            result.value,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ================================================================
    # HIERARCHY — read-paths and relationship removal
    # ================================================================

    @rt("/api/habits/children", methods=["GET"])
    @boundary_handler()
    async def habit_children(request: Request) -> Result[list[Habit]]:
        """Direct subhabits of a parent habit."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(habits_service, uid, user_uid, "habit")
        if ownership_error:
            return ownership_error
        result = await habits_service.get_subhabits(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([h for h in result.value if h.user_uid == user_uid])

    @rt("/api/habits/parent", methods=["GET"])
    @boundary_handler()
    async def habit_parent(request: Request) -> Result[Optional[Habit]]:  # noqa: UP045
        """Immediate parent of a subhabit (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(habits_service, uid, user_uid, "habit")
        if ownership_error:
            return ownership_error
        result = await habits_service.get_parent_habit(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

    @rt("/api/habits/hierarchy", methods=["GET"])
    @boundary_handler()
    async def habit_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(habits_service, uid, user_uid, "habit")
        if ownership_error:
            return ownership_error
        result = await habits_service.get_habit_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [hab for hab in h["ancestors"] if hab.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [hab for hab in h["siblings"] if hab.user_uid == user_uid],
                "children": [hab for hab in h["children"] if hab.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

    @rt("/api/habits/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subhabit relationship (does not delete the habit nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            habits_service, req.parent_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            habits_service, req.child_uid, user_uid, "habit"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await habits_service.remove_subhabit_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/habits/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subhabit relationship between two habits."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, AddHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        if req.parent_uid == req.child_uid:
            return Result.fail(
                Errors.validation("parent_uid and child_uid must differ", field="child_uid")
            )
        ownership_error = await verify_entity_ownership(
            habits_service, req.parent_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            habits_service, req.child_uid, user_uid, "habit"
        )
        if child_ownership_error:
            return child_ownership_error
        existing_parent = await habits_service.get_parent_habit(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation("habit already has a parent — remove it first", field="child_uid")
            )
        result = await habits_service.create_subhabit_relationship(
            req.parent_uid, req.child_uid, req.progress_weight
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/habits/link-knowledge", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_link_knowledge(request: Request) -> Result[dict[str, Any]]:
        """Link habit to knowledge/skill it develops (REINFORCES_KNOWLEDGE). Ku is shared content."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkHabitToKnowledgeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        result = await habits_service.link_habit_to_knowledge(
            req.habit_uid, req.knowledge_uid, req.skill_level, req.proficiency_gain_rate
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    @rt("/api/habits/link-principle", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def habit_link_principle(request: Request) -> Result[dict[str, Any]]:
        """Link habit to principle/value it embodies (EMBODIES_PRINCIPLE)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkHabitToPrincipleRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            habits_service, req.habit_uid, user_uid, "habit"
        )
        if ownership_error:
            return ownership_error
        principle_ownership_error = await verify_entity_ownership(
            principles_service, req.principle_uid, user_uid, "principle"
        )
        if principle_ownership_error:
            return principle_ownership_error
        result = await habits_service.link_habit_to_principle(
            req.habit_uid, req.principle_uid, req.embodiment_strength
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    @rt("/api/habits/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def habit_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's habits."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await habits_service.analyze_learning_patterns(user_uid, timeframe_days)
        if result.is_error:
            return Result.fail(result)
        patterns = [
            {
                "pattern_type": p.pattern_type.value,
                "knowledge_uids": p.knowledge_uids,
                "entity_uids": p.entity_uids,
                "confidence": p.confidence,
                "timeframe_days": p.timeframe_days,
                "frequency": p.frequency,
                "growth_indicator": p.growth_indicator,
                "metadata": p.metadata,
            }
            for p in result.value
        ]
        return Result.ok(
            {"patterns": patterns, "count": len(patterns), "timeframe_days": timeframe_days}
        )

    return [
        *field_routes,
        habit_track,
        habit_untrack,
        habit_bulk_complete,
        habit_streak,
        habit_progress,
        habit_history,
        habit_completion_calendar,
        habit_badge_progress,
        habits_due_today,
        habits_completed_today_count,
        habit_set_reminder,
        habit_get_reminders,
        habit_delete_reminder,
        habit_export,
        habit_children,
        habit_parent,
        habit_hierarchy,
        habit_remove_child,
        habit_add_child,
        habit_link_knowledge,
        habit_link_principle,
        habit_knowledge_patterns,
    ]
