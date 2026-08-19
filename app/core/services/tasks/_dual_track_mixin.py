"""Tasks dual-track productivity assessment mixin.

Implements the user-level half of the dual-track pattern (ADR-030) for Tasks:
compares the user's *self-assessed* productivity (vision) against a
*system-measured* productivity score derived from their actual task throughput,
on-time completion, and overdue backlog (action). The gap between the two is the
self-awareness insight.

This is the Tasks counterpart to the Events (`_BehavioralSignalsMixin`) and
Choices dual-track mixins — all three are user-level (uid == user_uid), so they
pass ``require_entity=False`` to the BaseAnalyticsService template.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.enums import ProductivityLevel
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.ports.domain_protocols import TasksOperations


class _DualTrackMixin:
    """Dual-track productivity self-assessment for the Tasks domain.

    Declares class-level attributes used by these methods so mypy resolves them
    without runtime cost (the house mixin pattern).

    See: /docs/decisions/ADR-030-dual-track-assessment-pattern.md
    """

    # Populated by TasksIntelligenceService / BaseAnalyticsService
    backend: "TasksOperations"
    logger: Any
    _dual_track_assessment: Any  # provided by BaseAnalyticsService

    async def assess_productivity_dual_track(
        self,
        user_uid: UserUID,
        user_productivity_level: ProductivityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
        store_callback: Callable[[str, DualTrackResult[ProductivityLevel]], Awaitable[None]]
        | None = None,
    ) -> Result[DualTrackResult[ProductivityLevel]]:
        """Compare self-assessed productivity with measured task throughput.

        This is a *user-level* assessment (across all of the user's tasks), not a
        single-entity one — ``uid`` is the user's uid and there is no ``:Entity``
        row to fetch, so the template is invoked with ``require_entity=False``.

        Args:
            user_uid: User making the assessment.
            user_productivity_level: The user's self-reported productivity level.
            user_evidence: Free-text evidence behind the self-rating.
            user_reflection: Optional reflection.
            period_days: Window (days) to measure throughput over (default 30).
            store_callback: Optional persistence callback (uid, result) -> None. The
                user-level check-in lives on the :User node, so the caller binds
                ``UserService.append_dual_track_checkin`` with the dimension — the
                Tasks intelligence backend can't write the User node itself.

        Returns:
            Result[DualTrackResult[ProductivityLevel]] with perception-gap analysis.
        """
        return await self._dual_track_assessment(
            uid=user_uid,  # user-level: user_uid acts as the assessment subject
            user_uid=user_uid,
            user_level=user_productivity_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._make_system_productivity_calculator(period_days),
            level_scorer=self._productivity_level_to_score,
            entity_type="productivity",
            require_entity=False,  # user-level: uid=user_uid, no :Entity row to fetch
            store_callback=store_callback,
        )

    def _make_system_productivity_calculator(self, period_days: int) -> Any:
        """Build the system-calculator closure the template expects."""

        async def _calculate(
            _entity: object, u_uid: str
        ) -> tuple[ProductivityLevel, float, list[str]]:
            return await self._calculate_system_productivity_for_dual_track(
                UserUID(u_uid), period_days
            )

        return _calculate

    async def _calculate_system_productivity_for_dual_track(
        self, user_uid: UserUID, period_days: int = 30
    ) -> tuple[ProductivityLevel, float, list[str]]:
        """Measure productivity from task data.

        Composite (0.0-1.0): completion throughput 50%, on-time rate 30%,
        backlog-not-overdue 20%.

        - completion throughput = completed-in-window / (completed-in-window + open backlog)
        - on-time rate = of completed-in-window, fraction finished on/before due
          (tasks with no due_date count as on-time)
        - backlog-not-overdue = 1 - overdue / open backlog

        Returns (level, score, evidence-lines).
        """
        evidence: list[str] = []
        start_date = date.today() - timedelta(days=period_days)

        # Fetch the full task set (find_by defaults to limit=100 with no ordering, so
        # the in-memory window filter below would otherwise sample an arbitrary page and
        # miss recent completions / backlog for prolific users).
        tasks_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if tasks_result.is_error or not tasks_result.value:
            evidence.append("No tasks found to measure")
            # No data is not the same as low productivity — return a neutral midpoint
            # so the perception gap reflects "nothing to measure", not "overwhelmed".
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, evidence

        all_tasks = tasks_result.value
        if len(all_tasks) >= QueryLimit.MAXIMUM:
            self.logger.warning(
                "Productivity assessment for %s capped at %d tasks — score may be truncated",
                user_uid,
                QueryLimit.MAXIMUM,
            )

        completed_in_window = [
            t
            for t in all_tasks
            if t.is_completed and t.completion_date and t.completion_date >= start_date
        ]
        open_backlog = [t for t in all_tasks if not t.is_completed]

        denom = len(completed_in_window) + len(open_backlog)
        if denom == 0:
            evidence.append(f"No tasks active in the last {period_days} days")
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, evidence

        completion_rate = len(completed_in_window) / denom
        evidence.append(
            f"{len(completed_in_window)} completed in {period_days}d vs "
            f"{len(open_backlog)} open ({completion_rate:.0%} throughput)"
        )

        if completed_in_window:
            on_time = [
                t
                for t in completed_in_window
                # completion_date is non-None by construction of completed_in_window
                if not t.due_date
                or (t.completion_date is not None and t.completion_date <= t.due_date)
            ]
            on_time_rate = len(on_time) / len(completed_in_window)
            evidence.append(f"On-time completion: {on_time_rate:.0%}")
        else:
            on_time_rate = 0.0

        if open_backlog:
            overdue = [t for t in open_backlog if t.is_overdue()]
            not_overdue_rate = 1.0 - (len(overdue) / len(open_backlog))
            if overdue:
                evidence.append(f"{len(overdue)} of {len(open_backlog)} open tasks overdue")
        else:
            not_overdue_rate = 1.0

        composite_score = completion_rate * 0.50 + on_time_rate * 0.30 + not_overdue_rate * 0.20

        system_level = ProductivityLevel.from_score(composite_score)
        return system_level, composite_score, evidence

    @staticmethod
    def _productivity_level_to_score(level: ProductivityLevel) -> float:
        """Convert ProductivityLevel to its numeric score."""
        return level.to_score()
