# skuel-lint: disable-file=SKUEL005 -- Event-bus subscribers; fire-and-forget by design (see module docstring)
"""Event handlers that fire :meth:`PsEngagementService.check_auto_complete`.

Subscribed to the four per-domain completion events that fire when an Activity
Domain instance's entity status reaches terminal:

    TaskCompleted          → task.completed
    GoalAchieved           → goal.achieved
    CalendarEventCompleted → calendar_event.completed
    ChoiceMade             → choice.made

Habits and Principles are not subscribed (see ``_terminal_status_rules`` for
the rationale). Engagements containing only Habits/Principles require a
student-declared ``complete_pathstep`` call.

Handlers are fire-and-forget: a check_auto_complete error is logged but never
propagated back through the event bus — the originating mutation (task
completion, goal achievement, etc.) already succeeded and shouldn't be
poisoned by a downstream engagement-check failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.events.calendar_event_events import CalendarEventCompleted
    from core.events.choice_events import ChoiceMade
    from core.events.goal_events import GoalAchieved
    from core.events.task_events import TaskCompleted
    from core.services.ps_engagement.ps_engagement_service import PsEngagementService

logger = get_logger(__name__)


class _AutoCompletionHandler:
    """Bridges per-domain completion events to ``check_auto_complete``.

    One instance is constructed at bootstrap with the live
    :class:`PsEngagementService`. Its methods are subscribed to the four
    trigger event types on the global event bus.
    """

    def __init__(self, ps_engagement: PsEngagementService) -> None:
        self._ps_engagement = ps_engagement
        self.logger = logger

    async def on_task_completed(self, event: TaskCompleted) -> None:
        await self._check(event.user_uid, event.task_uid, "task")

    async def on_goal_achieved(self, event: GoalAchieved) -> None:
        await self._check(event.user_uid, event.goal_uid, "goal")

    async def on_calendar_event_completed(self, event: CalendarEventCompleted) -> None:
        await self._check(event.user_uid, event.event_uid, "event")

    async def on_choice_made(self, event: ChoiceMade) -> None:
        await self._check(event.user_uid, event.choice_uid, "choice")

    async def _check(self, user_uid: str, instance_uid: str, source: str) -> None:
        """Run the auto-complete check; log outcomes; never raise."""
        result = await self._ps_engagement.check_auto_complete(user_uid, instance_uid)
        if result.is_error:
            err = result.expect_error()
            self.logger.warning(
                f"Auto-complete check failed (source={source}, user={user_uid}, "
                f"instance={instance_uid}): {err.message}"
            )
            return
        if result.value is not None:
            self.logger.info(
                f"Auto-completed engagement (triggered by {source}.terminal): "
                f"user={user_uid} ps={result.value.ps_uid}"
            )


__all__ = ["_AutoCompletionHandler"]
