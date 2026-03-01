"""
User Context Populator - Populate UserContext from Query Results
=================================================================

**EXTRACTED (December 2025):** From user_context_builder.py for separation of concerns.

This module contains:
- UserContextPopulator class for populating UserContext fields

Architecture:
- Pure population logic, no database queries or extraction
- Takes structured data and assigns to UserContext fields
- Used by UserContextBuilder after extraction
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import (
    EnergyLevel,
    GuidanceMode,
    LearningLevel,
    Personality,
    ResponseTone,
    TimeOfDay,
)
from core.utils.logging import get_logger
from core.utils.sort_functions import get_updated_timestamp

if TYPE_CHECKING:
    from core.services.user import UserContext
    from core.services.user.user_context_extractor import GraphSourcedData

logger = get_logger(__name__)


class UserContextPopulator:
    """
    Populate UserContext from query results.

    This class handles the final step of context building:
    assigning extracted data to UserContext fields.

    All methods are pure (no side effects beyond context mutation).
    """

    def populate_standard_fields(self, context: "UserContext", uids_data: dict[str, Any]) -> None:
        """
        Populate standard context fields (UIDs, relationships) from MEGA-QUERY results.

        Args:
            context: UserContext to populate
            uids_data: The "uids" section from MEGA-QUERY results
        """
        # Tasks
        context.active_task_uids = uids_data.get("active_task_uids", [])
        context.completed_task_uids = set(uids_data.get("completed_task_uids", []))
        context.overdue_task_uids = uids_data.get("overdue_task_uids", [])
        context.today_task_uids = uids_data.get("today_task_uids", [])

        # Goals
        context.active_goal_uids = [uid for uid in uids_data.get("active_goal_uids", []) if uid]
        context.completed_goal_uids = set(
            uid for uid in uids_data.get("completed_goal_uids", []) if uid
        )
        goal_progress_list = uids_data.get("goal_progress", [])
        context.goal_progress = {
            item["uid"]: item["progress"]
            for item in goal_progress_list
            if item and item.get("uid") is not None
        }

        # Habits
        context.active_habit_uids = [uid for uid in uids_data.get("active_habit_uids", []) if uid]
        habit_metadata = uids_data.get("habit_metadata", [])
        context.habit_streaks = {
            item["uid"]: item["streak"]
            for item in habit_metadata
            if item and item.get("uid") is not None
        }
        context.habit_completion_rates = {
            item["uid"]: item["rate"]
            for item in habit_metadata
            if item and item.get("uid") is not None
        }

        # Knowledge - extract mastery scores, timestamps, and confidence
        knowledge_mastery_list = uids_data.get("knowledge_mastery", [])
        context.knowledge_mastery = {
            item["uid"]: item["score"]
            for item in knowledge_mastery_list
            if item and item.get("uid") is not None
        }
        context.mastered_knowledge_uids = set(
            uid for uid, score in context.knowledge_mastery.items() if score >= 0.8
        )
        # Extract mastery timestamps from relationship metadata
        context.mastery_timestamps = {
            item["uid"]: item["mastered_at"]
            for item in knowledge_mastery_list
            if item and item.get("uid") is not None and item.get("mastered_at")
        }
        # Extract mastery confidence scores from relationship metadata
        context.mastery_confidence_scores = {
            item["uid"]: item["confidence"]
            for item in knowledge_mastery_list
            if item and item.get("uid") is not None and item.get("confidence") is not None
        }

        # KU Tracking - view counts, recently viewed, marked as read (MVP - Phase B)
        ku_view_data = uids_data.get("ku_view_data", [])
        context.ku_view_counts = {
            item["uid"]: item["view_count"]
            for item in ku_view_data
            if item and item.get("uid") is not None
        }
        # Recently viewed KUs - sort by last_viewed_at descending, take last 10
        viewed_with_timestamps = [
            (item["uid"], item["last_viewed_at"])
            for item in ku_view_data
            if item and item.get("uid") is not None and item.get("last_viewed_at") is not None
        ]

        def by_timestamp(item: tuple) -> Any:
            return item[1]

        viewed_with_timestamps.sort(key=by_timestamp, reverse=True)
        context.recently_viewed_ku_uids = [uid for uid, _ in viewed_with_timestamps[:10]]

        # Marked as read KUs
        context.ku_marked_as_read_uids = set(
            uid for uid in uids_data.get("ku_marked_as_read_uids", []) if uid
        )

        # Bookmarked KUs
        context.ku_bookmarked_uids = set(
            uid for uid in uids_data.get("ku_bookmarked_uids", []) if uid
        )

        # KU time spent (from view data)
        context.ku_time_spent_seconds = {
            item["uid"]: item.get("time_spent_seconds", 0)
            for item in ku_view_data
            if item and item.get("uid") is not None
        }

        # Learning Paths
        context.enrolled_path_uids = uids_data.get("enrolled_path_uids", [])

        # Events
        context.upcoming_event_uids = uids_data.get("upcoming_event_uids", [])
        context.today_event_uids = uids_data.get("today_event_uids", [])

        # Principles
        context.core_principle_uids = [
            uid for uid in uids_data.get("core_principle_uids", []) if uid
        ]

        # Choices
        context.pending_choice_uids = [
            uid for uid in uids_data.get("pending_choice_uids", []) if uid
        ]

    def populate_rich_fields(self, context: "UserContext", rich_data: dict[str, Any]) -> None:
        """
        Populate rich context fields (full entities + graph) from MEGA-QUERY results.

        Args:
            context: UserContext to populate
            rich_data: The "rich" section from MEGA-QUERY results
        """
        # Tasks rich data
        context.active_tasks_rich = rich_data.get("tasks", [])

        # Goals rich data
        context.active_goals_rich = rich_data.get("goals", [])

        # Knowledge rich data (convert list to dict keyed by uid)
        knowledge_list = rich_data.get("knowledge", [])
        context.knowledge_units_rich = {
            item["uid"]: {"ku": item["ku"], "graph_context": item["graph_context"]}
            for item in knowledge_list
            if item and "uid" in item
        }

        # Learning paths rich data
        context.enrolled_paths_rich = rich_data.get("learning_paths", [])

        # Learning steps rich data
        context.active_learning_steps_rich = rich_data.get("learning_steps", [])

        # Habits, Events, Principles, Choices rich data
        context.active_habits_rich = rich_data.get("habits", [])
        context.active_events_rich = rich_data.get("events", [])
        context.core_principles_rich = rich_data.get("principles", [])
        context.recent_choices_rich = rich_data.get("choices", [])

    def populate_graph_sourced_fields(
        self, context: "UserContext", graph_data: "GraphSourcedData"
    ) -> None:
        """
        Populate graph-sourced relationship fields from extracted data.

        Args:
            context: UserContext to populate
            graph_data: GraphSourcedData from UserContextExtractor
        """
        # Task relationships
        context.task_dependencies = graph_data.tasks.dependencies
        context.task_blockers = graph_data.tasks.blockers
        context.task_knowledge_applied = graph_data.tasks.knowledge_applied
        context.task_goal_associations = graph_data.tasks.goal_associations

        # Goal relationships
        context.goal_knowledge_required = graph_data.goals.knowledge_required
        context.goal_knowledge_mastered = graph_data.goals.knowledge_mastered
        context.goal_completion_from_graph = graph_data.goals.completion_from_graph
        context.goal_supporting_tasks = graph_data.goals.supporting_tasks

        # Habit relationships
        context.habit_knowledge_applied = graph_data.habits.knowledge_applied
        context.habit_prerequisites = graph_data.habits.prerequisites

        # Knowledge relationships
        context.prerequisite_counts = graph_data.knowledge.prerequisite_counts
        context.ready_to_learn_uids = graph_data.knowledge.ready_to_learn_uids

    def populate_from_consolidated_data(self, context: "UserContext", data: dict[str, Any]) -> None:
        """
        Populate UserContext from consolidated query results (standard path).

        This is the simpler path that populates UIDs only, without rich data.

        Args:
            context: UserContext to populate
            data: Consolidated data from execute_consolidated_query()
        """
        # Tasks
        tasks_data = data.get("tasks", {})
        context.active_task_uids = tasks_data.get("active_uids", [])
        context.completed_task_uids = tasks_data.get("completed_uids", set())
        context.overdue_task_uids = tasks_data.get("overdue_uids", [])
        context.today_task_uids = tasks_data.get("today_uids", [])

        # Habits
        habits_data = data.get("habits", {})
        context.active_habit_uids = habits_data.get("active_uids", [])
        context.habit_streaks = habits_data.get("habit_streaks", {})
        context.habit_completion_rates = habits_data.get("completion_rates", {})

        # Goals
        goals_data = data.get("goals", {})
        context.active_goal_uids = goals_data.get("active_uids", [])
        context.completed_goal_uids = goals_data.get("completed_uids", set())
        context.goal_progress = goals_data.get("goal_progress", {})

        # Knowledge
        knowledge_data = data.get("knowledge", {})
        context.mastered_knowledge_uids = knowledge_data.get("mastered_uids", set())
        context.enrolled_path_uids = knowledge_data.get("enrolled_path_uids", [])
        context.knowledge_mastery = knowledge_data.get("knowledge_mastery", {})
        context.ku_view_counts = knowledge_data.get("ku_view_counts", {})
        context.recently_viewed_ku_uids = knowledge_data.get("recently_viewed_ku_uids", [])
        context.ku_marked_as_read_uids = knowledge_data.get("ku_marked_as_read_uids", set())
        context.ku_bookmarked_uids = knowledge_data.get("ku_bookmarked_uids", set())
        context.ku_time_spent_seconds = knowledge_data.get("ku_time_spent_seconds", {})

        # Events
        events_data = data.get("events", {})
        context.upcoming_event_uids = events_data.get("upcoming_uids", [])
        context.today_event_uids = events_data.get("today_uids", [])

        # MOCs (Maps of Content)
        mocs_data = data.get("mocs", {})
        context.active_moc_uids = mocs_data.get("active_uids", [])
        context.moc_view_counts = mocs_data.get("view_counts", {})
        context.recently_viewed_moc_uids = mocs_data.get("recently_viewed_uids", [])

    def populate_user_properties(self, context: "UserContext", user_props: dict[str, Any]) -> None:
        """
        Populate user preference fields from MEGA-QUERY user_properties.

        Args:
            context: UserContext to populate
            user_props: The "user_properties" section from MEGA-QUERY results
        """
        if not user_props:
            return

        # Learning level
        if learning_level := user_props.get("learning_level"):
            try:
                context.learning_level = LearningLevel(learning_level)
            except ValueError:
                logger.debug(f"Unknown learning_level value: {learning_level}")

        # Preferred time of day
        if preferred_time := user_props.get("preferred_time"):
            try:
                context.preferred_time = TimeOfDay(preferred_time)
            except ValueError:
                logger.debug(f"Unknown preferred_time value: {preferred_time}")

        # Energy level
        if energy_level := user_props.get("energy_level"):
            try:
                context.current_energy_level = EnergyLevel(energy_level)
            except ValueError:
                logger.debug(f"Unknown energy_level value: {energy_level}")

        # Available minutes
        if available_minutes := user_props.get("available_minutes"):
            context.available_minutes_daily = int(available_minutes)

        # Preferred personality
        if preferred_personality := user_props.get("preferred_personality"):
            try:
                context.preferred_personality = Personality(preferred_personality)
            except ValueError:
                logger.debug(f"Unknown preferred_personality value: {preferred_personality}")

        # Preferred tone
        if preferred_tone := user_props.get("preferred_tone"):
            try:
                context.preferred_tone = ResponseTone(preferred_tone)
            except ValueError:
                logger.debug(f"Unknown preferred_tone value: {preferred_tone}")

        # Preferred guidance
        if preferred_guidance := user_props.get("preferred_guidance"):
            try:
                context.preferred_guidance = GuidanceMode(preferred_guidance)
            except ValueError:
                logger.debug(f"Unknown preferred_guidance value: {preferred_guidance}")

    def populate_life_path(self, context: "UserContext", life_path_data: dict[str, Any]) -> None:
        """
        Populate life path fields from MEGA-QUERY life_path section.

        Args:
            context: UserContext to populate
            life_path_data: The "life_path" section from MEGA-QUERY results
        """
        if not life_path_data:
            return

        # Life path UID
        if life_path_uid := life_path_data.get("uid"):
            context.life_path_uid = life_path_uid

        # Alignment score
        if alignment_score := life_path_data.get("alignment_score"):
            context.life_path_alignment_score = float(alignment_score)

    def populate_activity_report(
        self, context: "UserContext", records: list[dict[str, Any]]
    ) -> None:
        """Populate latest activity report reference fields.

        records: 0 or 1 dicts from LATEST_ACTIVITY_REPORT_QUERY.
        No records = user has no activity reports yet; fields remain None.
        """
        if not records:
            return
        r = records[0]
        if not r.get("uid"):
            return
        context.latest_activity_report_uid = r["uid"]
        context.latest_activity_report_period = r.get("period")
        context.latest_activity_report_generated_at = r.get("period_end")
        context.latest_activity_report_content = r.get("content")

    def populate_moc_fields(self, context: "UserContext", uids_data: dict[str, Any]) -> None:
        """
        Populate MOC fields from MEGA-QUERY uids section.

        Args:
            context: UserContext to populate
            uids_data: The "uids" section from MEGA-QUERY results
        """
        # Active MOC UIDs
        context.active_moc_uids = [uid for uid in uids_data.get("active_moc_uids", []) if uid]

        # MOC metadata (view counts and recently viewed)
        moc_metadata = uids_data.get("moc_metadata", [])
        context.moc_view_counts = {
            item["uid"]: item["view_count"]
            for item in moc_metadata
            if item and item.get("uid") is not None
        }

        # Recently viewed MOCs (sorted by updated timestamp)
        context.recently_viewed_moc_uids = [
            item["uid"]
            for item in sorted(
                [i for i in moc_metadata if i and i.get("uid")],
                key=get_updated_timestamp,
                reverse=True,
            )[:10]
        ]

    def populate_progress_metrics(
        self, context: "UserContext", progress_counts: dict[str, Any]
    ) -> None:
        """
        Populate progress metrics from MEGA-QUERY progress_counts section.

        Args:
            context: UserContext to populate
            progress_counts: The "progress_counts" section from MEGA-QUERY results
        """
        if not progress_counts:
            return

        tasks_total = progress_counts.get("tasks_total", 0)
        tasks_completed = progress_counts.get("tasks_completed", 0)

        if tasks_total > 0:
            context.overall_progress = tasks_completed / tasks_total

    def populate_derived_fields(
        self,
        context: "UserContext",
        tasks_rich: list[dict[str, Any]],
        habits_rich: list[dict[str, Any]],
    ) -> None:
        """
        Populate derived fields (tasks_by_goal, habits_by_goal, etc.) from rich data.

        Args:
            context: UserContext to populate
            tasks_rich: Rich task data from MEGA-QUERY
            habits_rich: Rich habit data from MEGA-QUERY
        """
        # Build tasks_by_goal (inverse of task_goal_associations)
        tasks_by_goal: dict[str, list[str]] = {}
        blocked_task_uids: set[str] = set()

        for task_item in tasks_rich:
            if not task_item:
                continue
            task_data = task_item.get("task", {})
            graph_ctx = task_item.get("graph_context", {})
            task_uid = task_data.get("uid")

            if not task_uid:
                continue

            # Extract goal association
            goal_ctx = graph_ctx.get("goal_context")
            if goal_ctx and goal_ctx.get("uid"):
                goal_uid = goal_ctx["uid"]
                tasks_by_goal.setdefault(goal_uid, []).append(task_uid)

            # Extract blocked tasks (tasks that have incomplete dependencies)
            dependencies = graph_ctx.get("dependencies", [])
            for dep in dependencies:
                if dep and dep.get("uid"):
                    # If task has dependencies, it may be blocked
                    # The blocker logic is already computed in task_blockers
                    pass

        context.tasks_by_goal = tasks_by_goal

        # Build habits_by_goal from habits_rich
        habits_by_goal: dict[str, list[str]] = {}
        at_risk_habits: list[str] = []

        for habit_item in habits_rich:
            if not habit_item:
                continue
            habit_data = habit_item.get("habit", {})
            graph_ctx = habit_item.get("graph_context", {})
            habit_uid = habit_data.get("uid")

            if not habit_uid:
                continue

            # Extract linked goals
            linked_goals = graph_ctx.get("linked_goals", [])
            for goal in linked_goals:
                if goal and goal.get("uid"):
                    habits_by_goal.setdefault(goal["uid"], []).append(habit_uid)

            # Compute at-risk habits (streak == 0 or low completion rate)
            streak = context.habit_streaks.get(habit_uid, 0)
            completion_rate = context.habit_completion_rates.get(habit_uid, 0.0)
            if streak == 0 or completion_rate < 0.5:
                at_risk_habits.append(habit_uid)

        context.habits_by_goal = habits_by_goal
        context.at_risk_habits = at_risk_habits

        # Compute blocked_task_uids from task_blockers (already populated by graph-sourced)
        for blocked_uids in context.task_blockers.values():
            blocked_task_uids.update(blocked_uids)
        context.blocked_task_uids = blocked_task_uids

    def populate_principle_choice_integration(
        self,
        context: "UserContext",
        principles_rich: list[dict[str, Any]],
        choices_rich: list[dict[str, Any]],
    ) -> None:
        """
        Populate principle-choice integration fields from rich data.

        Args:
            context: UserContext to populate
            principles_rich: Rich principle data from MEGA-QUERY
            choices_rich: Rich choice data from MEGA-QUERY
        """
        principle_guided_choice_counts: dict[str, int] = {}
        principle_aligned_choices: list[str] = []

        for principle_item in principles_rich:
            if not principle_item:
                continue
            principle_data = principle_item.get("principle", {})
            graph_ctx = principle_item.get("graph_context", {})
            principle_uid = principle_data.get("uid")

            if not principle_uid:
                continue

            # Extract guided choices
            guided_choices = graph_ctx.get("guided_choices", [])
            if guided_choices:
                principle_guided_choice_counts[principle_uid] = len(guided_choices)
                for choice in guided_choices:
                    if choice and choice.get("uid"):
                        principle_aligned_choices.append(choice["uid"])

        context.principle_guided_choice_counts = principle_guided_choice_counts

        # Compute integration score
        total_choices = len(choices_rich)
        aligned_count = len(set(principle_aligned_choices))
        context.principle_integration_score = (
            aligned_count / total_choices if total_choices > 0 else 0.0
        )

        # Store recent principle-aligned choices (last 10)
        context.recent_principle_aligned_choices = principle_aligned_choices[:10]
