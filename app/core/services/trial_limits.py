"""
Trial Limits Service
====================

Manages consumption limits for REGISTERED (free trial) users.

SKUEL uses a four-tier user role system:
- REGISTERED: Free trial (unlimited curriculum + activities)
- MEMBER: Paid subscription (unlimited access)
- TEACHER: Member + curriculum content creation
- ADMIN: Teacher + user management

Current Policy (December 2025):
- Curriculum domains (KU, LS, LP): UNLIMITED for all users
- Activity domains (Tasks, Goals, Habits, Events, Choices): UNLIMITED for all users
- Rate limiting (API calls): Reserved for future use

Use -1 to indicate unlimited for any limit.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import QueryExecutor

logger = get_logger("skuel.services.trial_limits")


# ============================================================================
# TRIAL LIMITS CONFIGURATION
# ============================================================================


# Constant for unlimited access
UNLIMITED = -1


@dataclass(frozen=True)
class TrialLimits:
    """
    Configuration for trial user limits.

    Use -1 (UNLIMITED) to indicate no limit for a category.

    Current policy: All curriculum and activity domains are unlimited.
    Rate limiting reserved for future use.
    """

    # Curriculum domains - UNLIMITED for all users
    max_knowledge_units: int = UNLIMITED  # KU access
    max_learning_steps: int = UNLIMITED  # LS access
    max_learning_paths: int = UNLIMITED  # LP enrollment

    # Activity domains - UNLIMITED for all users
    max_tasks: int = UNLIMITED
    max_goals: int = UNLIMITED
    max_habits: int = UNLIMITED
    max_events: int = UNLIMITED
    max_choices: int = UNLIMITED

    # Rate limiting (future use)
    max_daily_api_calls: int = 100


# Singleton configuration
TRIAL_LIMITS = TrialLimits()


# ============================================================================
# TRIAL LIMITS SERVICE
# ============================================================================


class TrialLimitsService:
    """
    Service for checking and enforcing trial limits.

    Pattern: Query current usage, compare to limits.

    Usage:
        # Check if user can create more tasks
        result = await trial_limits.check_limit(user_uid, "task")
        if result.is_error:
            return result  # Returns error with limit info

        # Get usage summary for UI
        summary = await trial_limits.get_usage_summary(user_uid)
    """

    def __init__(
        self,
        user_service: Any,
        executor: "QueryExecutor",
        limits: TrialLimits | None = None,
    ) -> None:
        """
        Initialize trial limits service.

        Args:
            user_service: UserService for user lookups
            executor: Query executor for usage queries
            limits: Optional custom limits (defaults to TRIAL_LIMITS)
        """
        if not user_service:
            raise ValueError("UserService is required")
        if not executor:
            raise ValueError("QueryExecutor is required")

        self.user_service = user_service
        self.executor = executor
        self.limits = limits or TRIAL_LIMITS

    async def check_limit(
        self,
        user_uid: str,
        entity_type: str,
    ) -> Result[bool]:
        """
        Check if user can create more entities of this type.

        Members and above have no limits.
        REGISTERED users have quota limits.

        Args:
            user_uid: User to check
            entity_type: One of: task, goal, habit, event, choice, ku_access, lp_enrollment

        Returns:
            Result[True] if allowed, Result.fail with limit info if exceeded

        Example:
            result = await trial_limits.check_limit("user_john", "task")
            if result.is_error:
                # User has reached trial limit
                return result
            # Proceed with creation
        """
        # Get user
        user_result = await self.user_service.get_user(user_uid)
        if user_result.is_error or not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Members and above have no limits
        if user.role.is_subscriber():
            logger.debug(f"User {user_uid} is {user.role.value} - no limits apply")
            return Result.ok(True)

        # REGISTERED users - check limits
        current_count = await self._get_entity_count(user_uid, entity_type)
        limit = self._get_limit(entity_type)

        # UNLIMITED (-1) or unknown entity type (0) means no limit
        if limit == UNLIMITED or limit == 0:
            if limit == 0:
                logger.warning(f"Unknown entity type for trial limits: {entity_type}")
            return Result.ok(True)

        if current_count >= limit:
            logger.info(
                f"Trial limit reached for {user_uid}: {current_count}/{limit} {entity_type}s"
            )
            return Result.fail(
                Errors.business(
                    rule="trial_limit",
                    message=(
                        f"Trial limit reached: {current_count}/{limit} {entity_type}s. "
                        f"Upgrade to Member for unlimited access."
                    ),
                )
            )

        logger.debug(
            f"Trial limit check passed for {user_uid}: {current_count}/{limit} {entity_type}s"
        )
        return Result.ok(True)

    async def get_usage_summary(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get trial usage summary for user.

        Returns usage vs limits for display in UI.

        Args:
            user_uid: User to check

        Returns:
            Result containing:
            - unlimited: bool (True if Member+)
            - role: str
            - usage: dict[entity_type, {current, limit, remaining}]

        Example:
            summary = await trial_limits.get_usage_summary("user_john")
            # Returns:
            # {
            #     "unlimited": False,
            #     "role": "registered",
            #     "usage": {
            #         "task": {"current": 5, "limit": 10, "remaining": 5},
            #         "goal": {"current": 2, "limit": 3, "remaining": 1},
            #         ...
            #     }
            # }
        """
        # Get user
        user_result = await self.user_service.get_user(user_uid)
        if user_result.is_error or not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Members and above have unlimited access
        if user.role.is_subscriber():
            return Result.ok(
                {
                    "unlimited": True,
                    "role": user.role.value,
                    "usage": {},
                }
            )

        # Build usage summary for REGISTERED users
        entity_types = [
            # Activity domains
            "task",
            "goal",
            "habit",
            "event",
            "choice",
            # Curriculum domains
            "ku_access",
            "ls_access",
            "lp_enrollment",
        ]

        usage = {}
        for entity_type in entity_types:
            count = await self._get_entity_count(user_uid, entity_type)
            limit = self._get_limit(entity_type)

            # Handle unlimited (-1) for UI display
            if limit == UNLIMITED:
                usage[entity_type] = {
                    "current": count,
                    "limit": "unlimited",
                    "remaining": "unlimited",
                    "unlimited": True,
                }
            else:
                usage[entity_type] = {
                    "current": count,
                    "limit": limit,
                    "remaining": max(0, limit - count),
                    "unlimited": False,
                }

        return Result.ok(
            {
                "unlimited": False,
                "role": user.role.value,
                "usage": usage,
            }
        )

    async def _get_entity_count(self, user_uid: str, entity_type: str) -> int:
        """
        Query current entity count for user.

        Args:
            user_uid: User UID
            entity_type: Entity type to count

        Returns:
            Current count of entities
        """
        query_map = {
            "task": """
                MATCH (u:User {uid: $uid})-[:HAS_TASK]->(t:Task)
                WHERE t.status <> 'archived'
                RETURN count(t) as count
            """,
            "goal": """
                MATCH (u:User {uid: $uid})-[:HAS_GOAL]->(g:Goal)
                WHERE g.status <> 'archived'
                RETURN count(g) as count
            """,
            "habit": """
                MATCH (u:User {uid: $uid})-[:HAS_HABIT]->(h:Habit)
                WHERE h.status <> 'archived'
                RETURN count(h) as count
            """,
            "event": """
                MATCH (u:User {uid: $uid})-[:HAS_EVENT]->(e:Event)
                RETURN count(e) as count
            """,
            "choice": """
                MATCH (u:User {uid: $uid})-[:MADE_CHOICE]->(c:Choice)
                RETURN count(c) as count
            """,
            "ku_access": """
                MATCH (u:User {uid: $uid})-[:LEARNING|MASTERED]->(k:Ku)
                RETURN count(DISTINCT k) as count
            """,
            "ls_access": """
                MATCH (u:User {uid: $uid})-[:COMPLETED_STEP]->(ls:Ls)
                RETURN count(DISTINCT ls) as count
            """,
            "lp_enrollment": """
                MATCH (u:User {uid: $uid})-[:ENROLLED_IN]->(lp:Lp)
                RETURN count(lp) as count
            """,
        }

        query = query_map.get(entity_type)
        if not query:
            logger.warning(f"Unknown entity type for count query: {entity_type}")
            return 0

        try:
            result = await self.executor.execute_query(query, {"uid": user_uid})
            if result.is_error:
                logger.error(f"Error counting {entity_type} for {user_uid}: {result.error}")
                return 0
            records = result.value
            return records[0]["count"] if records else 0
        except Exception as e:
            logger.error(f"Error counting {entity_type} for {user_uid}: {e}")
            return 0

    def _get_limit(self, entity_type: str) -> int:
        """
        Get limit for entity type.

        Args:
            entity_type: Entity type

        Returns:
            Limit for this entity type (0 if unknown, -1 if unlimited)
        """
        limit_map = {
            # Activity domains
            "task": self.limits.max_tasks,
            "goal": self.limits.max_goals,
            "habit": self.limits.max_habits,
            "event": self.limits.max_events,
            "choice": self.limits.max_choices,
            # Curriculum domains
            "ku_access": self.limits.max_knowledge_units,
            "ls_access": self.limits.max_learning_steps,
            "lp_enrollment": self.limits.max_learning_paths,
        }
        return limit_map.get(entity_type, 0)


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_trial_limits_service(
    user_service: Any,
    executor: "QueryExecutor",
    limits: TrialLimits | None = None,
) -> TrialLimitsService:
    """
    Factory function to create a TrialLimitsService.

    Args:
        user_service: UserService for user lookups
        executor: Query executor for database queries
        limits: Optional custom limits

    Returns:
        TrialLimitsService instance
    """
    return TrialLimitsService(user_service, executor, limits)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "TRIAL_LIMITS",
    "UNLIMITED",
    "TrialLimits",
    "TrialLimitsService",
    "create_trial_limits_service",
]
