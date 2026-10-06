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
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from core.events import (
    GoalAchieved,
    GoalContributionsChanged,
    GoalMilestoneReached,
    GoalProgressUpdated,
    publish_event,
)
from core.models.enums import Domain, EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.graph_context import GraphContext
from core.models.type_hints import Neo4jProperties, UserUID
from core.models.update_contracts import StatusWriteGuard
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
    day_of,
    from_wall_clock,
    instant_of,
    now_utc,
    today_in,
)
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

    Each progress writer below derives its own achievement TARGET in Python — "every
    milestone is done now", "progress reached 100" — and that half stays a pre-read,
    because it is a statement about the NEW state. The other half of the old
    ``goal_achieved_now`` local, *"…and it was not already achieved"*, is a fact only the
    write knows: it depends on the status the node holds at write time, which a
    concurrent writer can move between this call's read and its write. So it becomes the
    guard's condition — the status/stamp pair merges only when the prior was not already
    COMPLETED. Re-completing a milestone of a finished goal therefore cannot re-date
    ``achieved_date``, and neither can a race.

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
    """A TASK_BASED goal whose stored tally disagrees with its contributions."""

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
    """Plan a HABIT_BASED goal's write from its habits' average streak; ``None`` for none.

    Runs under the goal's lock (``GoalsBackend.recompute_progress_from_linked_habits``).
    """
    # Only HABIT_BASED goals — MIXED for the reason given in _plan_contribution_progress.
    if goal.measurement_type != MeasurementType.HABIT_BASED:
        return None

    total_habits = tally["total_habits"]
    avg_streak = tally["avg_streak"]
    if total_habits == 0:
        return None

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


if TYPE_CHECKING:
    from core.events.habit_events import HabitCompleted
    from core.services.relationships import UnifiedRelationshipService


#: The trailing window each ``get_goal_progress`` period names, in days.
_PROGRESS_PERIOD_DAYS: dict[str, int] = {"week": 7, "month": 30, "quarter": 90, "year": 365}


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

    async def complete_milestone(
        self, goal_uid: str, milestone_index: int, user_context: UserContext
    ) -> Result[Goal]:
        """
        Mark a milestone as complete and update goal progress.

        Args:
            goal_uid: Goal identifier,
            milestone_index: Index of milestone to complete,
            user_context: User's unified context

        Returns:
            Result containing updated Goal
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        if not goal.milestones or milestone_index >= len(goal.milestones):
            return Result.fail(
                Errors.validation(
                    message=f"Milestone index {milestone_index} is out of range",
                    field="milestone_index",
                    value=milestone_index,
                    user_message=f"Please provide a valid milestone index (0-{len(goal.milestones) - 1 if goal.milestones else 0})",
                )
            )

        # Update milestone (Milestone is a frozen dataclass)
        from dataclasses import replace

        updated_milestones = list(goal.milestones)
        target_milestone = updated_milestones[milestone_index]
        # The milestone stamp records when this milestone was FIRST completed —
        # ``achieved_date`` is documented as "when actually achieved". Completing an
        # already-completed milestone is a legal, reachable call, and stamping it
        # unconditionally moved that date to today on every such call: the same
        # mutable-completion-stamp defect the goal-level gate below fixes, one level
        # down. ``is_completed`` needs no gate — it is already idempotent (True → True).
        # An already-completed milestone whose date is null stays null: a repeat is not
        # a transition, so there is no moment here to record. That matches the task
        # stamp gate (#1125), which likewise never backfills on a repeat.
        updated_milestones[milestone_index] = replace(
            target_milestone,
            is_completed=True,
            achieved_date=(
                target_milestone.achieved_date
                if target_milestone.is_completed
                else today_in(current_zone())
            ),
        )

        # Calculate new progress
        completed_count = sum(1 for m in updated_milestones if m.is_completed)
        new_progress = (completed_count / len(updated_milestones)) * 100

        # Achievement is the TRANSITION into "every milestone done", not the state.
        # Re-completing a milestone of an already-achieved goal is a legal, reachable
        # call, and the count alone would re-stamp achieved_date to today and re-publish
        # GoalAchieved on each one — a mutable completion stamp.
        #
        # Only the TARGET half is decided here. "Already achieved" is the goal's own
        # completion STATUS, not "every milestone is flagged done": the two diverge after
        # a reopen, which clears achieved_date and resets progress_percentage
        # (GoalsCoreService.update_goal) but leaves the milestone flags alone, so a
        # milestone-flag proxy would stay true forever and a genuine re-achievement would
        # never stamp or publish again. That status half now belongs to the write, which
        # reads it under the node's lock (ADR-087) instead of from the `goal` fetched
        # above — the same signal, read at the moment it is acted on.
        target_achieved = completed_count == len(updated_milestones)

        # Update goal. The progress stamp is a TRANSITION record: only a milestone
        # moving into completed is a progress event. A repeat leaves the count, the
        # figure and the stamp exactly where they were, so a re-posted completion in
        # a later period cannot make the report count the goal as progressed then.
        updates: dict[str, Any] = {
            "milestones": updated_milestones,
            "progress_percentage": new_progress,
            "current_value": completed_count,
        }
        if not target_milestone.is_completed:
            now = datetime.now()
            updates["last_progress_update"] = now
            updates["progress_history"] = with_progress_entry(goal, new_progress, now)
        guard, achievement = _achievement_write(target_achieved)

        update_result = await self.backend.update_with_status_guard(goal_uid, updates, guard)
        if update_result.is_error:
            return Result.fail(update_result)

        # Context invalidation happens via GoalMilestoneReached/GoalAchieved events (event-driven architecture)
        # Event handlers in bootstrap will call user_service.invalidate_context()

        # This guard refuses nothing, so the write always applied; the prior it returned
        # is what decides the achievement below.
        outcome = update_result.value
        updated_goal = outcome.entity
        goal_achieved_now = is_completion_transition(outcome.prior_status, achievement)

        self.logger.info(f"Completed milestone {milestone_index} for goal {goal_uid}")

        # Publish GoalMilestoneReached event
        # Calculate milestone percentage (e.g., milestone 0 of 4 = 0.25, milestone 2 of 4 = 0.75)
        milestone_percentage = (milestone_index + 1) / len(updated_milestones)
        milestone_event = GoalMilestoneReached(
            goal_uid=goal_uid,
            user_uid=user_context.user_uid,
            milestone_percentage=milestone_percentage,
        )
        await publish_event(self.event_bus, milestone_event, self.logger)

        # Publish GoalAchieved only on the transition — GoalEventHandlerService
        # appends a PRINCIPLE_ALIGNMENT PersistedInsight per event, under a UID
        # carrying a per-second timestamp, so a re-publish duplicates the row.
        if goal_achieved_now:
            achieved_event = GoalAchieved(
                goal_uid=goal_uid,
                user_uid=user_context.user_uid,
                actual_duration_days=(
                    today_in(current_zone()) - day_of(goal.created_at, current_zone())
                ).days
                if goal.created_at
                else None,
                completed_ahead_of_schedule=today_in(current_zone()) < goal.target_date
                if goal.target_date
                else False,
            )
            await publish_event(self.event_bus, achieved_event, self.logger)

        return Result.ok(updated_goal)

    # ========================================================================
    # HABIT INTEGRATION
    # ========================================================================

    async def update_goal_from_habit_progress(
        self, goal_uid: str, habit_uid: str, new_streak: int
    ) -> Result[Goal]:
        """
        Update goal progress based on habit streak changes.

        Args:
            goal_uid: Goal identifier,
            habit_uid: Habit that was updated,
            new_streak: New streak count for the habit

        Returns:
            Result containing updated Goal (or unchanged if not habit-based)
        """
        goal_result = await self.backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # GRAPH-NATIVE: Fetch relationships from graph
        rels = None
        if self.relationships:
            from core.services.goals.goal_relationships import GoalRelationships

            rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        # Only update if this is a habit-based goal
        if (
            not rels
            or goal.measurement_type != "habit_based"
            or habit_uid not in rels.supporting_habit_uids
        ):
            return Result.ok(goal)

        # Build habit streaks dict (use new_streak for the updated habit)
        habit_streaks = {
            h_uid: new_streak if h_uid == habit_uid else 0 for h_uid in rels.supporting_habit_uids
        }

        # Use ProgressCalculator for habit contribution
        habit_result = ProgressCalculator.calculate_habit_contribution(
            habit_uids=list(rels.supporting_habit_uids),
            habit_streaks=habit_streaks,
        )

        if habit_result.habit_count > 0:
            new_progress = habit_result.contribution * 100
            old_progress = goal.progress_percentage or 0.0

            # current_value is untouched: the contribution is normalized against
            # STREAK_NORMALIZATION_DAYS, not against this goal's target_value, so
            # there is no measurement in target_value's unit to record here.
            updates: dict[str, Any] = {"progress_percentage": new_progress}
            # The progress stamp records a CHANGE: a streak advancing past the
            # normalization window recomputes to the same capped figure, and that
            # is not a progress event a period report should count.
            if abs(new_progress - old_progress) >= 0.01:
                now = datetime.now()
                updates["last_progress_update"] = now
                updates["progress_history"] = with_progress_entry(goal, new_progress, now)

            # Check if goal is achieved — on the TRANSITION, matching the gate in
            # _update_goal_from_habit_completion. `>= 100` alone re-stamps
            # achieved_date on every later streak report once the streak has reached its
            # normalization window (30 -> 31 days is 100% both times), moving the
            # recorded achievement to today. The percentage crossing is this recompute's
            # TARGET derivation and stays here; whether the goal was ALREADY completed is
            # the write's to decide, under the node's lock (ADR-087).
            target_achieved = new_progress >= 100 and old_progress < 100
            guard, achievement = _achievement_write(target_achieved)

            update_result = await self.backend.update_with_status_guard(goal_uid, updates, guard)
            if update_result.is_error:
                return Result.fail(update_result)

            # This guard refuses nothing, so the write always applied.
            outcome = update_result.value
            updated_goal = outcome.entity
            goal_achieved_now = is_completion_transition(outcome.prior_status, achievement)

            self.logger.info(
                f"Updated goal {goal_uid} progress from habit {habit_uid} to {new_progress:.1f}%"
            )

            # Publish GoalProgressUpdated event
            progress_event = GoalProgressUpdated(
                goal_uid=goal_uid,
                user_uid=goal.user_uid,
                old_progress=goal.progress_percentage,
                new_progress=new_progress,
            )
            await publish_event(self.event_bus, progress_event, self.logger)

            # Publish GoalAchieved only on the transition — GoalEventHandlerService
            # appends a PRINCIPLE_ALIGNMENT PersistedInsight per event, under a UID
            # carrying a per-second timestamp, so a re-publish duplicates the row.
            if goal_achieved_now:
                achieved_event = GoalAchieved(
                    goal_uid=goal_uid,
                    user_uid=goal.user_uid,
                    actual_duration_days=(
                        today_in(current_zone()) - day_of(goal.created_at, current_zone())
                    ).days
                    if goal.created_at
                    else None,
                    completed_ahead_of_schedule=today_in(current_zone()) < goal.target_date
                    if goal.target_date
                    else False,
                )
                await publish_event(self.event_bus, achieved_event, self.logger)

            return Result.ok(updated_goal)

        return Result.ok(goal)

    # ========================================================================
    # VELOCITY & FORECASTING HELPERS
    # ========================================================================

    def calculate_velocity_metrics(self, context: GraphContext, goal: Goal) -> dict[str, float]:
        """
        Calculate velocity metrics from graph context.

        Args:
            context: Graph context with supporting activities,
            goal: Goal object for progress calculation

        Returns:
            Dict containing:
            - total_tasks: Total task count
            - completed_tasks: Completed task count
            - task_completion_velocity: Tasks per week estimate
            - habit_consistency_score: 0-1 consistency score
            - current_progress_rate: Progress % per week estimate
        """
        # Extract data for velocity calculation
        supporting_tasks = context.get_nodes_by_domain(Domain.TASKS)
        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

        # Calculate velocity metrics (simple heuristics)
        total_tasks = len(supporting_tasks)
        completed_tasks = sum(
            1 for t in supporting_tasks if t.properties.get("status") in ["completed", "done"]
        )
        task_completion_velocity = (
            completed_tasks / 4.0 if completed_tasks > 0 else 0
        )  # per week estimate

        # Habit consistency
        habit_consistency_score = (
            sum(h.properties.get("consistency_score", 0.5) for h in supporting_habits)
            / len(supporting_habits)
            if supporting_habits
            else 0.5
        )

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
        self, velocity_metrics: dict[str, float], context: GraphContext
    ) -> list[str]:
        """
        Identify risk factors that may prevent goal completion.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: Graph context with supporting activities

        Returns:
            List of risk factor descriptions
        """
        total_tasks = velocity_metrics["total_tasks"]
        habit_consistency_score = velocity_metrics["habit_consistency_score"]
        current_progress_rate = velocity_metrics["current_progress_rate"]

        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

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
        self, velocity_metrics: dict[str, float], context: GraphContext, required_velocity: float
    ) -> list[str]:
        """
        Identify opportunities to accelerate goal progress.

        Args:
            velocity_metrics: Velocity metrics from calculate_velocity_metrics(),
            context: Graph context with supporting activities,
            required_velocity: Required tasks per week from timeline analysis

        Returns:
            List of acceleration opportunity descriptions
        """
        velocity_metrics["total_tasks"]
        completed_tasks = velocity_metrics["completed_tasks"]
        task_completion_velocity = velocity_metrics["task_completion_velocity"]

        supporting_habits = context.get_nodes_by_domain(Domain.HABITS)

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
        self, uid: str, progress_value: float, notes: str = "", update_date: str | None = None
    ) -> Result[dict[str, Any]]:
        """
        Update goal progress manually.

        Args:
            uid: Goal UID
            progress_value: New progress value (0-100)
            notes: Optional progress notes
            update_date: The date the progress happened (ISO date or datetime),
                when it is not now — a September correction entered in October
                is a September event. Unparseable or in the future: validation
                failure.

        Returns:
            Result containing progress update confirmation with old/new values
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

        # Get current goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal_dto = goal_result.value
        if not goal_dto:
            return Result.fail(Errors.not_found(resource="Goal", identifier=uid))

        goal = to_domain_model(goal_dto, GoalDTO, Goal)
        old_progress = goal.progress_percentage or 0.0

        # Update progress. progress_value is a percent (0-100), so it goes to
        # progress_percentage only — current_value holds domain units. The stamp
        # records a CHANGE: re-posting the stored figure is not a progress event.
        updates: dict[str, Any] = {"progress_percentage": progress_value}
        if abs(progress_value - old_progress) >= 0.01:
            updates["last_progress_update"] = at
            updates["progress_history"] = with_progress_entry(goal, progress_value, at)

        if notes:
            # Append notes to metadata (access via DTO)
            metadata: dict[str, Any] = goal_dto.metadata or {}
            progress_notes = metadata.get("progress_notes", [])
            progress_notes.append({"date": at.isoformat(), "notes": notes})
            metadata["progress_notes"] = progress_notes
            updates["metadata"] = metadata

        update_result = await self.backend.update_goal(uid, dict(updates))
        if update_result.is_error:
            return Result.fail(update_result)

        # Publish GoalProgressUpdated event
        event = GoalProgressUpdated(
            goal_uid=uid,
            user_uid=goal.user_uid,
            old_progress=old_progress,
            new_progress=progress_value,
            triggered_by_manual_update=True,
        )
        await publish_event(self.event_bus, event, self.logger)

        return Result.ok(
            {
                "goal_uid": uid,
                "old_progress": old_progress,
                "new_progress": progress_value,
                "notes": notes,
                "update_date": at.isoformat(),
            }
        )

    async def get_goal_progress(self, uid: str, period: str = "month") -> Result[dict[str, Any]]:
        """
        Get goal progress history for a period.

        Args:
            uid: Goal UID
            period: Time period ("week", "month", "quarter", "year", "all")

        Returns:
            Result containing progress history data
        """
        # Get goal (as DTO to access metadata)
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal_dto = goal_result.value
        if not goal_dto:
            return Result.fail(Errors.not_found(resource="Goal", identifier=uid))

        goal = to_domain_model(goal_dto, GoalDTO, Goal)

        # Extract progress notes from DTO metadata
        metadata: dict[str, Any] = goal_dto.metadata or {}
        progress_notes = metadata.get("progress_notes", [])

        # Filter notes by period — a trailing window of whole days, compared as instants
        window_days = _PROGRESS_PERIOD_DAYS.get(period)
        if window_days is not None and progress_notes:
            cutoff = now_utc() - timedelta(days=window_days)
            zone = current_zone()
            progress_notes = [
                note
                for note in progress_notes
                if (noted := instant_of(note["date"], zone)) is not None and noted >= cutoff
            ]

        return Result.ok(
            {
                "goal_uid": uid,
                "current_progress": goal.progress_percentage,
                "target_value": goal.target_value,
                "period": period,
                "progress_history": progress_notes,
                "days_remaining": goal.days_remaining(),
                "is_on_track": goal.progress_percentage >= goal.expected_progress_percentage()
                if goal.target_date
                else None,
            }
        )

    async def create_goal_milestone(
        self, uid: str, milestone_title: str, target_date: str, description: str = ""
    ) -> Result[bool]:
        """
        Create a new milestone for a goal.

        Args:
            uid: Goal UID
            milestone_title: Milestone title
            target_date: Target completion date (ISO format)
            description: Optional milestone description

        Returns:
            Result containing True if milestone was created
        """
        from core.models.goal.milestone import Milestone

        # Get current goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # Create new milestone with UID
        import uuid

        new_milestone = Milestone(
            uid=str(uuid.uuid4()),
            title=milestone_title,
            description=description or "",
            target_date=date.fromisoformat(target_date),
            is_completed=False,
        )

        # Add to milestones list
        milestones = list(goal.milestones) if goal.milestones else []
        milestones.append(new_milestone)

        # Update goal
        updates: dict[str, Any] = {"milestones": milestones}
        update_result = await self.backend.update_goal(uid, dict(updates))

        if update_result.is_error:
            return Result.fail(update_result)

        self.logger.info(f"Created milestone '{milestone_title}' for goal {uid}")
        return Result.ok(True)

    async def get_goal_milestones(self, uid: str) -> Result[list[dict[str, Any]]]:
        """
        Get all milestones for a goal.

        Args:
            uid: Goal UID

        Returns:
            Result containing list of milestone dictionaries
        """
        # Get goal
        goal_result = await self.backend.get_goal(uid)
        if goal_result.is_error:
            return Result.fail(goal_result)

        goal = to_domain_model(goal_result.value, GoalDTO, Goal)

        # Convert milestones to dicts
        milestones = []
        if goal.milestones:
            for milestone in goal.milestones:
                milestones.append(
                    {
                        "title": milestone.title,
                        "description": milestone.description,
                        "target_date": (
                            milestone.target_date.isoformat() if milestone.target_date else None
                        ),
                        "is_completed": milestone.is_completed,
                        "achieved_date": (
                            milestone.achieved_date.isoformat() if milestone.achieved_date else None
                        ),
                    }
                )

        return Result.ok(milestones)

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
            goal_uid, owner, plan, outcome.prior_status, from_habits=False
        )
        return Result.ok(True)

    async def reconcile_goal_tallies(self, *, dry_run: bool) -> Result[list[GoalTallyGap]]:
        """Recompute every TASK_BASED goal whose stored tally disagrees with its contributions.

        The tally's trigger (``GoalContributionsChanged``) is best-effort: a recompute
        that fails after the change it answers has committed leaves the stored figure
        behind, and nothing replays the event. This reads every TASK_BASED goal, plans
        its write under the rule the recompute uses (``_plan_contribution_progress``)
        and, unless ``dry_run``, closes each gap through the same locked recompute.
        Idempotent: a second run finds nothing.

        Backend: GoalsBackend.list_task_based_goals / get_contribution_tally.
        """
        goals = await self.backend.list_task_based_goals()
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
            tally = await self.backend.get_contribution_tally(goal_uid)
            if tally.is_error:
                return Result.fail(tally)
            plan = _plan_contribution_progress(goal, tally.value)
            if plan is None:
                continue
            gaps.append(
                GoalTallyGap(
                    goal_uid=goal_uid,
                    user_uid=owner_uid,
                    stored=f"{goal.current_value}/{goal.target_value}",
                    live=plan.detail,
                )
            )
            if not dry_run:
                written = await self.recompute_goal_tally(goal_uid)
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
        try:
            # Goals this habit supports (Backend: GoalsBackend.find_linked_goals_for_habit)
            result = await self.backend.find_linked_goals_for_habit(event.habit_uid, event.user_uid)
            if result.is_error:
                self.logger.error(
                    f"Failed to query goals for habit {event.habit_uid}: {result.error}"
                )
                return

            goal_uids = result.value or []
            if not goal_uids:
                self.logger.debug(f"No goals linked to habit {event.habit_uid}")
                return

            for goal_uid in goal_uids:
                try:
                    await self._update_goal_from_habit_completion(
                        goal_uid=goal_uid,
                        user_uid=event.user_uid,
                        current_streak=event.current_streak,
                    )
                except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
                    # Best-effort: Don't let one goal failure block others
                    self.logger.error(
                        f"Failed to update goal {goal_uid} from habit completion: {e}"
                    )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            # Best-effort: Log error but don't raise (prevent habit completion failure)
            self.logger.error(f"Error handling habit_completed event: {e}")

    # FUTURE-IMPL-008: See docs/reference/PLACEHOLDER_INDEX.md § I2
    async def _update_goal_from_habit_completion(
        self, goal_uid: str, user_uid: UserUID, current_streak: int
    ) -> None:
        """Recompute one HABIT_BASED goal from its supporting habits' average streak.

        Progress is ``avg_streak / target_value * 100``, capped at 100 — target_value is
        the desired streak length. Decided under the goal's write-lock, like the
        task-based sibling (``GoalsBackend.recompute_progress_from_linked_habits``).

        Args:
            goal_uid: Goal to update
            user_uid: User owning the goal
            current_streak: Current streak length of the completed habit
        """
        result = await self.backend.recompute_progress_from_linked_habits(
            goal_uid, user_uid, _plan_habit_progress
        )
        if result.is_error:
            self.logger.error(f"Failed to recompute goal {goal_uid}: {result.error}")
            return
        if result.value is None:
            self.logger.debug(f"Goal {goal_uid}: no habit-based progress change")
            return

        plan, outcome = result.value.plan, result.value.outcome
        self.logger.info(
            f"Updated goal {goal_uid}: {plan.old_progress:.1f}% → {plan.new_progress:.1f}% "
            f"({plan.detail})"
        )
        await self._publish_recompute(
            goal_uid, user_uid, plan, outcome.prior_status, from_habits=True
        )

    async def _publish_recompute(
        self,
        goal_uid: str,
        user_uid: UserUID,
        plan: _ProgressWrite,
        prior_status: str | None,
        *,
        from_habits: bool,
    ) -> None:
        """Announce what a recompute wrote, with verdicts from the prior the write saw.

        ``GoalProgressUpdated`` only when the percentage moved:
        ``GoalEventHandlerService.handle_goal_progress_updated`` reads a near-zero delta
        on a positive goal as a STALL and persists an IMBALANCE_DETECTED insight, so a
        tally-only repair stays quiet. ``GoalAchieved`` only on the transition INTO
        completed, decided from the prior the write captured, so a goal another writer
        completed first is not announced twice, and a settled goal (``_SETTLED``), which
        the write did not achieve, is not announced at all.

        ``from_habits`` is the trigger's provenance: a habit-based recompute, or a
        contribution-based one.
        """
        if plan.progress_changed:
            await publish_event(
                self.event_bus,
                GoalProgressUpdated(
                    goal_uid=goal_uid,
                    user_uid=user_uid,
                    old_progress=plan.old_progress,
                    new_progress=plan.new_progress,
                    triggered_by_contribution_change=not from_habits,
                    triggered_by_habit_completion=from_habits,
                    triggered_by_manual_update=False,
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
