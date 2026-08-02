"""
Habits Completion Tracking Service
===================================

Handles habit completion tracking with quality scores, notes, and analytics.

Responsibilities:
- Record habit completions with quality tracking
- Calculate completion statistics (today, week, month)
- Track streaks based on completions
- Badge progress tracking
- Export completion history
"""

from datetime import date, datetime, timedelta
from typing import Any

from core.constants import QueryLimit
from core.events import publish_event
from core.models.habit.completion import HabitCompletion
from core.models.habit.completion_dto import HabitCompletionDTO
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.type_hints import UserUID
from core.ports.domain_protocols import HabitsOperations
from core.utils.completion_exporter import export_completions_csv, export_completions_json
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.neo4j_props import neo4j_str
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_completed_at


class HabitsCompletionService:
    """
    Completion tracking service for habits.

    Handles all completion-related operations including:
    - Recording completions with quality/notes
    - Analytics (completed today, this week, etc.)
    - Streak calculation
    - Badge progress

    Architecture Note:
        This service intentionally does NOT extend BaseService.
        HabitCompletion is a "secondary entity" - it tracks user engagement
        with a primary entity (Habit). Secondary entities:
        - Are queried via their parent entity, not directly
        - Don't need CRUD route factories
        - Handle ownership via User relationship, not verify_ownership()
        - Have simpler lifecycle (create, query - rarely update)

        See: /docs/patterns/SECONDARY_ENTITY_PATTERN.md
    """

    def __init__(
        self,
        habits_backend,  # UniversalNeo4jBackend[Habit]
        completions_backend,  # UniversalNeo4jBackend[HabitCompletion]
        event_bus=None,
    ) -> None:
        """
        Initialize habits completion service.

        Args:
            habits_backend: Backend for habit CRUD operations,
            completions_backend: Backend for completion CRUD operations,
            event_bus: Event bus for publishing domain events (optional)
        """
        if not habits_backend:
            raise ValueError("habits_backend is required")
        if not completions_backend:
            raise ValueError("completions_backend is required")

        self.habits_backend = habits_backend
        self.completions_backend = completions_backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits.completion")

    # ========================================================================
    # COMPLETION TRACKING
    # ========================================================================

    async def record_completion(
        self,
        habit_uid: str,
        user_uid: UserUID,
        completed_at: datetime | None = None,
        quality: int | None = None,
        duration_actual: int | None = None,
        notes: str | None = None,
    ) -> Result[HabitCompletion]:
        """
        Record a habit completion.

        Args:
            habit_uid: UID of habit completed,
            user_uid: User who completed the habit,
            completed_at: When habit was completed (default: now),
            quality: Quality rating 1-5 (optional),
            duration_actual: Actual duration in minutes (optional),
            notes: Completion notes (optional)

        Returns:
            Result[HabitCompletion] with the created completion record
        """
        self.logger.info(f"Recording completion for habit {habit_uid}")

        # Validate habit exists
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        # Create completion record
        now = datetime.now()
        completion_uid = f"hc.{user_uid}.{habit_uid}.{int(now.timestamp())}"

        completion_dto = HabitCompletionDTO(
            uid=completion_uid,
            habit_uid=habit_uid,
            completed_at=completed_at or now,
            quality=quality,
            duration_actual=duration_actual,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

        # Store completion
        create_result = await self.completions_backend.create(completion_dto)
        if create_result.is_error:
            return create_result

        # Convert to domain model
        completion = HabitCompletion.from_dto(completion_dto)

        # Update habit statistics (fail-fast: stats must succeed)
        stats_result = await self._update_habit_stats(habit_uid, completion)
        if stats_result.is_error:
            return Result.fail(stats_result)

        self.logger.info(f"✅ Recorded completion {completion_uid}")
        return Result.ok(completion)

    async def record_completions_bulk(
        self,
        habit_uids: list[str],
        user_uid: UserUID,
        completed_at: datetime | None = None,
    ) -> Result[list[HabitCompletion]]:
        """
        Record completions for multiple habits in a batch operation.

        More efficient than calling record_completion N times:
        - Single HabitCompletionBulk event vs N HabitCompleted events

        Args:
            habit_uids: List of habit UIDs to complete
            user_uid: User completing the habits
            completed_at: When habits were completed (default: now)

        Returns:
            Result[list[HabitCompletion]] with all created completion records
        """
        if not habit_uids:
            return Result.ok([])

        self.logger.info(f"Recording bulk completions for {len(habit_uids)} habits")

        completions: list[HabitCompletion] = []
        new_streak_records: list[str] = []
        milestones_reached: list[tuple[str, int]] = []
        now = completed_at or datetime.now()

        for habit_uid in habit_uids:
            # Record each completion (without individual events)
            result = await self._record_completion_no_event(habit_uid, user_uid, now)
            if result.is_ok:
                completion, is_new_record, milestone = result.value
                completions.append(completion)
                if is_new_record:
                    new_streak_records.append(habit_uid)
                if milestone:
                    milestones_reached.append(milestone)

        # Publish single bulk event for all completions
        if completions:
            from core.events.habit_events import HabitCompletionBulk

            event = HabitCompletionBulk(
                habit_uids=tuple(c.habit_uid for c in completions),
                user_uid=user_uid,
                new_streak_records=tuple(new_streak_records),
                milestones_reached=tuple(milestones_reached),
            )
            await publish_event(self.event_bus, event, self.logger)
            self.logger.info(
                f"✅ Bulk completed {len(completions)} habits "
                f"({len(new_streak_records)} new records, {len(milestones_reached)} milestones)"
            )

        return Result.ok(completions)

    async def _record_completion_no_event(
        self,
        habit_uid: str,
        user_uid: UserUID,
        completed_at: datetime,
    ) -> Result[tuple[HabitCompletion, bool, tuple[str, int] | None]]:
        """
        Record a completion without publishing individual events.

        Used by record_completions_bulk for batch processing.

        Returns:
            Result containing (completion, is_new_streak_record, milestone_or_none)
        """
        # Validate habit exists
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        habit = habit_result.value

        # Create completion record
        completion_uid = f"hc.{user_uid}.{habit_uid}.{int(completed_at.timestamp())}"
        now = datetime.now()

        completion_dto = HabitCompletionDTO(
            uid=completion_uid,
            habit_uid=habit_uid,
            completed_at=completed_at,
            quality=None,
            duration_actual=None,
            notes=None,
            created_at=now,
            updated_at=now,
        )

        # Store completion
        create_result = await self.completions_backend.create(completion_dto)
        if create_result.is_error:
            return Result.fail(create_result)

        completion = HabitCompletion.from_dto(completion_dto)

        # Calculate new streak (backfill-safe: an out-of-order completion never
        # regresses last_completed or breaks the streak — see the helper).
        streak_result = await self._streak_and_last_completed(habit, habit_uid, completed_at)
        if streak_result.is_error:
            return Result.fail(streak_result)
        new_streak, last_completed = streak_result.value
        is_new_record = new_streak > habit.best_streak

        # Check for milestone (names used by _publish_milestone_event_if_reached)
        milestone: tuple[str, int] | None = None
        milestone_values = {7, 30, 100, 365}  # one_week, one_month, one_hundred, one_year
        if new_streak in milestone_values and habit.current_streak < new_streak:
            milestone = (habit_uid, new_streak)

        # raw-write: system streak/stat propagation from a habit completion. Bypasses the
        # validated/event-firing service contract (HabitUpdateIntent → update_habit) on
        # purpose — this completion path owns streak/milestone provenance events. A plain
        # dict literal is the honest type here.
        updates: dict[str, Any] = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "total_completions": habit.total_completions + 1,
            "last_completed": last_completed,
            "updated_at": now,
        }
        if habit.is_identity_based():
            updates["identity_votes_cast"] = habit.identity_votes_cast + 1

        await self.habits_backend.update(habit_uid, updates)

        return Result.ok((completion, is_new_record, milestone))

    @with_error_handling("update_habit_stats", error_type="database", uid_param="habit_uid")
    async def _update_habit_stats(
        self, habit_uid: str, completion: HabitCompletion
    ) -> Result[None]:
        """Update habit statistics after completion."""
        # Get current habit
        habit_result = await self.habits_backend.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result)

        # Backend returns Result[Habit | None] - trust the type system
        habit = habit_result.value

        # Calculate new streak (backfill-safe: an out-of-order completion never
        # regresses last_completed or breaks the streak — see the helper).
        streak_result = await self._streak_and_last_completed(
            habit, habit_uid, completion.completed_at
        )
        if streak_result.is_error:
            return Result.fail(streak_result)
        new_streak, last_completed = streak_result.value

        # Check for streak milestones and publish events
        await self._check_streak_milestones(habit, new_streak, habit.user_uid)

        # raw-write: system streak/stat propagation from a habit completion. Bypasses the
        # validated/event-firing service contract (HabitUpdateIntent → update_habit) on
        # purpose — _check_streak_milestones above owns the streak/milestone provenance
        # events. A plain dict literal is the honest type here.
        updates: dict[str, Any] = {
            "current_streak": new_streak,
            "best_streak": max(new_streak, habit.best_streak),
            "total_completions": habit.total_completions + 1,
            "last_completed": last_completed,
        }

        # Update identity votes if applicable
        if habit.is_identity_based():
            updates["identity_votes_cast"] = habit.identity_votes_cast + 1

        update_result = await self.habits_backend.update(habit_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result)

        self.logger.debug(f"Updated habit {habit_uid} stats: streak={new_streak}")
        return Result.ok(None)

    async def _streak_and_last_completed(
        self, habit: Habit, habit_uid: str, completed_at: datetime
    ) -> Result[tuple[int, datetime]]:
        """New (streak, last_completed) after recording a completion at ``completed_at``.

        In-order completions use the incremental delta formula
        (``_calculate_new_streak``) and advance ``last_completed``. A BACKFILLED
        completion — one dated before the habit's ``last_completed``, e.g. the
        calendar's per-day Mark Complete on an earlier pending day — must not
        regress ``last_completed``, and the delta formula cannot apply (it would
        read the negative gap as a broken streak); the streak is instead
        recomputed from stored completion history, so a backfill can BRIDGE two
        runs into one, never break one.
        """
        if habit.last_completed is not None and completed_at.date() < habit.last_completed.date():
            recomputed = await self._streak_ending_at(habit_uid, habit.last_completed.date())
            if recomputed.is_error:
                return Result.fail(recomputed)
            return Result.ok((recomputed.value, habit.last_completed))
        return Result.ok((self._calculate_new_streak(habit, completed_at), completed_at))

    async def _streak_ending_at(self, habit_uid: str, anchor: date) -> Result[int]:
        """Consecutive-day streak ending at ``anchor``, recomputed from stored completions.

        Bounded to the trailing 365 days (past the largest milestone) — a streak
        longer than the window is reported as the window's span. Tolerates the
        native/string ``completed_at`` temporal split.
        """
        completions = await self.get_completions_for_habit(
            habit_uid,
            start_date=anchor - timedelta(days=365),
            end_date=anchor,
            limit=400,  # 366 daily completions fit; find_by truncation stays out of reach
        )
        if completions.is_error:
            return Result.fail(completions)
        completed_days: set[date] = set()
        for c in completions.value:
            completed_at = c.completed_at
            if isinstance(completed_at, str):
                try:
                    completed_at = datetime.fromisoformat(completed_at)
                except ValueError:
                    continue
            if completed_at is not None:
                completed_days.add(completed_at.date())
        streak = 0
        day = anchor
        while day in completed_days:
            streak += 1
            day -= timedelta(days=1)
        return Result.ok(streak)

    def _calculate_new_streak(self, habit: Habit, completion_date: datetime) -> int:
        """Calculate new streak based on last completion (in-order completions only).

        Backfilled (out-of-order) completions never reach this formula — they are
        routed to ``_streak_ending_at`` by ``_streak_and_last_completed``.
        """
        if not habit.last_completed:
            return 1  # First completion

        days_since = (completion_date.date() - habit.last_completed.date()).days

        if days_since == 0:
            # Same day completion
            return habit.current_streak
        elif days_since == 1:
            # Consecutive day
            return habit.current_streak + 1
        else:
            # Streak broken
            return 1

    async def _check_streak_milestones(
        self, habit: Habit, new_streak: int, user_uid: UserUID
    ) -> None:
        """
        Check if new streak reaches a milestone and publish event.

        Milestones: 7 (one week), 30 (one month), 100 (one hundred), 365 (one year)
        """
        # Define milestones with their names
        milestones = {
            7: "one_week",
            30: "one_month",
            100: "one_hundred",
            365: "one_year",
        }

        old_streak = habit.current_streak

        # Check if new streak exactly matches a milestone (and we just reached it)
        for milestone_value, milestone_name in milestones.items():
            if new_streak == milestone_value and old_streak < milestone_value:
                # Milestone reached! Publish event
                from core.events.habit_events import HabitStreakMilestone

                event = HabitStreakMilestone(
                    habit_uid=habit.uid,
                    user_uid=user_uid,
                    streak_length=new_streak,
                    milestone_name=milestone_name,
                )
                await publish_event(self.event_bus, event, self.logger)

    # ========================================================================
    # COMPLETION QUERIES
    # ========================================================================

    async def get_completions_for_habit(
        self,
        habit_uid: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> Result[list[HabitCompletion]]:
        """Get all completions for a habit within date range."""
        self.logger.debug(f"Getting completions for habit {habit_uid}")

        # Build filters
        filters: dict[str, str | datetime] = {"habit_uid": habit_uid}
        if start_date:
            filters["completed_at__gte"] = datetime.combine(start_date, datetime.min.time())
        if end_date:
            filters["completed_at__lte"] = datetime.combine(end_date, datetime.max.time())

        # Query completions
        result = await self.completions_backend.find_by(**filters, limit=limit)
        if result.is_error:
            return result

        # Convert to domain models
        completions = []
        for item in result.value:
            if isinstance(item, dict):
                dto = HabitCompletionDTO.from_dict(item)
                completions.append(HabitCompletion.from_dto(dto))
            elif isinstance(item, HabitCompletionDTO):
                completions.append(HabitCompletion.from_dto(item))
            else:
                completions.append(item)

        # Sort by completion date (most recent first)
        completions.sort(key=get_completed_at, reverse=True)

        return Result.ok(completions)

    async def get_today_completions(self, user_uid: UserUID) -> Result[list[dict[str, Any]]]:
        """
        Get all habit completions for today for a user.

        Args:
            user_uid: User identifier

        Returns list of dicts with habit details + completion info.
        """
        today = date.today()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())

        # Get user's completions for today
        completions_result = await self.completions_backend.find_by(
            user_uid=user_uid,
            completed_at__gte=start_of_day,
            completed_at__lte=end_of_day,
            limit=QueryLimit.COMPREHENSIVE,
        )

        if completions_result.is_error:
            return completions_result

        # Group completions by habit
        habit_completions: dict[str, list[HabitCompletion]] = {}
        for item in completions_result.value:
            if isinstance(item, dict):
                dto = HabitCompletionDTO.from_dict(item)
                completion = HabitCompletion.from_dto(dto)
            elif isinstance(item, HabitCompletionDTO):
                completion = HabitCompletion.from_dto(item)
            else:
                completion = item

            habit_uid = completion.habit_uid
            if habit_uid not in habit_completions:
                habit_completions[habit_uid] = []
            habit_completions[habit_uid].append(completion)

        # Get habit details and create response
        result = []
        for habit_uid, completions in habit_completions.items():
            habit_result = await self.habits_backend.get(habit_uid)
            if habit_result.is_ok:
                # Backend returns Result[Habit | None] - trust the type system
                habit = habit_result.value

                result.append(
                    {
                        "habit": habit,
                        "completions_today": len(completions),
                        "latest_completion": completions[0],  # Most recent
                        "total_quality_today": sum(c.quality or 0 for c in completions),
                        "completed": True,
                    }
                )

        return Result.ok(result)

    async def calculate_completed_today_count(self, user_uid: UserUID) -> Result[int]:
        """Calculate how many habits user completed today.

        Args:
            user_uid: User identifier
        """
        today_result = await self.get_today_completions(user_uid)
        if today_result.is_error:
            return Result.fail(today_result)

        return Result.ok(len(today_result.value))

    # ========================================================================
    # ANALYTICS
    # ========================================================================

    async def get_completion_stats(self, habit_uid: str, days: int = 30) -> Result[dict[str, Any]]:
        """Get completion statistics for a habit over a period."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        completions_result = await self.get_completions_for_habit(
            habit_uid, start_date=start_date, end_date=end_date
        )

        if completions_result.is_error:
            return Result.fail(completions_result)

        completions = completions_result.value

        # Calculate statistics
        stats = {
            "habit_uid": habit_uid,
            "period_days": days,
            "total_completions": len(completions),
            "completion_rate": len(completions) / days if days > 0 else 0,
            "average_quality": sum(c.quality or 0 for c in completions) / len(completions)
            if completions and any(c.quality for c in completions)
            else None,
            "high_quality_count": sum(1 for c in completions if c.is_high_quality()),
            "excellent_quality_count": sum(1 for c in completions if c.is_excellent_quality()),
            "completion_dates": [c.completed_at.date().isoformat() for c in completions],
            "notes_count": sum(1 for c in completions if c.has_meaningful_notes()),
        }

        return Result.ok(stats)

    async def get_badge_progress(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Calculate badge progress, merging persisted badges with computed progress.

        Streak, completion, quality, and identity badges are persisted to Neo4j
        as Achievement nodes by HabitEventHandlerService. This method computes
        live progress values and enriches them with persisted earned_at dates.

        Args:
            user_uid: User identifier

        Badges include:
        - Streak badges (7, 30, 100, 365 days)
        - Completion badges (10, 50, 100, 500 habits)
        - Quality badges (100 high-quality completions)
        - Identity badges (50 identity votes cast)
        """
        # Get user's habits
        habits_result = await self.habits_backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if habits_result.is_error:
            return habits_result

        # Calculate badge progress
        max_streak = 0
        total_completions = 0
        total_identity_votes = 0
        high_quality_completions = 0

        for item in habits_result.value:
            if isinstance(item, dict):
                habit_dto = HabitDTO.from_dict(item)
                habit = Habit.from_dto(habit_dto)
            else:
                habit = item

            max_streak = max(max_streak, habit.current_streak)
            total_completions += habit.total_completions

            if habit.is_identity_based():
                total_identity_votes += habit.identity_votes_cast

        # Get user's high-quality completions (last 1000)
        all_completions_result = await self.completions_backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if all_completions_result.is_ok:
            for item in all_completions_result.value:
                if isinstance(item, dict):
                    dto = HabitCompletionDTO.from_dict(item)
                    completion = HabitCompletion.from_dto(dto)
                else:
                    completion = item

                if completion.is_high_quality():
                    high_quality_completions += 1

        # Fetch persisted badges to get earned_at dates
        earned_badge_ids: set[str] = set()
        if isinstance(self.habits_backend, HabitsOperations):
            badges_result = await self.habits_backend.get_user_badges(user_uid)
            if badges_result.is_ok:
                for badge_record in badges_result.value:
                    earned_badge_ids.add(neo4j_str(badge_record, "badge_id", ""))

        def _badge_entry(badge_id: str, current: int | float, target: int) -> dict[str, Any]:
            """Build badge progress dict, marking as unlocked if persisted OR threshold met."""
            unlocked = current >= target or badge_id in earned_badge_ids
            return {"unlocked": unlocked, "progress": min(current / target, 1.0)}

        badge_progress: dict[str, Any] = {
            "streaks": {
                "current_max_streak": max_streak,
                "week_warrior": _badge_entry("habit_week_warrior", max_streak, 7),
                "month_master": _badge_entry("habit_month_master", max_streak, 30),
                "century_champion": _badge_entry("habit_century_champion", max_streak, 100),
                "year_legend": _badge_entry("habit_year_legend", max_streak, 365),
            },
            "completions": {
                "total_completions": total_completions,
                "getting_started": _badge_entry("getting_started", total_completions, 10),
                "habit_builder": _badge_entry("habit_builder", total_completions, 50),
                "century_club": _badge_entry("century_club", total_completions, 100),
                "habit_master": _badge_entry("habit_master", total_completions, 500),
            },
            "quality": {
                "high_quality_count": high_quality_completions,
                "quality_focused": _badge_entry("quality_focused", high_quality_completions, 100),
            },
            "identity": {
                "total_identity_votes": total_identity_votes,
                "identity_seeker": _badge_entry("identity_established", total_identity_votes, 50),
            },
            # Persisted badge IDs for UI consumption
            "earned_badge_ids": list(earned_badge_ids),
        }

        return Result.ok(badge_progress)

    # ========================================================================
    # EXPORT
    # ========================================================================

    async def export_completion_history(
        self,
        user_uid: UserUID,
        start_date: date | None = None,
        end_date: date | None = None,
        format: str = "csv",
    ) -> Result[str]:
        """
        Export completion history for a user.

        Args:
            user_uid: User to export for
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            format: Export format ("csv" or "json")

        Returns:
            Result[str] with exported data as string
        """
        if format not in ("csv", "json"):
            return Result.fail(
                Errors.validation(
                    message=f"Unsupported export format: {format}", field="format", value=format
                )
            )

        # Scope through the habits backend — HabitCompletion has no user_uid field,
        # so filtering completions_backend by user_uid is silently a no-op. The
        # correct path is: fetch the user's habit UIDs (habits_backend IS scoped),
        # then pull completions only for those UIDs.
        habits_result = await self.habits_backend.find_by(
            user_uid=user_uid, limit=QueryLimit.COMPREHENSIVE
        )
        if habits_result.is_error:
            return habits_result

        habit_uids = [
            (item["uid"] if isinstance(item, dict) else item.uid)
            for item in habits_result.value
            if (item.get("uid") if isinstance(item, dict) else item.uid)
        ]
        if not habit_uids:
            return self._export_csv([]) if format == "csv" else self._export_json([])

        date_filters: dict[str, datetime] = {}
        if start_date:
            date_filters["completed_at__gte"] = datetime.combine(start_date, datetime.min.time())
        if end_date:
            date_filters["completed_at__lte"] = datetime.combine(end_date, datetime.max.time())

        completions: list[HabitCompletion] = []
        for habit_uid in habit_uids:
            per_habit = await self.completions_backend.find_by(
                habit_uid=habit_uid, **date_filters, limit=QueryLimit.BULK
            )
            if per_habit.is_error:
                continue
            for item in per_habit.value:
                if isinstance(item, dict):
                    completions.append(HabitCompletion.from_dto(HabitCompletionDTO.from_dict(item)))
                else:
                    completions.append(item)

        # Sort by date
        completions.sort(key=get_completed_at)

        if format == "csv":
            return self._export_csv(completions)
        return self._export_json(completions)

    def _export_csv(self, completions: list[HabitCompletion]) -> Result[str]:
        """Export completions as CSV. Delegates to presentation layer."""
        return Result.ok(export_completions_csv(completions))

    def _export_json(self, completions: list[HabitCompletion]) -> Result[str]:
        """Export completions as JSON. Delegates to presentation layer."""
        return Result.ok(export_completions_json(completions))
