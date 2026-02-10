"""
Planning Mixin - UserContext-Aware Planning Methods
=====================================================

Provides UserContext-aware planning methods that can be mixed into
the UnifiedRelationshipService, enabling context-first queries like:
- get_actionable_for_user()
- get_at_risk_habits_for_user()
- get_upcoming_events_for_user()
- get_actionable_tasks_for_user()
- get_advancing_goals_for_user()
- get_pending_decisions_for_user()
- get_aligned_principles_for_user()

These methods leverage UserContext (~240 fields) for filtering and ranking.

**Domain-Specific Methods (January 2026):**
The DailyPlanningMixin in UserContextIntelligence expects these domain-specific
methods on all Activity Domain relationship services (UnifiedRelationshipService).
Each method works regardless of the current domain but returns domain-appropriate
results when called on the correct service.

Version: 2.0.0
Date: 2026-01-15
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.models.relationship_names import RelationshipName
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import (
    get_core_and_alignment,
    get_days_until_and_priority,
    get_overdue_and_priority,
    get_priority_score,
    get_result_score,
    get_risk_progress_priority,
    get_streak_and_priority,
)

if TYPE_CHECKING:
    from core.models.relationship_registry import DomainRelationshipConfig
    from core.services.user.unified_user_context import UserContext

T = TypeVar("T")


class PlanningMixin:
    """
    Mixin providing UserContext-aware planning methods.

    Methods follow the naming convention *_for_user() to indicate
    that they leverage UserContext for personalization.

    Philosophy: "Filter by readiness, rank by relevance, enrich with insights"

    Usage:
        class UnifiedRelationshipService(PlanningMixin, BaseService):
            pass

    Required Attributes (provided by the class using this mixin):
        - config: RelationshipConfig
        - backend: Any backend with list() and execute_query() methods
        - logger: logging.Logger

    Note: Backend type is Any to avoid conflicts with BaseService's
    BackendOperations[T] type. The actual backend is provided by
    the class that uses this mixin.
    """

    # These will be provided by the service class
    # Using Any for backend to avoid type conflicts with BaseService
    config: DomainRelationshipConfig
    backend: Any
    logger: Any

    @with_error_handling("get_actionable_for_user", error_type="database")
    async def get_actionable_for_user(
        self,
        context: UserContext,
        limit: int = 10,
        include_learning: bool = True,
    ) -> Result[list[Any]]:
        """
        Get actionable entities for user based on their context.

        "Actionable" means:
        - No blocking prerequisites
        - User has required knowledge mastery
        - Not already completed
        - Relevant to active goals

        Context Fields Used:
        - knowledge_mastery: Filter by user's mastery levels
        - completed_*_uids: Exclude completed items
        - active_goal_uids: Prioritize goal-aligned items
        - overdue_*_uids: Boost urgency

        Args:
            context: User's complete context (~240 fields)
            limit: Maximum number of items to return
            include_learning: Include learning-related items

        Returns:
            Result containing list of actionable entities, ranked by relevance
        """
        # Get all user entities for this domain
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        # Build filter for user's entities
        list_result = await self.backend.list(
            filters={"user_uid": user_uid},
            limit=limit * 3,  # Get extra for filtering
        )

        if list_result.is_error:
            return Result.fail(list_result.expect_error())

        # list() returns tuple[list[T], int]
        entities, _ = list_result.value

        # Filter and score each entity
        scored_entities = []
        for entity in entities:
            # Skip completed entities
            if self._is_completed(entity, context):
                continue

            # Calculate readiness score
            readiness = await self._calculate_readiness_score(entity, context)
            if readiness < 0.5:  # Not ready
                continue

            # Calculate relevance score
            relevance = self._calculate_relevance_score(entity, context)

            # Combined score
            score = readiness * 0.4 + relevance * 0.6

            # Urgency boost
            if self._is_urgent(entity, context):
                score *= 1.3

            scored_entities.append((entity, score))

        # Sort by score descending
        scored_entities.sort(key=get_result_score, reverse=True)

        # Return top N
        result_entities = [e for e, _ in scored_entities[:limit]]

        self.logger.debug(
            f"Found {len(result_entities)} actionable {domain_name}s for user {user_uid}"
        )

        return Result.ok(result_entities)

    @with_error_handling("get_blocked_for_user", error_type="database")
    async def get_blocked_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get entities blocked by unmet prerequisites.

        Returns entities with their blocking reasons, helping users
        understand what they need to do to unblock progress.

        Args:
            context: User's complete context
            limit: Maximum number of items to return

        Returns:
            Result containing list of dicts with entity and blocking_reasons
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        list_result = await self.backend.list(filters={"user_uid": user_uid}, limit=limit * 2)

        if list_result.is_error:
            return list_result

        # list() returns tuple[list[T], int]
        entities, _ = list_result.value
        blocked = []

        for entity in entities:
            if self._is_completed(entity, context):
                continue

            readiness = await self._calculate_readiness_score(entity, context)
            if readiness >= 0.5:  # Not blocked
                continue

            # Get blocking reasons
            reasons = await self._identify_blocking_reasons(entity, context)
            if reasons:
                blocked.append(
                    {
                        domain_name: entity,
                        "blocking_reasons": reasons,
                        "readiness_score": readiness,
                    }
                )

        return Result.ok(blocked[:limit])

    @with_error_handling("get_learning_related_for_user", error_type="database")
    async def get_learning_related_for_user(
        self,
        context: UserContext,
        knowledge_focus: str | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get entities that apply or develop specific knowledge.

        Filters for entities that:
        - Apply knowledge the user is learning
        - Develop skills at appropriate level
        - Align with user's learning goals

        Args:
            context: User's complete context
            knowledge_focus: Optional specific knowledge UID to focus on
            limit: Maximum number of items

        Returns:
            Result containing learning-related entities
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        # Get entities with knowledge relationships
        entity_label = self.config.entity_label
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_{domain_name.upper()}]->(e:{entity_label})
        MATCH (e)-[:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(k:Ku)
        {"WHERE k.uid = $knowledge_focus" if knowledge_focus else ""}
        RETURN DISTINCT e, collect(k.uid) as knowledge_uids
        LIMIT $limit
        """

        params = {
            "user_uid": user_uid,
            "limit": limit,
        }
        if knowledge_focus:
            params["knowledge_focus"] = knowledge_focus

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return result

        # Extract entities
        entities = [record.get("e") for record in result.value if record.get("e")]

        return Result.ok(entities)

    @with_error_handling("get_goal_aligned_for_user", error_type="database")
    async def get_goal_aligned_for_user(
        self,
        context: UserContext,
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get entities aligned with user's goals.

        Args:
            context: User's complete context
            goal_uid: Optional specific goal to filter by
            limit: Maximum number of items

        Returns:
            Result containing goal-aligned entities
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        # Build query based on domain's goal relationships
        goal_rels = [
            RelationshipName.FULFILLS_GOAL.value,
            RelationshipName.SUPPORTS_GOAL.value,
            RelationshipName.CONTRIBUTES_TO_GOAL.value,
        ]
        rel_pattern = "|".join(goal_rels)

        entity_label = self.config.entity_label
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_{domain_name.upper()}]->(e:{entity_label})
        MATCH (e)-[:{rel_pattern}]->(g:Goal)
        {"WHERE g.uid = $goal_uid" if goal_uid else ""}
        RETURN DISTINCT e, collect(g.uid) as goal_uids
        ORDER BY size(collect(g.uid)) DESC
        LIMIT $limit
        """

        params = {"user_uid": user_uid, "limit": limit}
        if goal_uid:
            params["goal_uid"] = goal_uid

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return result

        entities = [record.get("e") for record in result.value if record.get("e")]

        return Result.ok(entities)

    # =========================================================================
    # SCORING HELPERS
    # =========================================================================

    async def _calculate_readiness_score(
        self,
        entity: Any,
        context: UserContext,
    ) -> float:
        """
        Calculate readiness score (0-1) based on prerequisites met.

        Checks:
        - Prerequisite tasks completed
        - Prerequisite knowledge mastered
        - Prerequisite habits active
        """
        try:
            entity_uid = getattr(entity, "uid", None)
            if not entity_uid:
                return 0.0

            # Get prerequisites
            prereq_result = await self.get_related_uids("prerequisite_tasks", entity_uid)
            prereq_tasks = prereq_result.value if prereq_result.is_ok else []

            knowledge_result = await self.get_related_uids("prerequisite_knowledge", entity_uid)
            prereq_knowledge = knowledge_result.value if knowledge_result.is_ok else []

            if not prereq_tasks and not prereq_knowledge:
                return 1.0  # No prerequisites = fully ready

            # Check task prerequisites
            completed_tasks = set(getattr(context, "completed_task_uids", []) or [])
            tasks_met = sum(1 for t in prereq_tasks if t in completed_tasks)
            task_score = tasks_met / len(prereq_tasks) if prereq_tasks else 1.0

            # Check knowledge prerequisites
            mastery = getattr(context, "knowledge_mastery", {}) or {}
            knowledge_met = sum(1 for k in prereq_knowledge if mastery.get(k, 0) >= 0.7)
            knowledge_score = knowledge_met / len(prereq_knowledge) if prereq_knowledge else 1.0

            # Weighted average
            return task_score * 0.5 + knowledge_score * 0.5

        except Exception:
            return 0.5  # Default to uncertain

    def _calculate_relevance_score(
        self,
        entity: Any,
        context: UserContext,
    ) -> float:
        """
        Calculate relevance score (0-1) based on goal alignment.

        Considers:
        - Alignment with active goals
        - Priority level
        - Due date proximity
        """
        try:
            score = 0.5  # Base score

            # Priority boost
            priority = getattr(entity, "priority", None)
            if priority:
                priority_scores = {"urgent": 0.3, "high": 0.2, "medium": 0.1, "low": 0.0}
                score += priority_scores.get(str(priority).lower(), 0.0)

            # Goal alignment boost
            goal_uid = getattr(entity, "fulfills_goal_uid", None) or getattr(
                entity, "supports_goal_uid", None
            )
            active_goals = set(getattr(context, "active_goal_uids", []) or [])
            if goal_uid and goal_uid in active_goals:
                score += 0.2

            return min(score, 1.0)

        except Exception:
            return 0.5

    def _is_completed(self, entity: Any, context: UserContext) -> bool:
        """Check if entity is completed based on context."""
        entity_uid = getattr(entity, "uid", None)
        status = getattr(entity, "status", None)

        # Check status
        if status and str(status).lower() in ("completed", "done", "achieved"):
            return True

        # Check context completed lists
        domain_name = self.config.domain.value.rstrip("s")
        completed_field = f"completed_{domain_name}_uids"
        completed_uids = set(getattr(context, completed_field, []) or [])

        return entity_uid in completed_uids

    def _is_urgent(self, entity: Any, context: UserContext) -> bool:
        """Check if entity is urgent based on context."""
        entity_uid = getattr(entity, "uid", None)

        # Check overdue
        domain_name = self.config.domain.value.rstrip("s")
        overdue_field = f"overdue_{domain_name}_uids"
        overdue_uids = set(getattr(context, overdue_field, []) or [])

        if entity_uid in overdue_uids:
            return True

        # Check priority
        priority = getattr(entity, "priority", None)
        return bool(priority and str(priority).lower() == "urgent")

    async def _identify_blocking_reasons(
        self,
        entity: Any,
        context: UserContext,
    ) -> list[str]:
        """
        Identify what's blocking this entity.

        Returns human-readable reasons like:
        - "Requires completion of: task:123 (Setup database)"
        - "Requires knowledge mastery: ku:python (80% needed, you have 60%)"
        """
        reasons = []
        entity_uid = getattr(entity, "uid", None)
        if not entity_uid:
            return reasons

        try:
            # Check prerequisite tasks
            prereq_result = await self.get_related_uids("prerequisite_tasks", entity_uid)
            prereq_tasks = prereq_result.value if prereq_result.is_ok else []
            completed_tasks = set(getattr(context, "completed_task_uids", []) or [])

            for task_uid in prereq_tasks:
                if task_uid not in completed_tasks:
                    reasons.append(f"Requires completion of task: {task_uid}")

            # Check knowledge prerequisites
            knowledge_result = await self.get_related_uids("prerequisite_knowledge", entity_uid)
            prereq_knowledge = knowledge_result.value if knowledge_result.is_ok else []
            mastery = getattr(context, "knowledge_mastery", {}) or {}

            for ku_uid in prereq_knowledge:
                current_mastery = mastery.get(ku_uid, 0)
                if current_mastery < 0.7:
                    reasons.append(
                        f"Requires knowledge mastery: {ku_uid} "
                        f"(70% needed, you have {int(current_mastery * 100)}%)"
                    )

        except Exception as e:
            self.logger.warning(f"Error identifying blocking reasons: {e}")

        return reasons

    # =========================================================================
    # DOMAIN-SPECIFIC PLANNING METHODS (January 2026)
    # =========================================================================
    # These methods are called by DailyPlanningMixin in UserContextIntelligence.
    # Each returns domain-specific contextual entities.

    @with_error_handling("get_at_risk_habits_for_user", error_type="database")
    async def get_at_risk_habits_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get habits with streaks at risk of breaking.

        Context Fields Used:
        - at_risk_habits: UIDs of habits at risk
        - active_habits_rich: Rich habit data with context

        Returns:
            Result[list[ContextualHabit]] - habits needing attention
        """
        from core.models.context_types import ContextualHabit

        at_risk_uids = set(getattr(context, "at_risk_habits", []) or [])
        rich_habits = getattr(context, "active_habits_rich", []) or []

        contextual_habits = []
        for habit_data in rich_habits:
            habit_dict = habit_data.get("habit", {})
            uid = habit_dict.get("uid")
            if not uid or uid not in at_risk_uids:
                continue

            contextual = ContextualHabit.from_entity_and_context(
                uid=uid,
                title=habit_dict.get("title", ""),
                context=context,
                current_streak=habit_dict.get("current_streak", 0),
                days_since_last=habit_dict.get("days_since_last", 0),
                readiness_override=1.0,
                relevance_override=0.9,
                priority_override=0.95,
            )
            contextual_habits.append(contextual)

        contextual_habits.sort(key=get_streak_and_priority, reverse=True)

        return Result.ok(contextual_habits[:limit])

    @with_error_handling("get_upcoming_events_for_user", error_type="database")
    async def get_upcoming_events_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get upcoming events for today and near future.

        Context Fields Used:
        - today_event_uids: Events scheduled for today
        - upcoming_event_uids: Events scheduled for near future
        - active_events_rich: Rich event data with context

        Returns:
            Result[list[ContextualEvent]] - upcoming events
        """
        from core.models.context_types import ContextualEvent

        today_uids = set(getattr(context, "today_event_uids", []) or [])
        upcoming_uids = set(getattr(context, "upcoming_event_uids", []) or [])
        all_event_uids = today_uids | upcoming_uids
        rich_events = getattr(context, "active_events_rich", []) or []

        contextual_events = []
        for event_data in rich_events:
            event_dict = event_data.get("event", {})
            uid = event_dict.get("uid")
            if not uid or uid not in all_event_uids:
                continue

            is_today = uid in today_uids
            days_until = 0 if is_today else event_dict.get("days_until", 1)
            contextual = ContextualEvent.from_entity_and_context(
                uid=uid,
                title=event_dict.get("title", ""),
                context=context,
                days_until=days_until,
                duration_minutes=event_dict.get("duration_minutes", 30),
            )
            contextual_events.append(contextual)

        contextual_events.sort(key=get_days_until_and_priority)

        return Result.ok(contextual_events[:limit])

    @with_error_handling("get_actionable_tasks_for_user", error_type="database")
    async def get_actionable_tasks_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get tasks user can start immediately, ranked by priority.

        Context Fields Used:
        - active_tasks_rich: Rich task data with graph_context
        - overdue_task_uids: Overdue tasks (urgency boost)
        - knowledge_mastery: Knowledge mastery levels

        Returns:
            Result[list[ContextualTask]] - actionable tasks sorted by priority
        """
        from core.models.context_types import ContextualTask

        rich_tasks = getattr(context, "active_tasks_rich", []) or []
        overdue_uids = set(getattr(context, "overdue_task_uids", []) or [])
        mastery = getattr(context, "knowledge_mastery", {}) or {}

        contextual_tasks = []
        for task_data in rich_tasks:
            task_dict = task_data.get("task", {})
            uid = task_dict.get("uid")
            if not uid:
                continue

            graph_ctx = task_data.get("graph_context", {})

            # Check knowledge prerequisites
            knowledge_uids = [
                k.get("uid") for k in graph_ctx.get("applied_knowledge", []) if k.get("uid")
            ]
            prereq_met = (
                all(mastery.get(k, 0) >= 0.7 for k in knowledge_uids) if knowledge_uids else True
            )

            # Check task prerequisites
            prereq_tasks = [t.get("uid") for t in graph_ctx.get("dependencies", []) if t.get("uid")]
            completed_tasks = set(getattr(context, "completed_task_uids", []) or [])
            tasks_met = all(t in completed_tasks for t in prereq_tasks) if prereq_tasks else True

            if not prereq_met or not tasks_met:
                continue  # Not actionable

            is_overdue = uid in overdue_uids
            priority = task_dict.get("priority", "medium")
            priority_scores = {"urgent": 0.3, "high": 0.2, "medium": 0.1, "low": 0.0}
            base_priority = 0.5 + priority_scores.get(str(priority).lower(), 0.1)
            overdue_boost = 0.3 if is_overdue else 0

            contextual = ContextualTask.from_entity_and_context(
                uid=uid,
                title=task_dict.get("title", ""),
                context=context,
                prerequisite_knowledge=knowledge_uids,
                prerequisite_tasks=prereq_tasks,
                readiness_override=1.0,  # Passed all checks above
                relevance_override=0.7,
                priority_override=min(1.0, base_priority + overdue_boost),
            )
            contextual_tasks.append(contextual)

        contextual_tasks.sort(key=get_overdue_and_priority, reverse=True)

        return Result.ok(contextual_tasks[:limit])

    @with_error_handling("get_advancing_goals_for_user", error_type="database")
    async def get_advancing_goals_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get goals ready for progress advancement.

        Context Fields Used:
        - active_goal_uids: User's active goals
        - active_goals_rich: Rich goal data with context
        - at_risk_goals: Goals at risk (deprioritize)

        Returns:
            Result[list[ContextualGoal]] - goals to advance
        """
        from core.models.context_types import ContextualGoal

        active_goal_uids = set(getattr(context, "active_goal_uids", []) or [])
        rich_goals = getattr(context, "active_goals_rich", []) or []
        at_risk_uids = set(getattr(context, "at_risk_goals", []) or [])
        stalled_uids = set(context.get_stalled_goals())

        contextual_goals = []
        for goal_data in rich_goals:
            goal_dict = goal_data.get("goal", {})
            uid = goal_dict.get("uid")
            if not uid or uid not in active_goal_uids:
                continue

            if uid in stalled_uids:
                continue

            is_at_risk = uid in at_risk_uids
            progress = goal_dict.get("progress", 0.0)

            contextual = ContextualGoal.from_entity_and_context(
                uid=uid,
                title=goal_dict.get("title", ""),
                context=context,
                readiness_override=0.9 if not is_at_risk else 0.6,
                relevance_override=0.8,
                priority_override=0.7 + (progress * 0.2),
            )
            contextual_goals.append(contextual)

        contextual_goals.sort(key=get_risk_progress_priority, reverse=True)

        return Result.ok(contextual_goals[:limit])

    @with_error_handling("get_pending_decisions_for_user", error_type="database")
    async def get_pending_decisions_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get choices/decisions awaiting resolution.

        Context Fields Used:
        - pending_choice_uids: Pending choices
        - recent_choices_rich: Rich choice data with context

        Returns:
            Result[list[ContextualChoice]] - pending decisions
        """
        from core.models.context_types import ContextualChoice

        pending_uids = set(getattr(context, "pending_choice_uids", []) or [])
        rich_choices = getattr(context, "recent_choices_rich", []) or []

        contextual_choices = []
        for choice_data in rich_choices:
            choice_dict = choice_data.get("choice", {})
            uid = choice_dict.get("uid")
            if not uid or uid not in pending_uids:
                continue

            priority_level = str(choice_dict.get("priority", "medium")).lower()
            contextual = ContextualChoice.from_entity_and_context(
                uid=uid,
                title=choice_dict.get("title", ""),
                context=context,
                priority_level=priority_level,
            )
            contextual_choices.append(contextual)

        contextual_choices.sort(key=get_priority_score, reverse=True)

        return Result.ok(contextual_choices[:limit])

    @with_error_handling("get_aligned_principles_for_user", error_type="database")
    async def get_aligned_principles_for_user(
        self,
        context: UserContext,
        limit: int = 10,
    ) -> Result[list[Any]]:
        """
        Get principles aligned with user's active focus.

        Context Fields Used:
        - core_principle_uids: Core principles
        - core_principles_rich: Rich principle data with context

        Returns:
            Result[list[ContextualPrinciple]] - aligned principles
        """
        from core.models.context_types import ContextualPrinciple

        core_uids = set(getattr(context, "core_principle_uids", []) or [])
        rich_principles = getattr(context, "core_principles_rich", []) or []

        contextual_principles = []
        for principle_data in rich_principles:
            principle_dict = principle_data.get("principle", {})
            uid = principle_dict.get("uid")
            if not uid:
                continue

            alignment = principle_dict.get("alignment_score", 0.5)
            contextual = ContextualPrinciple.from_entity_and_context(
                uid=uid,
                title=principle_dict.get("title", ""),
                context=context,
                alignment_score=alignment,
            )
            contextual_principles.append(contextual)

        contextual_principles.sort(key=get_core_and_alignment, reverse=True)

        return Result.ok(contextual_principles[:limit])

    # Placeholder for get_related_uids - will be provided by the service
    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        """Get related UIDs - implemented by service."""
        raise NotImplementedError("Must be implemented by service class")
