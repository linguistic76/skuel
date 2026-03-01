"""
Planning Mixin - UserContext-Aware Planning Methods
=====================================================

Provides generic UserContext-aware planning methods that can be mixed into
the UnifiedRelationshipService, enabling context-first queries like:
- get_actionable_for_user()
- get_blocked_for_user()
- get_learning_related_for_user()
- get_goal_aligned_for_user()

These methods leverage UserContext (~240 fields) for filtering and ranking.

Domain-specific planning methods (get_at_risk_habits_for_user, etc.) live in
_domain_planning_mixin.py, which is also mixed into UnifiedRelationshipService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.models.relationship_names import RelationshipName
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score

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
        MATCH (e)-[:APPLIES_KNOWLEDGE|REQUIRES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(k:Entity)
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
        if status and str(status).lower() in ("completed", "done"):
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

    # Placeholder for get_related_uids - will be provided by the service
    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        """Get related UIDs - implemented by service."""
        raise NotImplementedError("Must be implemented by service class")
