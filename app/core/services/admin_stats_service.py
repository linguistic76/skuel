"""
Admin Stats Service
====================

System-wide statistics for the admin dashboard.

Encapsulates cross-domain aggregation queries that were previously executed
as raw Cypher in the admin dashboard UI routes. These queries span multiple
entity types and relationship types — they don't belong to any single domain
service.

Methods:
- get_entity_system_metrics   — System-wide learning metrics (totals, interaction counts)
- get_all_users_progress      — Per-user learning progress summary
- get_user_ku_detail          — Detailed KU progress for a specific user
- get_user_detail_stats       — Cross-domain activity stats for a specific user
- get_users_with_activity_counts — Users list with entity counts (for admin table)
"""

from typing import TYPE_CHECKING, Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger("skuel.services.admin_stats")


class AdminStatsService:
    """Cross-domain admin statistics backed by aggregation Cypher queries.

    Injected with a QueryExecutor (not a typed backend) because these queries
    span User, Task, Goal, Habit, Event, Choice, Principle, Entity, Session,
    and AuthEvent nodes — no single domain backend covers them all.
    """

    def __init__(self, query_executor: "QueryExecutor") -> None:
        self.query_executor = query_executor
        self.logger = logger

    async def get_entity_system_metrics(self) -> Result[dict[str, int]]:
        """Get system-wide learning metrics: entity totals and interaction counts."""
        result = await self.query_executor.execute_query(
            """
            OPTIONAL MATCH (ku:Entity)
            WITH count(DISTINCT ku) AS total_kus
            OPTIONAL MATCH (:User)-[v:VIEWED]->(:Entity)
            WITH total_kus, count(v) AS total_viewed
            OPTIONAL MATCH (:User)-[:IN_PROGRESS]->(:Entity)
            WITH total_kus, total_viewed, count(*) AS total_in_progress
            OPTIONAL MATCH (:User)-[:MASTERED]->(:Entity)
            WITH total_kus, total_viewed, total_in_progress, count(*) AS total_mastered
            OPTIONAL MATCH (:User)-[:BOOKMARKED]->(:Entity)
            WITH total_kus, total_viewed, total_in_progress, total_mastered,
                 count(*) AS total_bookmarked
            OPTIONAL MATCH (u:User)
                WHERE EXISTS { (u)-[:VIEWED|IN_PROGRESS|MASTERED|BOOKMARKED]->(:Entity) }
            RETURN total_kus, total_viewed, total_in_progress, total_mastered,
                   total_bookmarked, count(DISTINCT u) AS users_with_progress
            """
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        defaults: dict[str, int] = {
            "total_kus": 0,
            "total_viewed": 0,
            "total_in_progress": 0,
            "total_mastered": 0,
            "total_bookmarked": 0,
            "users_with_progress": 0,
        }

        records = result.value or []
        if records:
            r = records[0]
            for key in defaults:
                defaults[key] = r[key] or 0

        return Result.ok(defaults)

    async def get_all_users_progress(self) -> Result[list[dict[str, Any]]]:
        """Get per-user KU progress summary (for admin learning dashboard table)."""
        result = await self.query_executor.execute_query(
            """
            MATCH (u:User)
            WHERE u.uid <> 'user_system'
            OPTIONAL MATCH (u)-[:VIEWED]->(ku1:Entity)
            WITH u, count(DISTINCT ku1) AS viewed_count
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(ku2:Entity)
            WITH u, viewed_count, count(DISTINCT ku2) AS in_progress_count
            OPTIONAL MATCH (u)-[:MASTERED]->(ku3:Entity)
            WITH u, viewed_count, in_progress_count, count(DISTINCT ku3) AS mastered_count
            OPTIONAL MATCH (u)-[:BOOKMARKED]->(ku4:Entity)
            WITH u, viewed_count, in_progress_count, mastered_count,
                 count(DISTINCT ku4) AS bookmarked_count
            RETURN u.uid AS uid,
                   u.display_name AS display_name,
                   u.title AS username,
                   u.role AS role,
                   viewed_count,
                   in_progress_count,
                   mastered_count,
                   bookmarked_count,
                   (viewed_count + in_progress_count + mastered_count) AS total_interactions
            ORDER BY total_interactions DESC
            """
        )

        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok([dict(r) for r in (result.value or [])])

    async def get_user_ku_detail(self, user_uid: str) -> Result[dict[str, Any]]:
        """Get detailed KU progress (viewed/in-progress/mastered/bookmarked) for one user."""
        result = await self.query_executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[v:VIEWED]->(vku:Entity)
            WITH u, collect(DISTINCT {
                uid: vku.uid, title: vku.title,
                view_count: v.view_count,
                first_viewed_at: toString(v.first_viewed_at),
                last_viewed_at: toString(v.last_viewed_at)
            }) AS viewed_kus

            OPTIONAL MATCH (u)-[p:IN_PROGRESS]->(pku:Entity)
            WITH u, viewed_kus, collect(DISTINCT {
                uid: pku.uid, title: pku.title,
                started_at: toString(p.started_at),
                progress_score: p.progress_score
            }) AS progress_kus

            OPTIONAL MATCH (u)-[m:MASTERED]->(mku:Entity)
            WITH u, viewed_kus, progress_kus, collect(DISTINCT {
                uid: mku.uid, title: mku.title,
                mastered_at: toString(m.mastered_at),
                mastery_score: m.mastery_score,
                method: m.method
            }) AS mastered_kus

            OPTIONAL MATCH (u)-[b:BOOKMARKED]->(bku:Entity)
            WITH viewed_kus, progress_kus, mastered_kus, collect(DISTINCT {
                uid: bku.uid, title: bku.title,
                bookmarked_at: toString(b.bookmarked_at)
            }) AS bookmarked_kus

            RETURN viewed_kus, progress_kus, mastered_kus, bookmarked_kus
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        detail: dict[str, Any] = {
            "viewed": [],
            "in_progress": [],
            "mastered": [],
            "bookmarked": [],
            "summary": {
                "viewed_count": 0,
                "in_progress_count": 0,
                "mastered_count": 0,
                "bookmarked_count": 0,
            },
        }

        records = result.value or []
        if records:
            r = records[0]
            # Filter out entries with null uid (from OPTIONAL MATCH with no results)
            viewed = [ku for ku in r["viewed_kus"] if ku.get("uid")]
            in_progress = [ku for ku in r["progress_kus"] if ku.get("uid")]
            mastered = [ku for ku in r["mastered_kus"] if ku.get("uid")]
            bookmarked = [ku for ku in r["bookmarked_kus"] if ku.get("uid")]

            detail["viewed"] = viewed
            detail["in_progress"] = in_progress
            detail["mastered"] = mastered
            detail["bookmarked"] = bookmarked
            detail["summary"]["viewed_count"] = len(viewed)
            detail["summary"]["in_progress_count"] = len(in_progress)
            detail["summary"]["mastered_count"] = len(mastered)
            detail["summary"]["bookmarked_count"] = len(bookmarked)

        return Result.ok(detail)

    async def get_user_detail_stats(self, user_uid: str) -> Result[dict[str, int]]:
        """Get cross-domain activity stats for a specific user.

        Covers all 6 activity domains + knowledge interactions + sessions/logins.
        """
        result = await self.query_executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS tasks_total
            OPTIONAL MATCH (u)-[:OWNS]->(tc:Task)
                WHERE tc.status IN ['completed', 'done']
            WITH u, tasks_total, count(DISTINCT tc) AS tasks_completed

            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            WITH u, tasks_total, tasks_completed, count(DISTINCT g) AS goals_total
            OPTIONAL MATCH (u)-[:OWNS]->(ga:Goal)
                WHERE ga.status IN ['active', 'in_progress']
            With u, tasks_total, tasks_completed, goals_total,
                 count(DISTINCT ga) AS goals_active

            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 count(DISTINCT h) AS habits_total
            OPTIONAL MATCH (u)-[:OWNS]->(ha:Habit)
                WHERE ha.status IN ['active', 'in_progress']
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, count(DISTINCT ha) AS habits_active

            OPTIONAL MATCH (u)-[:OWNS]->(e:Event)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, count(DISTINCT e) AS events_total

            OPTIONAL MATCH (u)-[:OWNS]->(c:Choice)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total,
                 count(DISTINCT c) AS choices_total

            OPTIONAL MATCH (u)-[:OWNS]->(p:Principle)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 count(DISTINCT p) AS principles_total

            OPTIONAL MATCH (u)-[:VIEWED]->(kv:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, count(DISTINCT kv) AS ku_viewed
            OPTIONAL MATCH (u)-[:IN_PROGRESS]->(kp:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed,
                 count(DISTINCT kp) AS ku_in_progress
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Entity)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress,
                 count(DISTINCT km) AS ku_mastered

            OPTIONAL MATCH (u)-[:HAS_SESSION]->(s:Session)
            WITH u, tasks_total, tasks_completed, goals_total, goals_active,
                 habits_total, habits_active, events_total, choices_total,
                 principles_total, ku_viewed, ku_in_progress, ku_mastered,
                 count(DISTINCT s) AS session_count
            OPTIONAL MATCH (u)-[:HAD_AUTH_EVENT]->(ae:AuthEvent)
                WHERE ae.event_type = 'LOGIN_SUCCESS'
            RETURN tasks_total, tasks_completed, goals_total, goals_active,
                   habits_total, habits_active, events_total, choices_total,
                   principles_total, ku_viewed, ku_in_progress, ku_mastered,
                   session_count, count(DISTINCT ae) AS login_count
            """,
            {"user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        defaults: dict[str, int] = {
            "tasks_total": 0,
            "tasks_completed": 0,
            "goals_total": 0,
            "goals_active": 0,
            "habits_total": 0,
            "habits_active": 0,
            "events_total": 0,
            "choices_total": 0,
            "principles_total": 0,
            "ku_viewed": 0,
            "ku_in_progress": 0,
            "ku_mastered": 0,
            "session_count": 0,
            "login_count": 0,
        }

        records = result.value or []
        if records:
            r = records[0]
            for key in defaults:
                defaults[key] = r[key] or 0

        return Result.ok(defaults)

    async def get_users_with_activity_counts(
        self,
        role_filter: str | None = None,
        active_only: bool = True,
    ) -> Result[list[dict[str, Any]]]:
        """Get all users with entity counts for the admin users table.

        Returns user info plus task/goal/habit/KU mastered counts.
        Uses parameterized WHERE clauses (no string interpolation).
        """
        # Build parameterized WHERE conditions
        where_clauses = ["u.uid <> 'user_system'"]
        params: dict[str, Any] = {}

        if role_filter:
            where_clauses.append("u.role = $role_filter")
            params["role_filter"] = role_filter
        if active_only:
            where_clauses.append("u.is_active = true")

        where_str = " AND ".join(where_clauses)

        result = await self.query_executor.execute_query(
            f"""
            MATCH (u:User)
            WHERE {where_str}

            OPTIONAL MATCH (u)-[:OWNS]->(t:Task)
            WITH u, count(DISTINCT t) AS task_count
            OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
            With u, task_count, count(DISTINCT g) AS goal_count
            OPTIONAL MATCH (u)-[:OWNS]->(h:Habit)
            WITH u, task_count, goal_count, count(DISTINCT h) AS habit_count
            OPTIONAL MATCH (u)-[:MASTERED]->(km:Entity)
            WITH u, task_count, goal_count, habit_count,
                 count(DISTINCT km) AS ku_mastered

            RETURN u.uid AS uid,
                   u.title AS username,
                   u.display_name AS display_name,
                   u.email AS email,
                   u.role AS role,
                   u.is_active AS is_active,
                   u.updated_at AS last_login_at,
                   task_count, goal_count, habit_count, ku_mastered
            ORDER BY u.title
            """,
            params,
        )

        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok([dict(r) for r in (result.value or [])])
