"""
Goals Progress Service
=======================

Handles goal progress tracking, milestones, and forecasting.

Responsibilities:
- Progress calculation with context awareness
- Milestone management and completion
- Habit-based progress updates
- Velocity metrics and forecasting
- Risk analysis and acceleration opportunities
"""

import dataclasses
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal

from core.events import (
    GoalAchieved,
    GoalContributionsChanged,
    GoalHabitsChanged,
    GoalMilestoneReached,
    GoalProgressUpdated,
    GoalReopened,
    GoalUpdated,
    publish_event,
)
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.goal.milestone import Milestone
from core.models.type_hints import Neo4jProperties, UserUID
from core.models.update_contracts import GuardedRecompute, StatusWriteGuard
from core.ports.domain_protocols import GoalsOperations
from core.ports.query_types import ContributionTally, LinkedHabitTally
from core.services.base_service import BaseService
from core.services.completion_stamp import (
    COMPLETION_FIELDS,
    is_completion_transition,
    is_reopen_transition,
)
from core.services.domain_config import create_activity_domain_config
from core.services.goals.goal_relationships import GoalRelationships
from core.services.goals.progress_history import with_progress_entry
from core.services.infrastructure import ProgressCalculator
from core.services.user import UserContext
from core.services.user.rich_context import (
    find_rich_graph_context,
    get_model_from_rich_context,
    rich_graph_uids,
)
from core.utils.dto_converters import to_domain_model
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.result_simplified import ErrorCategory, Errors, Result
from core.utils.timestamp_helpers import (
    as_stored_clock,
    as_utc,
    from_wall_clock,
    now_utc,
    today_in,
)
from core.utils.uid_generator import UIDGenerator
from core.utils.zone_context import current_zone

# Type alias for rich goal data from UserContext
RichGoalData = dict[str, Any]

#: The one prior status every achievement condition in this file tests. The guard's sets
#: hold canonical ``EntityStatus`` **values** (strings), matching how status is stored —
#: an enum member would never match the prior the write hands back.
_COMPLETED_ONLY: Final = frozenset({EntityStatus.COMPLETED.value})

#: Goal's canonical completion field, taken from the shared mapping the update chokepoint
#: and the backfill script also read, so this file cannot drift from them on the name.
_ACHIEVED_FIELD: Final = COMPLETION_FIELDS[EntityType.GOAL]


def _achievement_write(target_achieved: bool) -> tuple[StatusWriteGuard, Neo4jProperties]:
    """Package "this recompute achieves the goal" as a condition of the write (ADR-087).

    A progress writer derives its achievement TARGET in Python — "progress reached
    100" — and that half is a statement about the NEW state. The other half, "…and it
    was not already achieved", is a fact only the write knows: it depends on the status
    the node holds at write time. So it is the guard's condition — the status/stamp
    pair merges only when the prior was not already COMPLETED, and a write that finds
    a finished goal cannot re-date ``achieved_date``.

    The patch rides ``patch_if_prior_not_in`` rather than the base updates so that an
    already-achieved goal is written NO ``status`` key either — the recompute still lands
    (progress, tally, milestone flags), the completion pair does not.

    The patch is returned alongside the guard so the caller derives its ``GoalAchieved``
    verdict from the same pure helper the update chokepoints use
    (:func:`is_completion_transition`) instead of restating the condition in a second
    place. Against the empty patch that helper is False, so the not-achieved branch needs
    no separate test.

    Args:
        target_achieved: Whether this recompute's own derivation says the goal is now
            achieved.

    Returns:
        ``(guard, patch)`` — the guard to hand the write, and the patch it would merge on
        a prior that is not already COMPLETED. Both are empty/inert when the target is
        not achieved.
    """
    if not target_achieved:
        return StatusWriteGuard(), {}
    # Today in the user's zone matches _STAMP_SPECS[GOAL]'s factory in
    # ``completion_stamp`` — Goal stamps a calendar date, as
    # ``GoalsCoreService.update_goal`` does.
    patch: Neo4jProperties = {
        "status": EntityStatus.COMPLETED.value,
        _ACHIEVED_FIELD: today_in(current_zone()),
    }
    return StatusWriteGuard(patch_if_prior_not_in=(_COMPLETED_ONLY, patch)), patch


#: Statuses its owner settled a goal in. A recompute writes such a goal's figure, never its
#: status: reaching 100% does not complete a cancelled, archived or failed goal.
_SETTLED: Final = frozenset(
    s.value for s in (EntityStatus.CANCELLED, EntityStatus.ARCHIVED, EntityStatus.FAILED)
)


#: The status a goal returns to when a recompute un-achieves it — the working status a
#: goal is created in and counted under (``get_stats_for_user``'s ``active``).
_UNACHIEVED_STATUS: Final = EntityStatus.ACTIVE.value


def _recompute_status_write(
    old_progress: float, new_progress: float
) -> tuple[StatusWriteGuard, Neo4jProperties, Neo4jProperties]:
    """The status half of a tally recompute: achieve on a rise to 100, un-achieve on a drop.

    Progress a recompute derives from the graph is a measurement, so the goal's status
    follows it both ways (docs/roadmap/done/goal-progress-one-way.md):

    - **rising to 100%** achieves the goal — :func:`_achievement_write`'s patch, merged
      only when the prior is not already COMPLETED;
    - **falling below 100%** un-achieves it — status back to ACTIVE and ``achieved_date``
      removed, merged only when the prior IS COMPLETED. The mirror patch, on the mirror
      condition, so a goal that was never completed is not touched and one that was
      cannot keep a stamp while not completed.

    Both targets are transitions of the figure (old vs new, read under the lock), so a
    goal completed by hand at a lower figure is not un-achieved by a recompute that
    merely moves within the band below 100. A goal its owner settled (cancelled,
    archived, failed) is never achieved by a recompute: the achievement patch is merged
    only on a prior outside ``_COMPLETED_ONLY | _SETTLED``.

    Returns:
        ``(guard, achievement, unachievement)`` — the guard to write with, and the two
        patches it may merge, for the caller's transition verdicts.
    """
    guard, achievement = _achievement_write(new_progress >= 100 and old_progress < 100)
    if guard.patch_if_prior_not_in is not None:
        guard = dataclasses.replace(
            guard, patch_if_prior_not_in=(_COMPLETED_ONLY | _SETTLED, achievement)
        )
    if not (new_progress < 100 <= old_progress):
        return guard, achievement, {}
    unachievement: Neo4jProperties = {"status": _UNACHIEVED_STATUS, _ACHIEVED_FIELD: None}
    return (
        dataclasses.replace(guard, patch_if_prior_in=(_COMPLETED_ONLY, unachievement)),
        achievement,
        unachievement,
    )


@dataclass(frozen=True)
class GoalTallyGap:
    """A derived goal figure (TASK_BASED or HABIT_BASED) that disagrees with what it is
    derived from: its contributions or its supporting habits."""

    goal_uid: str
    user_uid: UserUID
    stored: str
    live: str


@dataclass(frozen=True)
class _ProgressWrite:
    """A tally recompute's write, plus what its handler reports from it.

    Satisfies ``GuardedWritePlan`` (``updates`` + ``guard``); the rest travels back on
    ``GuardedRecompute.plan`` so the handler publishes from the figures the write used.
    """

    # boundary: pre-serialization patch — ``progress_history`` is a list of entry dicts,
    # JSON-serialized at the write, as every progress writer's patch is.
    updates: dict[str, Any]
    guard: StatusWriteGuard
    achievement: Neo4jProperties
    unachievement: Neo4jProperties
    old_progress: float
    new_progress: float
    progress_changed: bool
    detail: str


def contribution_progress(tally: ContributionTally) -> float:
    """A contribution tally as a percentage: completed over total, 0.0 for none.

    The figure a TASK_BASED goal's progress is written as (:func:`_plan_contribution_progress`)
    and the one the progress dashboard reports as its contribution figure — one function,
    so the two cannot round or scale apart.
    """
    total = tally["total_contributions"]
    if total == 0:
        return 0.0
    return tally["completed_contributions"] / total * 100


def _plan_contribution_progress(goal: Goal, tally: ContributionTally) -> _ProgressWrite | None:
    """Plan a TASK_BASED goal's write from its contribution tally; ``None`` for no write.

    Runs under the goal's lock (``GoalsBackend.recompute_progress_from_contributions``),
    so ``goal`` and ``tally`` are the state the write lands on. A goal whose last
    contribution left is written 0 / 0 and 0%, so its stored figure never describes a
    contribution it no longer has.
    """
    # Only TASK_BASED goals are recomputed here. A MIXED goal weights tasks, habits,
    # knowledge and milestones together, and this handler sees only the contribution
    # tally; blending that into the stored figure feeds each result back into the next.
    # See docs/roadmap/mixed-goal-event-progress.md.
    if goal.measurement_type != MeasurementType.TASK_BASED:
        return None

    total = tally["total_contributions"]
    completed = tally["completed_contributions"]
    new_progress = contribution_progress(tally)
    old_progress = goal.progress_percentage or 0.0

    # Only write if something changed. The stored tally is part of "something":
    # 1-of-5 and 2-of-10 are both 20%, so a percentage-only guard would leave the
    # detail page rendering "1/5" after five more were linked and one completed.
    # `!=` rather than a narrowed comparison on purpose — it never raises across types,
    # and a legacy string current_value reads as stale and gets repaired by the write.
    tally_stale = goal.current_value != completed or goal.target_value != total
    progress_changed = abs(new_progress - old_progress) >= 0.1
    if not progress_changed and not tally_stale:
        return None

    # raw-write: system progress propagation from the contribution tally. Bypasses the
    # validated/event-firing service contract (GoalUpdateIntent → update_goal) on
    # purpose — the handler publishes its own GoalProgressUpdated with the provenance
    # the generic update_goal cannot express.
    # The stamp records a CHANGE of the figure; a tally repair alone is not one.
    updates: dict[str, Any] = {"progress_percentage": new_progress}
    if progress_changed:
        now = datetime.now()
        updates["last_progress_update"] = now
        updates["progress_history"] = with_progress_entry(goal, new_progress, now)

    # The measurement IS the contribution tally, so this writer owns both ends of it.
    # Writing only the completed count would pair it with a target_value nothing relates
    # to it — a user-typed 5 against 20 contributions renders "4/5" beside a 20% bar.
    # total is the denominator new_progress was computed from, so all three fields agree
    # by construction. Nothing else computes on a TASK_BASED goal's target_value —
    # calculate_combined_progress returns task_contribution * 100 and discards
    # milestone_completion — which is what makes it this writer's to own.
    updates["current_value"] = float(completed)
    updates["target_value"] = float(total)

    guard, achievement, unachievement = _recompute_status_write(old_progress, new_progress)
    return _ProgressWrite(
        updates=updates,
        guard=guard,
        achievement=achievement,
        unachievement=unachievement,
        old_progress=old_progress,
        new_progress=new_progress,
        progress_changed=progress_changed,
        detail=f"{completed}/{total} contributions",
    )


def _plan_habit_progress(goal: Goal, tally: LinkedHabitTally) -> _ProgressWrite | None:
    """Plan a HABIT_BASED goal's write from its habits' average streak; ``None`` for no write.

    Runs under the goal's lock (``GoalsBackend.recompute_progress_from_linked_habits``).
    A goal whose last habit left is written an average of 0 and 0%, as a task-based goal
    whose last contribution left is, so its figure never describes a habit it no longer
    has.
    """
    # Only HABIT_BASED goals — MIXED for the reason given in _plan_contribution_progress.
    if goal.measurement_type != MeasurementType.HABIT_BASED:
        return None

    total_habits = tally["total_habits"]
    avg_streak = tally["avg_streak"]

    old_progress = goal.progress_percentage or 0.0
    # target_value is the desired streak length
    target_value = goal.target_value or 100.0
    habit_contribution = (avg_streak / target_value) if target_value > 0 else 0
    new_progress = min(habit_contribution * 100, 100.0)

    # Skip only if nothing changed. `new_progress` is capped at 100, so once a streak
    # reaches its target the percentage stops moving while avg_streak keeps climbing —
    # the measurement would freeze at "30/30 days" on a 31-day streak.
    measurement_stale = goal.current_value != avg_streak
    progress_changed = abs(new_progress - old_progress) >= 0.01
    if not progress_changed and not measurement_stale:
        return None

    # raw-write: system progress propagation from the habit streaks — same reasoning as
    # _plan_contribution_progress, with the habit provenance.
    updates: dict[str, Any] = {"progress_percentage": new_progress}
    if progress_changed:
        now = datetime.now()
        updates["last_progress_update"] = now
        updates["progress_history"] = with_progress_entry(goal, new_progress, now)
    # avg_streak is a genuine measurement in target_value's unit (days).
    updates["current_value"] = float(avg_streak)

    guard, achievement, unachievement = _recompute_status_write(old_progress, new_progress)
    return _ProgressWrite(
        updates=updates,
        guard=guard,
        achievement=achievement,
        unachievement=unachievement,
        old_progress=old_progress,
        new_progress=new_progress,
        progress_changed=progress_changed,
        detail=f"avg_streak={avg_streak:.1f}, {total_habits} habits",
    )


def _plan_milestones(goal: Goal, milestones: list[Milestone]) -> _ProgressWrite:
    """Plan the write of a goal's milestone list, and of the figure when it follows them.

    Runs under the goal's lock. On a milestone-measured goal the figure is the
    milestones': completed over total as the percentage, the two counts as the
    ``current_value`` / ``target_value`` pair, and status follows the figure by the
    recompute rule (``_recompute_status_write``). On every other type the list alone is
    written: that goal's figure has another writer.
    """
    old_progress = goal.progress_percentage or 0.0
    # boundary: pre-serialization patch — the milestone records and history entries are
    # JSON-serialized at the write, as every progress writer's patch is.
    updates: dict[str, Any] = {"milestones": milestones}
    total = len(milestones)
    completed = sum(1 for m in milestones if m.is_completed)
    detail = f"{completed}/{total} milestones"
    measurement = goal.measurement_type
    if measurement is None or not measurement.follows_milestones():
        return _ProgressWrite(
            updates=updates,
            guard=StatusWriteGuard(),
            achievement={},
            unachievement={},
            old_progress=old_progress,
            new_progress=old_progress,
            progress_changed=False,
            detail=detail,
        )

    new_progress = completed / total * 100 if total else 0.0
    progress_changed = abs(new_progress - old_progress) >= 0.01
    updates["progress_percentage"] = new_progress
    updates["current_value"] = float(completed)
    updates["target_value"] = float(total)
    if progress_changed:
        now = datetime.now()
        updates["last_progress_update"] = now
        updates["progress_history"] = with_progress_entry(goal, new_progress, now)
    guard, achievement, unachievement = _recompute_status_write(old_progress, new_progress)
    return _ProgressWrite(
        updates=updates,
        guard=guard,
        achievement=achievement,
        unachievement=unachievement,
        old_progress=old_progress,
        new_progress=new_progress,
        progress_changed=progress_changed,
        detail=detail,
    )


def _plan_entered_figure(
    goal: Goal, value: float, note: str, at: datetime
) -> Result[_ProgressWrite]:
    """Plan the write of a figure the learner entered, or the refusal it is owed.

    Runs under the goal's lock. ``at`` is the moment the progress happened, on the
    stored clock. ``note`` rides the history entry the write appends; a note with
    the figure unmoved is still an entry, marked ``note_only`` (it records what the
    learner said, not a progress event, so no stamp and no event).
    """
    measurement = goal.measurement_type or MeasurementType.PERCENTAGE
    if not measurement.takes_entered_figure():
        return Result.fail(
            Errors.business(
                "goal_figure_is_derived",
                "This goal's progress is measured for you, so it takes no entered figure.",
                measurement_type=measurement.value,
            )
        )
    if value < 0:
        return Result.fail(
            Errors.validation(message="Progress cannot be negative", field="progress", value=value)
        )

    old_progress = goal.progress_percentage or 0.0
    # boundary: pre-serialization patch, as in ``_plan_milestones``.
    updates: dict[str, Any] = {}
    if measurement.entered_in_units():
        target = goal.target_value
        if not target or target <= 0:
            return Result.fail(
                Errors.validation(
                    message="Set a target value on this goal before recording progress",
                    field="target_value",
                )
            )
        new_progress = min(value / target * 100, 100.0)
        updates["current_value"] = float(value)
        detail = f"{value:g}/{target:g}"
    else:
        if value > 100:
            return Result.fail(
                Errors.validation(
                    message="Progress is a percentage, 0 to 100", field="progress", value=value
                )
            )
        new_progress = float(value)
        detail = f"{value:g}%"

    updates["progress_percentage"] = new_progress
    # The stamp records a CHANGE: re-posting the stored figure is not a progress event.
    progress_changed = abs(new_progress - old_progress) >= 0.01
    if progress_changed:
        updates["last_progress_update"] = at
        updates["progress_history"] = with_progress_entry(goal, new_progress, at, note)
    elif note:
        updates["progress_history"] = with_progress_entry(
            goal, new_progress, at, note, note_only=True
        )

    guard, achievement, unachievement = _recompute_status_write(old_progress, new_progress)
    return Result.ok(
        _ProgressWrite(
            updates=updates,
            guard=guard,
            achievement=achievement,
            unachievement=unachievement,
            old_progress=old_progress,
            new_progress=new_progress,
            progress_changed=progress_changed,
            detail=detail,
        )
    )


def _without_status(plan: _ProgressWrite) -> _ProgressWrite:
    """A recompute's write with its status half taken off: the figure and the measure,
    never the status.

    What a reopen's recompute writes. The learner has just said the goal is not done,
    so the recompute restores the figure its measure gives and leaves the status the
    reopen set: a measure still at 100 shows 100% on a working goal, and the next real
    change of the measure moves it from there.
    """
    return dataclasses.replace(plan, guard=StatusWriteGuard(), achievement={}, unachievement={})


def _contribution_figure(goal: Goal, tally: ContributionTally) -> _ProgressWrite | None:
    """:func:`_plan_contribution_progress` without its status half (:func:`_without_status`)."""
    plan = _plan_contribution_progress(goal, tally)
    return _without_status(plan) if plan is not None else None


def _habit_figure(goal: Goal, tally: LinkedHabitTally) -> _ProgressWrite | None:
    """:func:`_plan_habit_progress` without its status half (:func:`_without_status`)."""
    plan = _plan_habit_progress(goal, tally)
    return _without_status(plan) if plan is not None else None


if TYPE_CHECKING:
    from core.events.habit_events import HabitCompleted
    from core.models.graph.path_aware_types import GoalCrossContext
    from core.services.relationships import UnifiedRelationshipService


def _parse_progress_date(raw: str) -> datetime | None:
    """A client's ISO date or datetime as the instant it names — ``None`` when it
    does not parse. An offset-less value is a wall clock in the current zone and a
    bare date that day's first instant there (``from_wall_clock``); the instant
    comes back on the stored clock, the naive form the goal's stamps take."""
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return as_stored_clock(from_wall_clock(parsed, current_zone()))


class GoalsProgressService(BaseService[GoalsOperations, Goal]):
    """
    Goal progress tracking and milestone management service.

    Handles:
    - Progress calculation with multiple contribution factors
    - Milestone completion and tracking
    - Habit-based progress updates
    - Velocity metrics and completion forecasting
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=GoalDTO,
        model_class=Goal,
        domain_name="goals",
        date_field="target_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )

    # Service name for hierarchical logging
    _service_name = "goals.progress"

    def __init__(
        self,
        backend: GoalsOperations,
        event_bus=None,
        relationship_service: UnifiedRelationshipService | None = None,
    ) -> None:
        """
        Initialize goals progress service.

        Args:
            backend: Protocol-based backend for goal operations,
            event_bus: Event bus for publishing domain events (optional)
            relationship_service: Service for fetching goal relationships

        Note:
            Context invalidation now happens via event-driven architecture.
            Goal events trigger user_service.invalidate_context() in bootstrap.
        """
        super().__init__(backend)  # Uses _service_name class attribute
        self.event_bus = event_bus
        self.relationships = relationship_service  # GRAPH-NATIVE: For fetching goal relationships

    # ========================================================================
    # CONTEXT-FIRST PATTERN HELPERS (November 26, 2025)
    # ========================================================================
    #
    # These methods implement the Context-First Pattern:
    # - UserContext is THE source of truth for user state
    # - Services CONSUME context, they don't rebuild it
    # - Only query what context doesn't have
    #
    # Benefits:
    # - 2 queries → 1 query per progress calculation (when rich context available)
    # - Single source of truth (no race conditions)
    # - Architectural consistency
    #
    # ========================================================================

    def _get_goal_from_rich_context(self, goal_uid: str, user_context: UserContext) -> Goal | None:
        """
        Try to get Goal entity from UserContext rich data.

        Context-First Pattern: Use context data when available to avoid
        unnecessary Neo4j queries.

        Args:
            goal_uid: Goal identifier
            user_context: User's context (may contain rich goal data)

        Returns:
            Goal if found in rich context, None otherwise
        """
        return get_model_from_rich_context(user_context, "goals", goal_uid, GoalDTO, Goal)

    def _get_relationships_from_rich_context(
        self, goal_uid: str, user_context: UserContext
    ) -> GoalRelationships | None:
        """
        Try to get GoalRelationships from UserContext rich data.

        Context-First Pattern: Graph neighborhoods are often included in
        rich context from MEGA-QUERY.

        Args:
            goal_uid: Goal identifier
            user_context: User's context with potential graph neighborhoods

        Returns:
            GoalRelationships if found in rich context, None otherwise
        """
        graph_ctx = find_rich_graph_context(user_context, "goals", goal_uid)
        if graph_ctx is None:
            return None
        return GoalRelationships(
            supporting_habit_uids=rich_graph_uids(graph_ctx, "supporting_habits"),
            required_knowledge_uids=rich_graph_uids(graph_ctx, "required_knowledge"),
            sub_goal_uids=rich_graph_uids(graph_ctx, "sub_goals"),
            aligned_learning_path_uids=rich_graph_uids(graph_ctx, "aligned_paths"),
            supporting_principle_uids=rich_graph_uids(graph_ctx, "guiding_principles"),
        )

    # ========================================================================
    # PROGRESS CALCULATION
    # ========================================================================

    async def calculate_goal_progress_with_context(
        self, goal_uid: str, user_context: UserContext
    ) -> Result[dict[str, Any]]:
        """
        Calculate goal progress using full context awareness.

        Returns dict with:
        - progress_percentage: Overall progress
        - task_contribution: Progress from tasks
        - habit_contribution: Progress from habits
        - knowledge_completion: Ku prerequisites met
        - milestone_completion: Milestones completed

        **CONTEXT-FIRST PATTERN (November 26, 2025):**
        This method now uses the Context-First Pattern:
        - First tries to get goal from user_context.entities_rich["goals"]
        - First tries to get relationships from rich context graph_context
        - Only falls back to Neo4j queries if not in context
        - Reduces from 2 queries to 0 when context is available

        Args:
            goal_uid: Goal identifier,
            user_context: User's unified context

        Returns:
            Result containing progress breakdown dictionary
        """
        # CONTEXT-FIRST: Try to get goal from rich context before querying Neo4j
        goal = self._get_goal_from_rich_context(goal_uid, user_context)
        context_hit = goal is not None

        if goal is None:
            # Fallback: Query Neo4j directly
            goal_result = await self.backend.get_goal(goal_uid)
            if goal_result.is_error:
                return Result.fail(goal_result)
            goal = to_domain_model(goal_result.value, GoalDTO, Goal)
            self.logger.debug(f"Goal {goal_uid} fetched from Neo4j (not in rich context)")
        else:
            self.logger.debug(f"Goal {goal_uid} found in rich context (no Neo4j query needed)")

        # CONTEXT-FIRST: Try to get relationships from rich context
        rels = self._get_relationships_from_rich_context(goal_uid, user_context)
        if rels is not None:
            self.logger.debug(
                f"Goal relationships from rich context: {len(rels.supporting_habit_uids)} habits"
            )
        else:
            # Fallback: Fetch relationships from graph
            if self.relationships:
                rels = await GoalRelationships.fetch(goal_uid, self.relationships)
                self.logger.debug("Goal relationships from Neo4j")

        # Log context efficiency
        if context_hit:
            self.logger.info(
                f"Context-first: Goal {goal_uid} progress calculation used rich context (saved queries)"
            )

        # Get goal tasks from context
        goal_tasks = list(user_context.tasks_by_goal_or_empty().get(goal_uid, []))

        # Get supporting habit UIDs from relationships
        supporting_habit_uids = list(rels.supporting_habit_uids) if rels else []

        # Get required knowledge UIDs from relationships
        required_knowledge_uids = list(rels.required_knowledge_uids) if rels else []

        # Use ProgressCalculator for unified calculation
        progress = ProgressCalculator.calculate_full_progress(
            goal_tasks=goal_tasks,
            completed_task_uids=user_context.completed_task_uids,
            supporting_habit_uids=supporting_habit_uids,
            habit_streaks=user_context.habit_streaks,
            required_knowledge_uids=required_knowledge_uids,
            mastered_knowledge_uids=user_context.mastered_knowledge_uids,
            current_value=goal.current_value,
            target_value=goal.target_value if goal.target_value is not None else 100.0,
            measurement_type=goal.measurement_type or "mixed",
            expected_progress=goal.expected_progress_percentage(),
        )

        return Result.ok(
            {
                "progress_percentage": progress.combined_progress,
                "task_contribution": progress.task_contribution,
                "habit_contribution": progress.habit_contribution,
                "knowledge_completion": progress.knowledge_completion,
                "milestone_completion": progress.milestone_completion,
                "is_on_track": progress.is_on_track,
                "days_remaining": goal.days_remaining(),
            }
        )

    # ========================================================================
    # MILESTONE MANAGEMENT
    # ========================================================================

    async def _rewrite_goal(
        self, goal_uid: str, decide: Callable[[Goal], Result[_ProgressWrite]]
    ) -> Result[GuardedRecompute[Goal, _ProgressWrite]]:
        """Plan one rewrite from the goal under its lock and write it.

        ``decide`` reads the locked goal and answers the write, or the refusal its
        caller owes the client; a refusal writes nothing. A goal that does not exist
        is the backend's not found.

        Backend: ``rewrite_under_lock``.
        """
        refusals: list[Result[_ProgressWrite]] = []

        def plan(goal: Goal) -> _ProgressWrite | None:
            decided = decide(goal)
            if decided.is_error:
                refusals.append(decided)
                return None
            return decided.value

        result = await self.backend.rewrite_under_lock(goal_uid, plan)
        if result.is_error:
            return Result.fail(result)
        if result.value is None:
            if refusals:
                return Result.fail(refusals[0])
            return Result.fail(
                Errors.system(message=f"The rewrite of goal {goal_uid} wrote nothing.")
            )
        return Result.ok(result.value)

    async def create_goal_milestone(
        self,
        goal_uid: str,
        title: str,
        target_date: date | None = None,
        description: str | None = None,
    ) -> Result[Goal]:
        """Add one milestone to a goal; the goal as written.

        The milestone is appended to the list read under the goal's lock, so two adds
        at once keep both. On a milestone-measured goal the figure follows: one more
        open milestone lowers it, and a goal the last milestone had achieved is
        un-achieved (``_plan_milestones``).

        Args:
            goal_uid: Goal identifier
            title: What reaching the milestone means
            target_date: When it should be reached
            description: Optional detail

        Events Published:
            - GoalUpdated: always (context invalidation)
            - GoalProgressUpdated: when the figure moved
        """
        milestone = Milestone(
            uid=UIDGenerator.generate_random_uid("milestone"),
            title=title,
            description=description or None,
            target_date=target_date,
        )

        def append(goal: Goal) -> Result[_ProgressWrite]:
            return Result.ok(_plan_milestones(goal, [*goal.milestones, milestone]))

        rewrite = await self._rewrite_goal(goal_uid, append)
        if rewrite.is_error:
            return Result.fail(rewrite)
        plan, outcome = rewrite.value.plan, rewrite.value.outcome
        goal = outcome.entity
        owner = UserUID(str(goal.user_uid))

        self.logger.info(f"Added milestone {milestone.uid} to goal {goal_uid}")
        await publish_event(
            self.event_bus,
            GoalUpdated(goal_uid=goal_uid, user_uid=owner, updated_fields=["milestones"]),
            self.logger,
        )
        await self._publish_recompute(goal_uid, owner, plan, outcome.prior_status, trigger=None)
        return Result.ok(goal)

    async def complete_milestone(self, goal_uid: str, milestone_uid: str) -> Result[Goal]:
        """Mark one of a goal's milestones reached; the goal as written.

        The milestone is found by its uid in the list read under the goal's lock, so a
        milestone added or completed at the same moment is kept. Its ``achieved_date``
        records the first completion (today in the user's zone) and never moves: a
        repeat moves no stamp and announces nothing, and completing one reopened since
        (``reopen_milestone``) keeps the date it was first reached. On a
        milestone-measured goal the figure follows, and the completion that makes every
        milestone done achieves the goal (``_plan_milestones``); on any other type the
        milestones are a checklist.

        Args:
            goal_uid: Goal identifier
            milestone_uid: The milestone to complete; one the goal does not hold is
                not found

        Events Published:
            - GoalMilestoneReached: when the milestone was open (not on a repeat)
            - GoalProgressUpdated: when the figure moved
            - GoalAchieved: on the transition into completed
        """
        first_completion: list[float] = []

        def complete(goal: Goal) -> Result[_ProgressWrite]:
            milestones = list(goal.milestones)
            index = next((i for i, m in enumerate(milestones) if m.uid == milestone_uid), None)
            if index is None:
                return Result.fail(Errors.not_found("Milestone", milestone_uid))
            target = milestones[index]
            if not target.is_completed:
                milestones[index] = dataclasses.replace(
                    target,
                    is_completed=True,
                    achieved_date=target.achieved_date or today_in(current_zone()),
                )
                first_completion.append(
                    sum(1 for m in milestones if m.is_completed) / len(milestones)
                )
            return Result.ok(_plan_milestones(goal, milestones))

        rewrite = await self._rewrite_goal(goal_uid, complete)
        if rewrite.is_error:
            return Result.fail(rewrite)
        plan, outcome = rewrite.value.plan, rewrite.value.outcome
        goal = outcome.entity
        owner = UserUID(str(goal.user_uid))

        if first_completion:
            self.logger.info(f"Completed milestone {milestone_uid} of goal {goal_uid}")
            await publish_event(
                self.event_bus,
                GoalMilestoneReached(
                    goal_uid=goal_uid, user_uid=owner, milestone_percentage=first_completion[0]
                ),
                self.logger,
            )
        await self._publish_recompute(goal_uid, owner, plan, outcome.prior_status, trigger=None)
        return Result.ok(goal)

    async def reopen_milestone(self, goal_uid: str, milestone_uid: str) -> Result[Goal]:
        """Mark one of a goal's milestones not reached after all; the goal as written.

        The mirror of :meth:`complete_milestone`, under the same lock. The milestone keeps
        its ``achieved_date``: the day it was first reached, which a later completion
        does not move. On a milestone-measured goal the figure follows, and a fall from
        100 un-achieves the goal (``_plan_milestones``); on any other type the milestones
        are a checklist. Reopening an open milestone changes nothing.

        Args:
            goal_uid: Goal identifier
            milestone_uid: The milestone to reopen; one the goal does not hold is not
                found

        Events Published:
            - GoalUpdated: when the milestone was reached (context invalidation)
            - GoalProgressUpdated: when the figure moved
        """
        reopened: list[bool] = []

        def reopen(goal: Goal) -> Result[_ProgressWrite]:
            milestones = list(goal.milestones)
            index = next((i for i, m in enumerate(milestones) if m.uid == milestone_uid), None)
            if index is None:
                return Result.fail(Errors.not_found("Milestone", milestone_uid))
            target = milestones[index]
            if target.is_completed:
                milestones[index] = dataclasses.replace(target, is_completed=False)
                reopened.append(True)
            return Result.ok(_plan_milestones(goal, milestones))

        rewrite = await self._rewrite_goal(goal_uid, reopen)
        if rewrite.is_error:
            return Result.fail(rewrite)
        plan, outcome = rewrite.value.plan, rewrite.value.outcome
        goal = outcome.entity
        owner = UserUID(str(goal.user_uid))

        if reopened:
            self.logger.info(f"Reopened milestone {milestone_uid} of goal {goal_uid}")
            await publish_event(
                self.event_bus,
                GoalUpdated(goal_uid=goal_uid, user_uid=owner, updated_fields=["milestones"]),
                self.logger,
            )
        await self._publish_recompute(goal_uid, owner, plan, outcome.prior_status, trigger=None)
        return Result.ok(goal)

    async def handle_goal_reopened(self, event: GoalReopened) -> None:
        """Give a reopened goal the figure its measure gives.

        Best-effort, like the other progress subscribers: a failure is logged, never
        raised, so a recompute cannot fail the reopen that triggered it.
        """
        try:
            result = await self.restore_figure_from_measure(event.goal_uid, event.user_uid)
        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(f"Failed to restore reopened goal {event.goal_uid}'s figure: {e}")
            return
        if result.is_error:
            self.logger.error(
                f"Failed to restore reopened goal {event.goal_uid}'s figure: {result.error}"
            )

    async def restore_figure_from_measure(self, goal_uid: str, user_uid: UserUID) -> Result[bool]:
        """Rewrite a goal's percentage from the measure its type names, status untouched.

        Run on a reopen. ``complete_goal`` writes 100% on every type, so a goal completed
        by hand at 2 of 5 tasks would reopen at a figure its measure contradicts; this
        writes the measure's figure (the contribution tally, the habits' streaks, the
        milestones, ``current_value`` against ``target_value``) through the same planner
        that type's writer uses, under the goal's lock, with the status half taken off
        (:func:`_without_status`). A goal whose percentage is the whole measurement has no
        other source, and a numeric goal with no target has no figure to give: both are
        left alone. ``Result.ok(True)`` when the goal was written.

        Backend: ``rewrite_under_lock``, ``recompute_progress_from_contributions``,
        ``recompute_progress_from_linked_habits``.
        """
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)
        goal = goal_result.value
        if goal is None:
            return Result.ok(False)
        measurement = goal.measurement_type or MeasurementType.PERCENTAGE

        if measurement is MeasurementType.TASK_BASED:
            tallied = await self.backend.recompute_progress_from_contributions(
                goal_uid, _contribution_figure
            )
            trigger: Literal["contributions", "habits"] | None = "contributions"
        elif measurement is MeasurementType.HABIT_BASED:
            tallied = await self.backend.recompute_progress_from_linked_habits(
                goal_uid, _habit_figure
            )
            trigger = "habits"
        elif measurement.follows_milestones() or (
            measurement.entered_in_units() and goal.target_value
        ):
            return await self._restore_node_figure(goal_uid, user_uid)
        else:
            return Result.ok(False)

        if tallied.is_error:
            return Result.fail(tallied)
        if tallied.value is None:
            return Result.ok(False)
        plan, outcome = tallied.value.plan, tallied.value.outcome
        await self._publish_recompute(
            goal_uid, user_uid, plan, outcome.prior_status, trigger=trigger
        )
        return Result.ok(True)

    async def _restore_node_figure(self, goal_uid: str, user_uid: UserUID) -> Result[bool]:
        """The figure of a goal whose measure is on its own node (milestones, units),
        planned from the goal read under its lock. See :meth:`restore_figure_from_measure`.
        """

        def from_node(goal: Goal) -> Result[_ProgressWrite]:
            measurement = goal.measurement_type or MeasurementType.PERCENTAGE
            if measurement.entered_in_units():
                entered = _plan_entered_figure(goal, goal.current_value or 0.0, "", datetime.now())
                if entered.is_error:
                    return entered
                return Result.ok(_without_status(entered.value))
            return Result.ok(_without_status(_plan_milestones(goal, list(goal.milestones))))

        rewrite = await self._rewrite_goal(goal_uid, from_node)
        if rewrite.is_error:
            return Result.fail(rewrite)
        plan, outcome = rewrite.value.plan, rewrite.value.outcome
        await self._publish_recompute(goal_uid, user_uid, plan, outcome.prior_status, trigger=None)
        return Result.ok(True)

    # ========================================================================
    # VELOCITY & FORECASTING HELPERS
    # ========================================================================

    def calculate_velocity_metrics(
        self, goal: Goal, tally: ContributionTally, habit_adherence: float | None
    ) -> dict[str, float]:
        """
        Calculate velocity metrics from the goal's progress tally and habit adherence.

        Args:
            goal: Goal object for progress calculation,
            tally: The goal's contribution tally (``GoalsBackend.get_contribution_tally``)
                — the contributions that count toward it, by the rule its progress is
                written by,
            habit_adherence: The essentiality-weighted mean adherence of the goal's
                supporting habits, 0-1 (``dashboard_figures.habit_support_adherence``);
                ``None`` when no supporting habit has a rate yet

        Returns:
            Dict containing:
            - total_tasks: the tally's counting contributions
            - completed_tasks: the completed ones among them
            - task_completion_velocity: Tasks per week estimate
            - habit_consistency_score: the habits' adherence, 0-1; 0.5 (neutral)
              when no supporting habit has a rate
            - current_progress_rate: Progress % per week estimate
        """
        # Calculate velocity metrics (simple heuristics)
        total_tasks = tally["total_contributions"]
        completed_tasks = tally["completed_contributions"]
        task_completion_velocity = (
            completed_tasks / 4.0 if completed_tasks > 0 else 0
        )  # per week estimate

        # No measurement is neutral, not a zero.
        habit_consistency_score = 0.5 if habit_adherence is None else habit_adherence

        # Progress rate (% per week estimate)
        current_progress_rate = (
            goal.progress_percentage / 4.0 if goal.progress_percentage > 0 else 0
        )

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "task_completion_velocity": task_completion_velocity,
            "habit_consistency_score": habit_consistency_score,
            "current_progress_rate": current_progress_rate,
        }

    def generate_forecast(self, goal: Goal, current_progress_rate: float) -> dict[str, Any]:
        """
        Generate completion forecast based on current progress rate.

        Args:
            goal: Goal object with progress and target date,
            current_progress_rate: Current progress % per week

        Returns:
            Dict containing:
            - estimated_completion_date: Projected completion date
            - days_ahead_or_behind: Days ahead (positive) or behind (negative) schedule
            - completion_probability: Probability of completion (0-1)
        """
        estimated_completion_date = None
        days_ahead_or_behind = 0
        completion_probability = 0.5

        if goal.target_date and current_progress_rate > 0:
            remaining_progress = 100 - goal.progress_percentage
            weeks_to_complete = (
                remaining_progress / current_progress_rate if current_progress_rate > 0 else 999
            )
            days_to_complete = int(weeks_to_complete * 7)
            estimated_completion_date = today_in(current_zone()) + timedelta(days=days_to_complete)
            days_ahead_or_behind = (goal.target_date - estimated_completion_date).days

            # Completion probability based on current pace
            if days_ahead_or_behind > 0:
                completion_probability = min(0.95, 0.7 + (days_ahead_or_behind / 30.0) * 0.25)
            else:
                completion_probability = max(0.3, 0.7 - (abs(days_ahead_or_behind) / 30.0) * 0.4)

        return {
            "estimated_completion_date": estimated_completion_date,
            "days_ahead_or_behind": days_ahead_or_behind,
            "completion_probability": completion_probability,
        }

    def calculate_timeline_analysis(
        self, goal: Goal, velocity_metrics: dict[str, float], days_ahead_or_behind: int
    ) -> dict[str, Any]:
        """
        Calculate timeline analysis including required velocity and current pace.

        Args:
            goal: Goal object with target date,
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            days_ahead_or_behind: Days ahead (positive) or behind (negative)

        Returns:
            Dict containing:
            - target_date: Goal's target date
            - days_remaining: Days until target date
            - required_velocity: Tasks per week needed to complete on time
            - current_pace: "ahead", "on_track", or "behind"
            - confidence_level: Confidence in forecast (0-1)
        """
        total_tasks = velocity_metrics["total_tasks"]
        completed_tasks = velocity_metrics["completed_tasks"]
        habit_consistency_score = velocity_metrics["habit_consistency_score"]

        # Timeline analysis
        days_remaining = None
        required_velocity: float = 0
        if goal.target_date:
            days_remaining = (goal.target_date - today_in(current_zone())).days
            if days_remaining > 0:
                remaining_tasks = total_tasks - completed_tasks
                required_velocity = (remaining_tasks / days_remaining) * 7  # tasks per week

        # Determine pace
        current_pace = "unknown"
        if days_ahead_or_behind > 7:
            current_pace = "ahead"
        elif days_ahead_or_behind >= -7:
            current_pace = "on_track"
        else:
            current_pace = "behind"

        # Confidence level
        confidence_level = habit_consistency_score * 0.6 + (0.4 if total_tasks > 3 else 0.2)

        return {
            "target_date": goal.target_date,
            "days_remaining": days_remaining,
            "required_velocity": required_velocity,
            "current_pace": current_pace,
            "confidence_level": confidence_level,
        }

    def identify_risk_factors(
        self, velocity_metrics: dict[str, float], context: GoalCrossContext
    ) -> list[str]:
        """
        Identify risk factors that may prevent goal completion.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: The goal's path-aware context — its supporting habits

        Returns:
            List of risk factor descriptions
        """
        total_tasks = velocity_metrics["total_tasks"]
        habit_consistency_score = velocity_metrics["habit_consistency_score"]
        current_progress_rate = velocity_metrics["current_progress_rate"]

        supporting_habits = context.habits

        risk_factors = []
        if total_tasks < 3:
            risk_factors.append("Too few tasks defined - goal may lack concrete action plan")
        if habit_consistency_score < 0.5:
            risk_factors.append("Low habit consistency - supporting routines are inconsistent")
        if current_progress_rate < 2.0:
            risk_factors.append("Slow progress rate - may not complete on time")
        if len(supporting_habits) == 0:
            risk_factors.append("No supporting habits - progress relies entirely on ad-hoc tasks")

        return risk_factors

    def identify_acceleration_opportunities(
        self,
        velocity_metrics: dict[str, float],
        context: GoalCrossContext,
        required_velocity: float,
    ) -> list[str]:
        """
        Identify opportunities to accelerate goal progress.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: The goal's path-aware context — its supporting habits,
            required_velocity: Required tasks per week from timeline analysis

        Returns:
            List of acceleration opportunity descriptions
        """
        completed_tasks = velocity_metrics["completed_tasks"]
        task_completion_velocity = velocity_metrics["task_completion_velocity"]

        supporting_habits = context.habits

        acceleration_opportunities = []
        if len(supporting_habits) < 2:
            acceleration_opportunities.append("Create daily/weekly habits to build momentum")
        if task_completion_velocity < required_velocity:
            acceleration_opportunities.append("Increase task completion rate to meet timeline")
        if completed_tasks == 0:
            acceleration_opportunities.append(
                "Start completing tasks to establish velocity baseline"
            )

        return acceleration_opportunities

    # ========================================================================
    # API SUPPORT METHODS
    # ========================================================================

    async def update_goal_progress(
        self, uid: str, progress_value: float, note: str = "", update_date: str | None = None
    ) -> Result[Goal]:
        """Record the figure the learner enters for a goal; the goal as written.

        What the value means is the goal's measurement type's to say
        (``MeasurementType``): on a numeric goal it is a value in the goal's own unit,
        stored as ``current_value`` with the percentage derived against
        ``target_value``; on the other entered types it is the percentage, 0-100. A
        goal whose figure is derived (task-based, habit-based, milestone) takes no
        entered figure and refuses one. Planned from the goal under its lock.

        Status follows the figure as it does for a recompute
        (``_recompute_status_write``): rising to 100 achieves the goal unless its owner
        settled it, falling from 100 un-achieves it.

        Args:
            uid: Goal UID
            progress_value: The entered figure
            note: The learner's note on this entry, if any (stored on the
                history entry the write appends, the figure moved or not)
            update_date: The date the progress happened (ISO date or datetime),
                when it is not now — a September correction entered in October
                is a September event. Unparseable or in the future: validation
                failure.

        Events Published:
            - GoalProgressUpdated: when the percentage moved
            - GoalAchieved: on the transition into completed
        """
        at = datetime.now()
        if update_date:
            parsed = _parse_progress_date(update_date)
            if parsed is None:
                return Result.fail(
                    Errors.validation(
                        message=f"Invalid update_date {update_date!r}", field="update_date"
                    )
                )
            if as_utc(parsed) > now_utc():
                return Result.fail(
                    Errors.validation(
                        message="update_date cannot be in the future", field="update_date"
                    )
                )
            at = parsed

        def enter(goal: Goal) -> Result[_ProgressWrite]:
            return _plan_entered_figure(goal, progress_value, note, at)

        rewrite = await self._rewrite_goal(uid, enter)
        if rewrite.is_error:
            return Result.fail(rewrite)
        plan, outcome = rewrite.value.plan, rewrite.value.outcome
        goal = outcome.entity
        await self._publish_recompute(
            uid, UserUID(str(goal.user_uid)), plan, outcome.prior_status, trigger="manual"
        )
        return Result.ok(goal)

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_goal_contributions_changed(self, event: GoalContributionsChanged) -> None:
        """Recompute every goal whose contributions the event says may have changed.

        The goals are the ones the event names (a removed contribution, captured before
        its edge went) and the ones each named contributor contributes to now. The
        recompute counts graph state, so a doubled or redundant announcement is harmless.
        Event-driven, so the task, event and ingestion services hold no dependency on
        GoalsService. Best-effort: a failure is logged, never raised.

        Backend: GoalsBackend.find_contributed_goals.
        """
        goal_uids: list[str] = list(dict.fromkeys(event.goal_uids))
        for contributor_uid in event.contributor_uids:
            result = await self.backend.find_contributed_goals(contributor_uid, event.user_uid)
            if result.is_error:
                self.logger.error(
                    f"Failed to query goals for contributor {contributor_uid}: {result.error}"
                )
                continue
            goal_uids.extend(g for g in result.value or [] if g not in goal_uids)

        for goal_uid in goal_uids:
            try:
                await self.recompute_goal_tally(goal_uid)
            except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                self.logger.error(f"Failed to update goal {goal_uid} progress: {e}")

    async def recompute_goal_tally(self, goal_uid: str) -> Result[bool]:
        """Recompute one TASK_BASED goal from its contribution tally, and publish the result.

        The tally, the figure and the status verdict are all decided under the goal's
        write-lock (``GoalsBackend.recompute_progress_from_contributions``), so two
        recomputes of one goal serialize: the later one counts every contribution the
        earlier one's trigger had changed, and a count taken before a concurrent change
        can never land after it. ``Result.ok(True)`` when the goal was written.

        A goal that no longer exists (deleted with the contribution that named it) is
        nothing to write: ``Result.ok(False)``.

        Args:
            goal_uid: Goal to update — counted against its own owner's contributions
        """
        result = await self.backend.recompute_progress_from_contributions(
            goal_uid, _plan_contribution_progress
        )
        if result.is_error:
            if result.expect_error().category is ErrorCategory.NOT_FOUND:
                self.logger.debug(f"Goal {goal_uid}: gone, no tally to write")
                return Result.ok(False)
            self.logger.error(f"Failed to recompute goal {goal_uid}: {result.error}")
            return Result.fail(result)
        if result.value is None:
            self.logger.debug(f"Goal {goal_uid}: no contribution-based progress change")
            return Result.ok(False)

        plan, outcome = result.value.plan, result.value.outcome
        owner = UserUID(str(outcome.entity.user_uid))
        self.logger.info(
            f"Updated goal {goal_uid}: {plan.old_progress:.1f}% → {plan.new_progress:.1f}% "
            f"({plan.detail})"
        )
        await self._publish_recompute(
            goal_uid, owner, plan, outcome.prior_status, trigger="contributions"
        )
        return Result.ok(True)

    async def reconcile_goal_tallies(self, *, dry_run: bool) -> Result[list[GoalTallyGap]]:
        """Recompute every derived goal figure that disagrees with what it is derived from.

        A TASK_BASED goal's tally follows its contributions (``GoalContributionsChanged``)
        and a HABIT_BASED goal's figure follows its supporting habits (``GoalHabitsChanged``
        and ``HabitCompleted``). Each trigger is best-effort: a recompute that fails after
        the change it answers has committed leaves the stored figure behind, and nothing
        replays the event. This reads every goal of the two types, plans its write under
        the rule its recompute uses (``_plan_contribution_progress`` /
        ``_plan_habit_progress``) and, unless ``dry_run``, closes each gap through the
        same locked recompute. Idempotent: a second run finds nothing.

        Backend: GoalsBackend.list_goals_by_measurement / get_contribution_tally /
        get_linked_habit_tally.
        """
        gaps: list[GoalTallyGap] = []
        task_gaps = await self._reconcile_measure(
            MeasurementType.TASK_BASED,
            self.backend.get_contribution_tally,
            _plan_contribution_progress,
            self.recompute_goal_tally,
            dry_run=dry_run,
        )
        if task_gaps.is_error:
            return Result.fail(task_gaps)
        gaps.extend(task_gaps.value)
        habit_gaps = await self._reconcile_measure(
            MeasurementType.HABIT_BASED,
            self.backend.get_linked_habit_tally,
            _plan_habit_progress,
            self.recompute_habit_figure,
            dry_run=dry_run,
        )
        if habit_gaps.is_error:
            return Result.fail(habit_gaps)
        gaps.extend(habit_gaps.value)
        return Result.ok(gaps)

    async def _reconcile_measure[Tally](
        self,
        measurement_type: MeasurementType,
        read_tally: Callable[[str], Awaitable[Result[Tally]]],
        plan: Callable[[Goal, Tally], _ProgressWrite | None],
        recompute: Callable[[str], Awaitable[Result[bool]]],
        *,
        dry_run: bool,
    ) -> Result[list[GoalTallyGap]]:
        """One measurement type's half of :meth:`reconcile_goal_tallies`."""
        goals = await self.backend.list_goals_by_measurement(measurement_type)
        if goals.is_error:
            return Result.fail(goals)
        gaps: list[GoalTallyGap] = []
        for goal_uid, owner_uid in goals.value:
            goal_result = await self.backend.get(goal_uid)
            if goal_result.is_error:
                return Result.fail(goal_result)
            if goal_result.value is None:
                continue
            goal = to_domain_model(goal_result.value, GoalDTO, Goal)
            tally = await read_tally(goal_uid)
            if tally.is_error:
                return Result.fail(tally)
            planned = plan(goal, tally.value)
            if planned is None:
                continue
            gaps.append(
                GoalTallyGap(
                    goal_uid=goal_uid,
                    user_uid=owner_uid,
                    stored=f"{goal.current_value}/{goal.target_value}",
                    live=planned.detail,
                )
            )
            if not dry_run:
                written = await recompute(goal_uid)
                if written.is_error:
                    return Result.fail(written)
        return Result.ok(gaps)

    async def handle_habit_completed(self, event: HabitCompleted) -> None:
        """Recompute the goals a habit supports after one of its completions.

        Event-driven, so HabitsService holds no dependency on GoalsService. Best-effort:
        a failure is logged, never raised, so a goal update cannot fail the completion.

        Args:
            event: HabitCompleted carrying habit_uid, user_uid and current_streak
        """
        await self._recompute_habit_goals(event.user_uid, (), (event.habit_uid,))

    async def handle_goal_habits_changed(self, event: GoalHabitsChanged) -> None:
        """Recompute every goal whose supporting habits the event says may have changed.

        The goals are the ones the event names (a goal whose links a door changed, a
        removed habit's goals captured before its edge went) and the ones each named
        habit supports now. The recompute counts graph state, so a doubled or redundant
        announcement is harmless. Event-driven, so the habit, engagement and ingestion
        services hold no dependency on GoalsService. Best-effort: a failure is logged,
        never raised.
        """
        await self._recompute_habit_goals(event.user_uid, event.goal_uids, event.habit_uids)

    async def _recompute_habit_goals(
        self, user_uid: UserUID, goal_uids: tuple[str, ...], habit_uids: tuple[str, ...]
    ) -> None:
        """Recompute each goal named and each goal the named habits support, once each.

        Backend: GoalsBackend.find_linked_goals_for_habit.
        """
        goals: list[str] = list(dict.fromkeys(goal_uids))
        for habit_uid in habit_uids:
            try:
                found = await self.backend.find_linked_goals_for_habit(habit_uid, user_uid)
            except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                self.logger.error(f"Failed to query goals for habit {habit_uid}: {e}")
                continue
            if found.is_error:
                self.logger.error(f"Failed to query goals for habit {habit_uid}: {found.error}")
                continue
            goals.extend(g for g in found.value or [] if g not in goals)

        for goal_uid in goals:
            try:
                recomputed = await self.recompute_habit_figure(goal_uid)
                if recomputed.is_error:
                    self.logger.error(
                        f"Failed to recompute goal {goal_uid}: {recomputed.expect_error()}"
                    )
            except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                # Best-effort: one goal's failure does not block the others.
                self.logger.error(f"Failed to update goal {goal_uid} from its habits: {e}")

    async def recompute_habit_figure(self, goal_uid: str) -> Result[bool]:
        """Recompute one HABIT_BASED goal from its owner's supporting habits, and publish
        the result. ``Result.ok(True)`` when the goal was written.

        Progress is ``avg_streak / target_value * 100``, capped at 100 — target_value is
        the desired streak length; a goal with no supporting habit is written 0. Decided
        under the goal's write-lock, like the task-based sibling, so a habit completed
        while another is linked is counted by whichever recompute runs second. Run after
        a habit completion and after every change to the goal's habit links; any other
        measurement type is left alone. A goal that no longer exists (deleted with the
        habit that named it) is nothing to write: ``Result.ok(False)``.

        Backend: ``GoalsBackend.recompute_progress_from_linked_habits``.
        """
        result = await self.backend.recompute_progress_from_linked_habits(
            goal_uid, _plan_habit_progress
        )
        if result.is_error:
            if result.expect_error().category is ErrorCategory.NOT_FOUND:
                self.logger.debug(f"Goal {goal_uid}: gone, no habit figure to write")
                return Result.ok(False)
            return Result.fail(result)
        if result.value is None:
            self.logger.debug(f"Goal {goal_uid}: no habit-based progress change")
            return Result.ok(False)

        plan, outcome = result.value.plan, result.value.outcome
        self.logger.info(
            f"Updated goal {goal_uid}: {plan.old_progress:.1f}% → {plan.new_progress:.1f}% "
            f"({plan.detail})"
        )
        await self._publish_recompute(
            goal_uid,
            UserUID(str(outcome.entity.user_uid)),
            plan,
            outcome.prior_status,
            trigger="habits",
        )
        return Result.ok(True)

    async def _publish_recompute(
        self,
        goal_uid: str,
        user_uid: UserUID,
        plan: _ProgressWrite,
        prior_status: str | None,
        *,
        trigger: Literal["contributions", "habits", "manual"] | None,
    ) -> None:
        """Announce what a recompute wrote, with verdicts from the prior the write saw.

        ``GoalProgressUpdated`` only when the percentage moved:
        ``GoalEventHandlerService.handle_goal_progress_updated`` reads a near-zero delta
        on a positive goal as a STALL and persists an IMBALANCE_DETECTED insight, so a
        tally-only repair stays quiet. ``GoalAchieved`` only on the transition INTO
        completed, decided from the prior the write captured, so a goal another writer
        completed first is not announced twice, and a settled goal (``_SETTLED``), which
        the write did not achieve, is not announced at all.

        ``trigger`` is the write's provenance, as ``GoalProgressUpdated`` names it; a
        milestone write has none of the three.
        """
        if plan.progress_changed:
            await publish_event(
                self.event_bus,
                GoalProgressUpdated(
                    goal_uid=goal_uid,
                    user_uid=user_uid,
                    old_progress=plan.old_progress,
                    new_progress=plan.new_progress,
                    triggered_by_contribution_change=trigger == "contributions",
                    triggered_by_habit_completion=trigger == "habits",
                    triggered_by_manual_update=trigger == "manual",
                ),
                self.logger,
            )

        if prior_status not in _SETTLED and is_completion_transition(
            prior_status, plan.achievement
        ):
            await publish_event(
                self.event_bus, GoalAchieved(goal_uid=goal_uid, user_uid=user_uid), self.logger
            )
            self.logger.info(f"🎉 Goal {goal_uid} achieved!")
        elif is_reopen_transition(prior_status, plan.unachievement):
            self.logger.info(f"Goal {goal_uid} un-achieved: progress fell below 100%")
