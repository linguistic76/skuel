"""Activity Domain backends: Habits, Goals, Tasks, Events, Choices, Principles."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j._hierarchy_mixin import HierarchyConfig, _HierarchyMixin
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    ChoiceStats,
    EventStats,
    GoalStats,
    HabitStats,
    ParentProgressResult,
    PrincipleStats,
    TaskStats,
)
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from datetime import date

    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401
    from core.models.forms.form_template import FormTemplate  # noqa: F401
    from core.models.group.group import Group  # noqa: F401
    from core.models.interaction.interaction import Interaction  # noqa: F401
    from core.models.report_schedule import ReportSchedule  # noqa: F401
    from core.models.resource.resource import Resource  # noqa: F401


async def _count_user_stats(
    backend: UniversalNeo4jBackend[Any],
    user_uid: UserUID,
    entity_type: str,
    cases: dict[str, str],
    extra_params: dict[str, Any] | None = None,
) -> Result[dict[str, int]]:
    """
    Count per-user entity stats in one Cypher aggregate.

    THE shared body of the six domain get_stats_for_user methods — each
    domain supplies a spec dict of {result_key: CASE predicate on ``n``}.
    Predicates are backend-internal literals (injection-safe); any values
    they reference are parameterized via ``extra_params``.
    """
    case_lines = ",\n            ".join(
        f"count(CASE WHEN {predicate} THEN 1 END) AS {key}" for key, predicate in cases.items()
    )
    query = f"""
    MATCH (n:Entity {{user_uid: $user_uid, entity_type: $entity_type}})
    RETURN
        count(n) AS total,
        {case_lines}
    """
    result = await backend.execute_query(
        query, {"user_uid": user_uid, "entity_type": entity_type, **(extra_params or {})}
    )
    if result.is_error:
        return Result.fail(result)
    record = result.value[0] if result.value else {}
    return Result.ok(
        {"total": record.get("total", 0), **{key: record.get(key, 0) for key in cases}}
    )


async def _edge_targets(
    backend: UniversalNeo4jBackend[Any],
    source_entity_type: str,
    rel_type: str,
    source_uids: list[str],
    target_entity_type: str | None = None,
) -> Result[list[tuple[str, str]]]:
    """
    Batch-fetch (source_uid, target_uid) pairs for one edge type.

    THE shared query behind the label-swapped link-map clones
    (task→habit, event→habit, habit→goal, event→goal enrichment lookups).
    ``rel_type`` is a RelationshipName value; entity types are parameterized.
    """
    if not source_uids:
        return Result.ok([])

    target_part = "(t:Entity {entity_type: $target_type})" if target_entity_type else "(t:Entity)"
    params: dict[str, Any] = {"uids": source_uids, "source_type": source_entity_type}
    if target_entity_type:
        params["target_type"] = target_entity_type

    query = f"""
    MATCH (s:Entity {{entity_type: $source_type}})-[:{rel_type}]->{target_part}
    WHERE s.uid IN $uids
    RETURN s.uid AS source_uid, t.uid AS target_uid
    """
    result = await backend.execute_query(query, params)
    if result.is_error:
        return Result.fail(result)
    return Result.ok([(row["source_uid"], row["target_uid"]) for row in (result.value or [])])


async def _edge_map_single(
    backend: UniversalNeo4jBackend[Any],
    source_entity_type: str,
    rel_type: str,
    source_uids: list[str],
) -> Result[dict[str, str]]:
    """Edge map for single-valued links: source_uid → target_uid (last row wins)."""
    pairs = await _edge_targets(backend, source_entity_type, rel_type, source_uids)
    if pairs.is_error:
        return Result.fail(pairs)
    return Result.ok(dict(pairs.value))


async def _edge_map_multi(
    backend: UniversalNeo4jBackend[Any],
    source_entity_type: str,
    rel_type: str,
    source_uids: list[str],
    target_entity_type: str | None = None,
) -> Result[dict[str, list[str]]]:
    """Edge map for multi-valued links: source_uid → all linked target_uids."""
    pairs = await _edge_targets(
        backend, source_entity_type, rel_type, source_uids, target_entity_type
    )
    if pairs.is_error:
        return Result.fail(pairs)
    link_map: dict[str, list[str]] = {}
    for source_uid, target_uid in pairs.value:
        link_map.setdefault(source_uid, []).append(target_uid)
    return Result.ok(link_map)


class HabitsBackend(_HierarchyMixin, UniversalNeo4jBackend[Habit]):
    """
    Domain backend for Habit entities.

    Extends UniversalNeo4jBackend[Habit] with:
    - _HierarchyMixin: subhabit hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_habit(uid)          → get_or_fail() wrapper (NotFound as error)
    - get_user_habits(uid)    → alias for inherited list_by_user()
    - archive_habit(uid)      → status transition (not just delete)
    - get_stats_for_user(uid) → habit count stats (total/active/streaks)
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBHABIT.value,
        inverse_rel=RelationshipName.SUBHABIT_OF.value,
        node_label=NeoLabel.HABIT,
        domain_name="subhabit",
    )

    async def get_habit(self, habit_id: str) -> Result[Habit]:
        """Get habit by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(habit_id)

    async def get_user_habits(self, user_uid: UserUID) -> Result[list[Habit]]:
        """Get all habits for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def archive_habit(self, habit_id: str) -> Result[bool]:
        """Archive a habit by transitioning its status to 'archived'."""
        update_result: Result[Habit] = await self.update(habit_id, {"status": "archived"})
        if update_result.is_error:
            return Result.fail(update_result)
        return Result.ok(True)

    async def get_active_habits_prioritized(
        self,
        user_uid: UserUID,
        terminal_statuses: list[str],
        limit: int = 20,
    ) -> Result[list[Neo4jProperties]]:
        """Get active habits for a user, pre-sorted for prioritization.

        Fetches habits not in terminal statuses, sorted by streak-at-risk
        first, then by streak length and recency.

        Args:
            user_uid: Owner of the habits.
            terminal_statuses: Status values to exclude.
            limit: Maximum results.

        Returns:
            Result containing list of habit node properties.
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(h:Habit)
        WHERE NOT h.status IN $terminal_statuses
        RETURN h
        ORDER BY
            CASE WHEN h.current_streak > 0 AND date(datetime(h.last_completed)) < date() THEN 0 ELSE 1 END,
            h.current_streak DESC,
            h.created_at DESC
        LIMIT $fetch_limit
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "terminal_statuses": terminal_statuses,
                "fetch_limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["h"] for record in result.value])

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[HabitStats]:
        """Count habit stats: total, active, streaks."""
        result = await _count_user_stats(
            self,
            user_uid,
            "habit",
            {"active": "n.status = 'active'", "streaks": "n.current_streak > 0"},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("HabitStats", result.value))

    async def get_user_badges(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all badges earned by a user via EARNED_BADGE relationships."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier,
               r.earned_at as earned_at,
               r.streak_length as streak_length,
               r.habit_uid as habit_uid
        ORDER BY r.earned_at DESC
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return result
        return Result.ok(result.value or [])

    async def get_habit_badges(self, habit_uid: str) -> Result[list[Neo4jProperties]]:
        """Get all badges unlocked by a specific habit via UNLOCKED_ACHIEVEMENT."""
        query = f"""
        MATCH (habit:Habit {{uid: $habit_uid}})-[:{RelationshipName.UNLOCKED_ACHIEVEMENT.value}]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier
        ORDER BY badge.tier
        """
        result = await self.execute_query(query, {"habit_uid": habit_uid})
        if result.is_error:
            return result
        return Result.ok(result.value or [])

    async def check_badge_already_earned(
        self, user_uid: UserUID, habit_uid: str, badge_id: str
    ) -> Result[bool]:
        """Check if user has already earned this badge for this habit."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[r:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement {{badge_id: $badge_id}})
        WHERE r.habit_uid = $habit_uid
        RETURN count(r) > 0 as already_earned
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "habit_uid": habit_uid, "badge_id": badge_id},
        )
        if result.is_error or not result.value:
            return Result.ok(False)
        return Result.ok(result.value[0].get("already_earned", False))

    async def award_badge(
        self,
        user_uid: UserUID,
        habit_uid: str,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        streak_length: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record and link to user and habit."""
        query = f"""
        // Get or create achievement badge
        MERGE (badge:Achievement {{badge_id: $badge_id}})
        ON CREATE SET
            badge.name = $badge_name,
            badge.description = $badge_description,
            badge.tier = $badge_tier,
            badge.created_at = datetime()

        // Get user and habit
        WITH badge
        MATCH (user:User {{uid: $user_uid}})
        MATCH (habit:Habit {{uid: $habit_uid}})

        // Idempotent EARNED_BADGE relationship
        MERGE (user)-[r:{RelationshipName.EARNED_BADGE.value} {{
            habit_uid: $habit_uid
        }}]->(badge)
        ON CREATE SET
            r.earned_at = datetime($occurred_at),
            r.streak_length = $streak_length

        // Also link achievement to the habit for context
        MERGE (habit)-[:{RelationshipName.UNLOCKED_ACHIEVEMENT.value}]->(badge)

        RETURN badge.badge_id as badge_id
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "habit_uid": habit_uid,
                "badge_id": badge_id,
                "badge_name": badge_name,
                "badge_description": badge_description,
                "badge_tier": badge_tier,
                "streak_length": streak_length,
                "occurred_at": occurred_at,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def check_user_badge_earned(self, user_uid: UserUID, badge_id: str) -> Result[bool]:
        """Check if user has earned a badge (cross-habit, no habit_uid filter)."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.EARNED_BADGE.value}]->(badge:Achievement {{badge_id: $badge_id}})
        RETURN count(*) > 0 as already_earned
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "badge_id": badge_id})
        if result.is_error or not result.value:
            return Result.ok(False)
        return Result.ok(result.value[0].get("already_earned", False))

    async def award_user_badge(
        self,
        user_uid: UserUID,
        badge_id: str,
        badge_name: str,
        badge_description: str,
        badge_tier: str,
        badge_category: str,
        threshold_value: int,
        occurred_at: str,
    ) -> Result[bool]:
        """Create achievement record linked to user only (cross-habit badges)."""
        query = f"""
        MERGE (badge:Achievement {{badge_id: $badge_id}})
        ON CREATE SET
            badge.name = $badge_name,
            badge.description = $badge_description,
            badge.tier = $badge_tier,
            badge.category = $badge_category,
            badge.created_at = datetime()

        WITH badge
        MATCH (user:User {{uid: $user_uid}})

        MERGE (user)-[r:{RelationshipName.EARNED_BADGE.value} {{
            badge_category: $badge_category
        }}]->(badge)
        ON CREATE SET
            r.earned_at = datetime($occurred_at),
            r.threshold_value = $threshold_value

        RETURN badge.badge_id as badge_id
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "badge_id": badge_id,
                "badge_name": badge_name,
                "badge_description": badge_description,
                "badge_tier": badge_tier,
                "badge_category": badge_category,
                "threshold_value": threshold_value,
                "occurred_at": occurred_at,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(True)

    async def get_user_badge_stats(self, user_uid: UserUID) -> Result[Neo4jProperties]:
        """Get aggregated habit stats for badge evaluation in a single query.

        Returns:
            Dict with total_completions, high_quality_completions,
            max_identity_votes, established_identity_count.
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[:OWNS]->(h:Habit:Entity)
        WITH user,
             sum(coalesce(h.total_completions, 0)) AS total_completions,
             max(CASE WHEN h.is_identity_habit = true
                 THEN coalesce(h.identity_votes_cast, 0) ELSE 0 END) AS max_identity_votes,
             sum(CASE WHEN h.is_identity_habit = true
                 AND coalesce(h.identity_votes_cast, 0) >= 50 THEN 1 ELSE 0 END
             ) AS established_identity_count
        OPTIONAL MATCH (user)-[:OWNS]->(hc:HabitCompletion)
        WHERE hc.quality IS NOT NULL AND hc.quality >= 4
        RETURN total_completions,
               count(hc) AS high_quality_completions,
               max_identity_votes,
               established_identity_count
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(
                {
                    "total_completions": 0,
                    "high_quality_completions": 0,
                    "max_identity_votes": 0,
                    "established_identity_count": 0,
                }
            )
        return Result.ok(result.value[0])

    async def get_goal_links_for_habits(
        self, habit_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        """Map habit_uid → list of supporting goal_uids via SUPPORTS_GOAL edges (batch).

        Batch-lookup of the SUPPORTS_GOAL edge, used to enrich habits with
        their derived ``supports_goal_uid`` field for scoring. Returns all
        linked goals per habit so the enricher can prefer active ones.
        """
        return await _edge_map_multi(
            self,
            "habit",
            RelationshipName.SUPPORTS_GOAL.value,
            habit_uids,
            target_entity_type="goal",
        )


class GoalsBackend(_HierarchyMixin, UniversalNeo4jBackend[Goal]):
    """
    Domain backend for Goal entities.

    Extends UniversalNeo4jBackend[Goal] with:
    - _HierarchyMixin: subgoal hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_goal(uid)          → get_or_fail() wrapper (NotFound as error)
    - get_user_goals(uid)    → alias for inherited list_by_user()
    - get_stats_for_user(uid) → goal count stats (total/active/completed)
    - link_goal_to_habit    → Cypher MERGE
    - link_goal_to_knowledge → Cypher MERGE
    - link_goal_to_principle → Cypher MERGE
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBGOAL.value,
        inverse_rel=RelationshipName.SUBGOAL_OF.value,
        node_label=NeoLabel.ENTITY,
        domain_name="subgoal",
    )

    async def get_goal(self, goal_id: str) -> Result[Goal]:
        """Get goal by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(goal_id)

    async def get_user_goals(self, user_uid: UserUID) -> Result[list[Goal]]:
        """Get all goals for a user. Returns flat list (not paginated tuple)."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[GoalStats]:
        """Count goal stats: total, active, completed."""
        result = await _count_user_stats(
            self,
            user_uid,
            "goal",
            {"active": "n.status = 'active'", "completed": "n.status = 'completed'"},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("GoalStats", result.value))

    async def _find_linked_goals(
        self, target_uid: str, user_uid: UserUID, target_type: EntityType
    ) -> Result[list[str]]:
        """UIDs of the user's goals that SUPPORTS_GOAL a given activity entity.

        The target's ``entity_type`` is a guard, not a lookup key — ``uid``
        already pins the node, so a uid/type mismatch correctly yields no goals.
        """
        query = f"""
        MATCH (goal:Entity {{entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(target:Entity {{uid: $target_uid, entity_type: $target_type}})
        WHERE goal.user_uid = $user_uid
        RETURN goal.uid as goal_uid
        """
        result = await self.execute_query(
            query,
            {
                "target_uid": target_uid,
                "user_uid": user_uid,
                "target_type": target_type.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["goal_uid"] for record in (result.value or [])])

    async def find_linked_goals_for_task(
        self, task_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a task via SUPPORTS_GOAL."""
        return await self._find_linked_goals(task_uid, user_uid, EntityType.TASK)

    async def count_linked_tasks(self, goal_uid: str, user_uid: UserUID) -> Result[dict[str, int]]:
        """Count total and completed tasks linked to a goal via SUPPORTS_GOAL."""
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(task:Entity {{entity_type: 'task'}})
        WHERE task.user_uid = $user_uid
        WITH count(task) as total_tasks
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(completed:Entity {{entity_type: 'task'}})
        WHERE completed.user_uid = $user_uid
          AND completed.status = 'completed'
        RETURN total_tasks, count(completed) as completed_tasks
        """
        result = await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total_tasks": record.get("total_tasks", 0),
                "completed_tasks": record.get("completed_tasks", 0),
            }
        )

    async def find_linked_goals_for_habit(
        self, habit_uid: str, user_uid: UserUID
    ) -> Result[list[str]]:
        """Find goal UIDs linked to a habit via SUPPORTS_GOAL."""
        return await self._find_linked_goals(habit_uid, user_uid, EntityType.HABIT)

    async def count_linked_habits_avg_streak(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[dict[str, Any]]:
        """Count habits linked to a goal and compute their average streak."""
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WHERE habit.user_uid = $user_uid
        WITH count(habit) as total_habits
        MATCH (goal:Entity {{uid: $goal_uid, entity_type: 'goal'}})-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WHERE habit.user_uid = $user_uid
        RETURN total_habits, avg(COALESCE(habit.current_streak, 0)) as avg_streak
        """
        result = await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(
            {
                "total_habits": record.get("total_habits", 0),
                "avg_streak": record.get("avg_streak", 0),
            }
        )

    async def get_achievement_context(
        self, goal_uid: str, user_uid: UserUID
    ) -> Result[list[dict[str, Any]]]:
        """Fetch goal properties and related entities for recommendation generation.

        Returns goal domain/type/timeframe plus related knowledge units, habits,
        and principles — all the context needed to generate next-step recommendations
        after a GoalAchieved event.

        Args:
            goal_uid: UID of the achieved goal
            user_uid: Owner of the goal

        Returns:
            Result containing a list with one record (or empty list if not found)
        """
        query = f"""
        MATCH (goal:Entity {{uid: $goal_uid, user_uid: $user_uid, entity_type: 'goal'}})

        OPTIONAL MATCH (goal)-[:{RelationshipName.REQUIRES_KNOWLEDGE.value}]->(ku:Entity)
        WHERE ku.entity_type = 'knowledge_unit'
        WITH goal, collect(DISTINCT {{uid: ku.uid, title: ku.title, domain: ku.domain}}) as knowledge_units

        OPTIONAL MATCH (goal)-[:{RelationshipName.SUPPORTS_GOAL.value}]->(habit:Entity {{entity_type: 'habit'}})
        WITH goal, knowledge_units, collect(DISTINCT {{uid: habit.uid, title: habit.title}}) as habits

        OPTIONAL MATCH (goal)-[:{RelationshipName.GUIDED_BY_PRINCIPLE.value}]->(principle:Entity {{entity_type: 'principle'}})
        WITH goal, knowledge_units, habits, collect(DISTINCT {{uid: principle.uid, title: principle.title}}) as principles

        RETURN goal.uid as uid,
               goal.title as title,
               goal.domain as domain,
               goal.goal_type as goal_type,
               goal.timeframe as timeframe,
               knowledge_units,
               habits,
               principles
        """
        return await self.execute_query(query, {"goal_uid": goal_uid, "user_uid": user_uid})


class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]):
    """
    Domain backend for Task entities.

    Extends UniversalNeo4jBackend[Task] with:
    - _HierarchyMixin: subtask hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_task(uid)              → get_or_fail() wrapper (NotFound as error)
    - get_stats_for_user(…)      → task count stats (total/completed/overdue)
    - calculate_parent_progress(…) → weighted subtask completion percentage
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBTASK.value,
        inverse_rel=RelationshipName.SUBTASK_OF.value,
        node_label=NeoLabel.ENTITY,
        domain_name="subtask",
    )

    async def get_task(self, task_id: str) -> Result[Task]:
        """Get task by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(task_id)

    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """Get all tasks for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_tasks_reinforcing_habit(self, habit_uid: str) -> Result[list[Neo4jProperties]]:
        """Return node props for tasks linked to a habit via REINFORCES_HABIT.

        Graph-native reverse traversal of ``(Task)-[:REINFORCES_HABIT]->(Habit)``.
        Replaces the former ``find_by(reinforces_habit_uid=...)`` property query.
        """
        query = """
        MATCH (t:Entity {entity_type: 'task'})-[:REINFORCES_HABIT]->(h:Entity {uid: $habit_uid})
        RETURN t
        """
        result = await self.execute_query(query, {"habit_uid": habit_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(row["t"]) for row in (result.value or [])])

    async def get_habit_links_for_tasks(self, task_uids: list[str]) -> Result[dict[str, str]]:
        """Map task_uid → reinforced habit_uid for the given tasks.

        Batch reverse-lookup of the REINFORCES_HABIT edge, used to populate the
        derived ``Task.reinforces_habit_uid`` field for in-memory scorers.
        """
        return await _edge_map_single(
            self, "task", RelationshipName.REINFORCES_HABIT.value, task_uids
        )

    # ========================================================================
    # LEARNING LOOP METHODS (ADR-048)
    # ========================================================================

    async def get_user_learning_state(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get learning state properties from User node for duration calibration."""
        query = """
        MATCH (u:User {uid: $user_uid})
        RETURN u.task_duration_ratio AS task_duration_ratio,
               u.task_completion_count AS task_completion_count,
               u.task_duration_updated_at AS task_duration_updated_at
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(result.value[0])

    async def update_user_learning_state(
        self, user_uid: UserUID, properties: dict[str, Any]
    ) -> Result[bool]:
        """Update learning state properties on User node."""
        query = """
        MATCH (u:User {uid: $user_uid})
        SET u += $properties
        RETURN u.uid
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "properties": properties})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(True)

    # ========================================================================
    # HIERARCHY EXTENSIONS (Task-specific)
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[TaskStats]:
        """Count task stats via Cypher COUNT — no entity deserialization."""
        result = await _count_user_stats(
            self,
            user_uid,
            "task",
            {
                "completed": "n.status = 'completed'",
                "overdue": (
                    "n.due_date IS NOT NULL AND date(left(toString(n.due_date), 10)) < date() "
                    "AND n.status <> 'completed'"
                ),
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("TaskStats", result.value))

    async def get_assigned_tasks(
        self,
        user_uid: UserUID,
        include_completed: bool = False,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get tasks assigned to a user via ASSIGNED_TO relationship.

        Args:
            user_uid: Target user UID.
            include_completed: Whether to include completed tasks.
            limit: Maximum results.

        Returns:
            Result containing list of task node properties.
        """
        status_filter = "" if include_completed else "AND t.status <> 'completed'"
        query = f"""
        MATCH (t:Entity)-[:{RelationshipName.ASSIGNED_TO.value}]->(u:User {{uid: $user_uid}})
        WHERE t.uid IS NOT NULL {status_filter}
        RETURN t
        ORDER BY t.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["t"] for record in result.value])

    async def calculate_parent_progress(self, parent_uid: str) -> Result[ParentProgressResult]:
        """Calculate parent task progress based on weighted subtask completion."""
        query = f"""
        MATCH (parent:Entity {{uid: $parent_uid}})
        MATCH (parent)-[r:{RelationshipName.HAS_SUBTASK.value}]->(child:Entity)

        WITH parent,
             count(child) as total_subtasks,
             count(CASE WHEN child.status = 'completed' THEN 1 END) as completed_subtasks,
             sum(r.progress_weight) as total_weight,
             sum(
               CASE WHEN child.status = 'completed'
               THEN r.progress_weight
               ELSE 0
               END
             ) as completed_weight

        RETURN
          total_subtasks,
          completed_subtasks,
          total_weight,
          completed_weight,
          CASE WHEN total_weight > 0
            THEN (completed_weight / total_weight) * 100.0
            ELSE 0.0
          END as progress_percentage
        """

        result = await self.execute_query(query, {"parent_uid": parent_uid})

        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(
                {
                    "total_weight": 0.0,
                    "completed_weight": 0.0,
                    "progress_percentage": 0.0,
                    "total_subtasks": 0,
                    "completed_subtasks": 0,
                }
            )

        record = result.value[0]
        return Result.ok(
            {
                "total_weight": record["total_weight"] or 0.0,
                "completed_weight": record["completed_weight"] or 0.0,
                "progress_percentage": record["progress_percentage"] or 0.0,
                "total_subtasks": record["total_subtasks"],
                "completed_subtasks": record["completed_subtasks"],
            }
        )

    async def get_transitive_dependencies(
        self, task_uid: str, rel_type: RelationshipName, max_depth: int
    ) -> Result[list[str]]:
        """Get transitive dependency UIDs via variable-length path traversal."""
        safe_depth = max(1, min(max_depth, 10))
        query = f"""
        MATCH (root:Entity {{uid: $task_uid}})-[:{rel_type}*1..{safe_depth}]->(dep:Entity)
        WHERE dep.uid <> $task_uid
        RETURN DISTINCT dep.uid AS uid
        """
        result = await self.execute_query(query, {"task_uid": task_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["uid"] for record in result.value])

    async def dependency_path_exists(
        self, from_uid: str, to_uid: str, rel_type: RelationshipName
    ) -> Result[bool]:
        """Report whether a directed ``rel_type`` path exists from ``from_uid`` to ``to_uid``.

        UNBOUNDED reachability — unlike ``get_transitive_dependencies`` (capped at 10
        for the planner), the cycle guard must see arbitrarily-long chains, or it would
        admit a cycle that closes beyond the cap. Variable-length paths never reuse a
        relationship, so this terminates even on an already-cyclic graph; ``EXISTS``
        short-circuits at the first path found.
        """
        query = f"""
        MATCH (start:Entity {{uid: $from_uid}})
        RETURN EXISTS {{
            MATCH (start)-[:{rel_type}*1..]->(:Entity {{uid: $to_uid}})
        }} AS reachable
        """
        result = await self.execute_query(query, {"from_uid": from_uid, "to_uid": to_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(False)
        return Result.ok(bool(result.value[0]["reachable"]))


class EventsBackend(_HierarchyMixin, UniversalNeo4jBackend[Event]):
    """
    Domain backend for Event entities.

    Extends UniversalNeo4jBackend[Event] with:
    - _HierarchyMixin: subevent hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_event(uid)             → get_or_fail() wrapper (NotFound as error)
    - get_user_events(uid)       → alias for inherited list_by_user()
    - get_stats_for_user(uid)    → event count stats (total/scheduled/today)
    - get_goal_links_for_events(…)    → batch map event_uid → contributed goal_uid
    - get_habit_links_for_events(…)   → batch map event_uid → reinforced habit_uid
    - add_attendee/remove_attendee    → (User)-[:ATTENDS]->(Event) pair (ADR-086, staged)
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBEVENT.value,
        inverse_rel=RelationshipName.SUBEVENT_OF.value,
        node_label=NeoLabel.ENTITY,
        domain_name="subevent",
    )

    async def get_event(self, event_id: str) -> Result[Event]:
        """Get event by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(event_id)

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
        """Get all events for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_events_in_range(
        self,
        start_date: str,
        end_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get events within a date range.

        Args:
            start_date: ISO date string (inclusive).
            end_date: ISO date string (inclusive).
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of event node properties.
        """
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (e:Entity)
        WHERE date(left(toString(e.event_date), 10)) >= date($start_date)
          AND date(left(toString(e.event_date), 10)) <= date($end_date)
          {user_clause}
        RETURN e
        ORDER BY e.event_date ASC, e.start_time ASC
        LIMIT $limit
        """
        params: dict[str, object] = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_recurring_events(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get events with a recurrence pattern.

        Args:
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of recurring event node properties.
        """
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (e:Entity)
        WHERE e.recurrence_pattern IS NOT NULL
          {user_clause}
        RETURN e
        ORDER BY e.event_date ASC
        LIMIT $limit
        """
        params: dict[str, object] = {"limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_events_on_date(
        self, event_date: str, user_uid: UserUID, exclude_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get events on a specific date for a user, excluding one event.

        Used for conflict detection.

        Args:
            event_date: ISO date string.
            user_uid: Owner of the events.
            exclude_uid: Event UID to exclude from results.

        Returns:
            Result containing list of event node properties.
        """
        query = """
        MATCH (e:Entity)
        WHERE date(left(toString(e.event_date), 10)) = date($event_date)
          AND e.user_uid = $user_uid
          AND e.uid <> $event_uid
          AND NOT e.status IN ['cancelled']
        RETURN e
        """
        result = await self.execute_query(
            query,
            {
                "event_date": event_date,
                "user_uid": user_uid,
                "event_uid": exclude_uid,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["e"] for record in result.value])

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[EventStats]:
        """Count event stats: total, scheduled, today."""
        from datetime import date

        result = await _count_user_stats(
            self,
            user_uid,
            "event",
            {
                "scheduled": "n.status = 'scheduled'",
                "today": (
                    "n.start_time IS NOT NULL AND substring(toString(n.start_time), 0, 10) = $today"
                ),
            },
            extra_params={"today": date.today().isoformat()},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("EventStats", result.value))

    async def count_recent_reschedules(self, user_uid: UserUID) -> Result[int]:
        """Count events rescheduled in last 30 days."""
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE e.rescheduled_at IS NOT NULL
          AND date(left(toString(e.rescheduled_at), 10)) >= date() - duration('P30D')
        RETURN count(e) as reschedule_count
        """
        result = await self.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        return Result.ok(row.get("reschedule_count", 0) if isinstance(row, dict) else 0)

    async def count_events_in_date_range(
        self, user_uid: UserUID, start_date: str, end_date: str
    ) -> Result[int]:
        """Count events in a date range."""
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE date(left(toString(e.event_date), 10)) >= date($start_date) AND date(left(toString(e.event_date), 10)) <= date($end_date)
        RETURN count(e) as event_count
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "start_date": start_date, "end_date": end_date}
        )
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        return Result.ok(row.get("event_count", 0) if isinstance(row, dict) else 0)

    async def get_goal_celebration_stats(
        self, user_uid: UserUID, start_date: str
    ) -> Result[dict[str, Any]]:
        """Aggregate completed events that celebrate goals since ``start_date``.

        Graph-native: counts events with a ``(Event)-[:CELEBRATES_GOAL]->(Goal)``
        edge rather than reading a property. Returns total completed events, the
        count celebrating ≥1 goal, and the distinct goal uids celebrated.
        """
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event', status: 'completed'})
        WHERE date(left(toString(e.event_date), 10)) >= date($start_date)
        OPTIONAL MATCH (e)-[:CELEBRATES_GOAL]->(g:Goal)
        RETURN count(DISTINCT e) AS total_completed,
               count(DISTINCT CASE WHEN g IS NOT NULL THEN e.uid END) AS milestone_count,
               collect(DISTINCT g.uid) AS goal_uids_raw
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "start_date": start_date})
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        goal_uids = [uid for uid in (row.get("goal_uids_raw") or []) if uid is not None]
        return Result.ok(
            {
                "total_completed": int(row.get("total_completed", 0) or 0),
                "milestone_count": int(row.get("milestone_count", 0) or 0),
                "goal_uids": goal_uids,
            }
        )

    async def get_events_reinforcing_habit(
        self, habit_uid: str, user_uid: UserUID | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Return node props for events linked to a habit via REINFORCES_HABIT.

        Graph-native reverse traversal of ``(Event)-[:REINFORCES_HABIT]->(Habit)``.
        Replaces the former ``find_by(reinforces_habit_uid=...)`` property query.
        """
        user_clause = "WHERE e.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (e:Entity {{entity_type: 'event'}})-[:REINFORCES_HABIT]->(h:Entity {{uid: $habit_uid}})
        {user_clause}
        RETURN e
        """
        params: dict[str, object] = {"habit_uid": habit_uid}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(row["e"]) for row in (result.value or [])])

    async def get_habit_links_for_events(self, event_uids: list[str]) -> Result[dict[str, str]]:
        """Map event_uid → reinforced habit_uid for the given events (batch).

        Reverse-lookup of the REINFORCES_HABIT edge, used to enrich events with
        their derived ``reinforces_habit_uid`` field on fallback (non-rich) paths.
        """
        return await _edge_map_single(
            self, "event", RelationshipName.REINFORCES_HABIT.value, event_uids
        )

    async def get_goal_links_for_events(
        self, event_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        """Map event_uid → list of contributed goal_uids for the given events (batch).

        Batch-lookup of the CONTRIBUTES_TO_GOAL edge, used to enrich events with
        their derived ``contributes_to_goal_uid`` field for scoring. Returns all
        linked goals per event so the enricher can prefer active ones.
        """
        return await _edge_map_multi(
            self, "event", RelationshipName.CONTRIBUTES_TO_GOAL.value, event_uids
        )

    # ------------------------------------------------------------------
    # Attendance (ADR-086) — the dedicated (User)-[:ATTENDS]->(Event) pair.
    # STAGED: no route reaches the service triple that calls these yet.
    # ------------------------------------------------------------------

    async def add_attendee(
        self,
        event_uid: str,
        attendee_uid: UserUID,
        actor_uid: UserUID,
        role: str,
        status: str,
        set_status_on_match: bool = False,
    ) -> Result[str]:
        """Upsert the ``(User)-[:ATTENDS]->(Event)`` edge (idempotent MERGE).

        The GroupBackend.add_member shape applied to attendance (ADR-086):
        ``joined_at``/``added_by``/``role``/``status`` are set ``ON CREATE`` only —
        re-adding never rewrites ``joined_at`` (it records when the edge was first
        created, i.e. the invite or self-add moment). ``set_status_on_match=True``
        additionally transitions an *existing* edge's ``status`` — the target user
        accepting their own attendance (the only actor allowed to transition; the
        service layer enforces the consent state machine before calling this).

        Returns the edge's status after the write.
        """
        on_match_clause = "ON MATCH SET r.status = $status" if set_status_on_match else ""
        query = f"""
        MATCH (u:User {{uid: $attendee_uid}})
        MATCH (e:{self.label} {{uid: $event_uid}})
        MERGE (u)-[r:{RelationshipName.ATTENDS.value}]->(e)
        ON CREATE SET r.joined_at = datetime($now),
                      r.added_by = $actor_uid,
                      r.role = $role,
                      r.status = $status
        {on_match_clause}
        RETURN r.status AS status
        """
        result = await self.execute_query(
            query,
            {
                "attendee_uid": attendee_uid,
                "event_uid": event_uid,
                "actor_uid": actor_uid,
                "role": role,
                "status": status,
                "now": datetime.now().isoformat(),
            },
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(
                Errors.not_found(
                    "attendance",
                    f"User {attendee_uid} or event {event_uid} not found",
                )
            )
        return Result.ok(str(result.value[0]["status"]))

    async def remove_attendee(
        self,
        event_uid: str,
        attendee_uid: UserUID,
        only_if_status: str | None = None,
    ) -> Result[bool]:
        """Delete the ``(User)-[:ATTENDS]->(Event)`` edge.

        With ``only_if_status`` the delete is guarded to edges in that status —
        the organizer's revoke path may only remove a still-``invited`` edge
        (ADR-086); the target's own removal passes ``None`` (any status).

        Returns whether an edge was deleted (``False`` when absent or guarded out).
        """
        status_clause = "WHERE r.status = $only_if_status" if only_if_status else ""
        query = f"""
        MATCH (u:User {{uid: $attendee_uid}})-[r:{RelationshipName.ATTENDS.value}]->(e:{self.label} {{uid: $event_uid}})
        {status_clause}
        DELETE r
        RETURN count(r) AS deleted
        """
        params: dict[str, object] = {"attendee_uid": attendee_uid, "event_uid": event_uid}
        if only_if_status:
            params["only_if_status"] = only_if_status
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        row = result.value[0] if result.value else {}
        deleted = int(row.get("deleted", 0) or 0) if isinstance(row, dict) else 0
        return Result.ok(deleted > 0)


class ChoicesBackend(_HierarchyMixin, UniversalNeo4jBackend[Choice]):
    """
    Domain backend for Choice entities.

    Extends UniversalNeo4jBackend[Choice] with:
    - _HierarchyMixin: subchoice hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_choice(uid)                      → get_or_fail() wrapper (NotFound as error)
    - get_user_choices(uid)                → alias for inherited list_by_user()
    - get_stats_for_user(uid)              → choice count stats (total/pending/decided)
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBCHOICE.value,
        inverse_rel=RelationshipName.SUBCHOICE_OF.value,
        node_label=NeoLabel.ENTITY,
        domain_name="subchoice",
        node_filter=", entity_type: 'choice'",
    )

    async def get_choice(self, choice_id: str) -> Result[Choice]:
        """Get choice by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(choice_id)

    async def get_user_choices(self, user_uid: UserUID) -> Result[list[Choice]]:
        """Get all choices for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[ChoiceStats]:
        """Count choice stats: total, pending, decided."""
        result = await _count_user_stats(
            self,
            user_uid,
            "choice",
            {"pending": "n.status = 'pending'", "decided": "n.status = 'decided'"},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("ChoiceStats", result.value))

    async def get_pending_choices(
        self, user_uid: UserUID, limit: int = 100
    ) -> Result[list[Neo4jProperties]]:
        """Get pending/undecided choices for a user.

        Args:
            user_uid: Owner of the choices.
            limit: Maximum results.

        Returns:
            Result containing list of choice node properties.
        """
        query = """
        MATCH (c:Entity {entity_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND c.status IN ['draft', 'active', 'scheduled']
        RETURN c
        ORDER BY c.decision_deadline ASC, c.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["c"] for record in result.value])

    async def get_choices_needing_decision(
        self, user_uid: UserUID, end_date: str
    ) -> Result[list[Neo4jProperties]]:
        """Get choices that need a decision by a deadline.

        Args:
            user_uid: Owner of the choices.
            end_date: ISO date string — choices with deadline <= this date.

        Returns:
            Result containing list of choice node properties.
        """
        query = """
        MATCH (c:Entity {entity_type: 'choice'})
        WHERE c.user_uid = $user_uid
          AND date(left(toString(c.decision_deadline), 10)) <= date($end_date)
          AND NOT c.status IN ['completed', 'decided', 'cancelled', 'archived']
        RETURN c
        ORDER BY c.decision_deadline ASC
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "end_date": end_date})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["c"] for record in result.value])


class PrinciplesBackend(_HierarchyMixin, UniversalNeo4jBackend[Principle]):
    """
    Domain backend for Principle entities.

    Extends UniversalNeo4jBackend[Principle] with:
    - _HierarchyMixin: subprinciple hierarchy (get children/parent/hierarchy, create/remove, cycle detection)
    - get_principle(uid)                        → get_or_fail() wrapper (NotFound as error)
    - get_user_principles(uid)                  → alias for inherited list_by_user()
    - get_stats_for_user(uid)                   → principle count stats (total/core/active)
    """

    _hierarchy_config = HierarchyConfig(
        forward_rel=RelationshipName.HAS_SUBPRINCIPLE.value,
        inverse_rel=RelationshipName.SUBPRINCIPLE_OF.value,
        node_label=NeoLabel.PRINCIPLE,
        domain_name="subprinciple",
    )

    async def get_principle(self, principle_uid: str) -> Result[Principle]:
        """Get principle by ID. Returns error if not found (contrast with get() → None)."""
        return await self.get_or_fail(principle_uid)

    async def get_user_principles(self, user_uid: UserUID) -> Result[list[Principle]]:
        """Get all principles for a user. Alias for list_by_user."""
        return await self.list_by_user(user_uid)

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[PrincipleStats]:
        """Count principle stats: total, core, active."""
        result = await _count_user_stats(
            self,
            user_uid,
            "principle",
            {"core": "n.strength = 'core'", "active": "n.is_active = true"},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(cast("PrincipleStats", result.value))

    async def get_user_items_in_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        include_completed: bool = False,
    ) -> Result[list[Principle]]:
        """Get principles adopted within a date range.

        Principles use is_active (bool) instead of a status enum, so
        build_user_activity_query — which filters on n.status — does not apply.
        This method is the correct home for that Cypher.

        Args:
            user_uid: Owner of the principles.
            start_date: Lower bound on adopted_date (inclusive).
            end_date: Upper bound on adopted_date (inclusive).
            include_completed: When True, inactive (is_active=False) principles are included.

        Returns:
            Result containing principles adopted in the given range.
        """
        query = """
        MATCH (n:Principle)
        WHERE n.user_uid = $user_uid
          AND date(left(toString(n.adopted_date), 10)) >= date($start_date)
          AND date(left(toString(n.adopted_date), 10)) <= date($end_date)
        """
        if not include_completed:
            query += "  AND n.is_active = true\n"
        query += """
        RETURN n
        ORDER BY n.created_at DESC
        LIMIT $limit
        """
        params: dict[str, object] = {
            "user_uid": user_uid,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": 1000,
        }
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        principles = []
        for record in result.value:
            principle_data = record.get("n")
            if principle_data:
                dto = PrincipleDTO.from_dict(principle_data)
                principles.append(Principle.from_dto(dto))
        return Result.ok(principles)

    async def get_principles_needing_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
        prioritize_never_reviewed: bool = False,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles whose last_review_date is before cutoff.

        Args:
            cutoff_date: ISO date string — principles reviewed before this are included.
            user_uid: Optional user filter.
            limit: Maximum results.
            prioritize_never_reviewed: If True, never-reviewed principles sort first.

        Returns:
            Result containing list of principle node properties.
        """
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        if prioritize_never_reviewed:
            order_clause = """
            ORDER BY
                CASE WHEN p.last_review_date IS NULL THEN 0 ELSE 1 END,
                p.last_review_date ASC
            """
        else:
            order_clause = "ORDER BY p.last_review_date ASC"

        query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(left(toString(p.last_review_date), 10)) < date($cutoff_date))
          {user_clause}
        RETURN p
        {order_clause}
        LIMIT $limit
        """
        params: dict[str, object] = {"cutoff_date": cutoff_date, "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def get_principles_due_for_review(
        self,
        cutoff_date: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles due for review (last_review_date <= cutoff).

        Unlike get_principles_needing_review (strict <), this uses <= for
        "due soon" semantics.

        Args:
            cutoff_date: ISO date string.
            user_uid: Optional user filter.
            limit: Maximum results.

        Returns:
            Result containing list of principle node properties.
        """
        user_clause = "AND p.user_uid = $user_uid" if user_uid else ""
        query = f"""
        MATCH (p:Principle)
        WHERE p.is_active = true
          AND (p.last_review_date IS NULL
               OR date(left(toString(p.last_review_date), 10)) <= date($cutoff_date))
          {user_clause}
        RETURN p
        ORDER BY p.last_review_date ASC
        LIMIT $limit
        """
        params: dict[str, object] = {"cutoff_date": cutoff_date, "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid
        result = await self.execute_query(query, params)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def get_related_principles_by_traversal(
        self, uid: str, depth: int, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get principles related via RELATED_TO traversal up to given depth.

        Args:
            uid: Source principle UID.
            depth: Maximum traversal depth (clamped 1-5).
            limit: Maximum results.

        Returns:
            Result containing list of related principle node properties.
        """
        depth = max(1, min(depth, 5))
        query = f"""
        MATCH (source:Principle {{uid: $uid}})
        OPTIONAL MATCH (source)-[:{RelationshipName.RELATED_TO.value}*1..{depth}]-(related:Principle)
        WHERE related.is_active = true AND related.uid <> $uid
        WITH DISTINCT related
        WHERE related IS NOT NULL
        RETURN related
        ORDER BY related.strength DESC
        LIMIT $limit
        """
        result = await self.execute_query(query, {"uid": uid, "limit": limit})
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["related"] for record in result.value if record.get("related")])

    async def get_principles_by_category(
        self, category: str, exclude_uid: str, limit: int = 10
    ) -> Result[list[Neo4jProperties]]:
        """Get active principles in a category, excluding one UID.

        Args:
            category: Category value string.
            exclude_uid: UID to exclude from results.
            limit: Maximum results.

        Returns:
            Result containing list of principle node properties.
        """
        query = """
        MATCH (p:Principle)
        WHERE p.category = $category
          AND p.uid <> $uid
          AND p.is_active = true
        RETURN p
        ORDER BY p.strength DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query, {"category": category, "uid": exclude_uid, "limit": limit}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["p"] for record in result.value])

    async def get_choice_influence_stats(
        self, principle_uid: str, user_uid: UserUID, period_days: int
    ) -> Result[Neo4jProperties]:
        """Get stats on how a principle has influenced choices."""
        query = f"""
        MATCH (p:Principle {{uid: $principle_uid}})-[:{RelationshipName.GUIDES_CHOICE.value}]->(c:Choice)
        WHERE c.user_uid = $user_uid
          AND datetime(c.created_at) >= datetime() - duration({{days: $period_days}})

        RETURN
            count(c) AS total_choices,
            avg(c.satisfaction_score) AS avg_satisfaction,
            sum(CASE WHEN c.satisfaction_score >= 4 THEN 1 ELSE 0 END) AS positive_outcomes
        """
        result = await self.execute_query(
            query,
            {"principle_uid": principle_uid, "user_uid": user_uid, "period_days": period_days},
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(dict(result.value[0]))
