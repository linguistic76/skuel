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
- get_growth                  — Accounts by sign-up month, trailing twelve months
- get_retention               — Presence by month and who came back the month after
- get_search_gaps             — Zero/low-result search queue (content authoring)
- get_search_event_total      — Running :SearchEvent count (Phase-2 trigger)
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID
from core.ports.query_types import (
    ActivityTotals,
    GrowthMonth,
    GrowthReport,
    RetentionMonth,
    RetentionReport,
    RoleCounts,
)
from core.utils.logging import get_logger
from core.utils.month_keys import month_key, shift_month, trailing_months
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.cross_domain_protocols import CrossDomainBackendOperations
    from core.ports.query_types import AccountMonthRow, PresenceMonthRow, SearchGapRow
    from core.ports.search_protocols import SearchEventBackendOperations

logger = get_logger("skuel.services.admin_stats")

#: How many months the growth and retention tables show, the current one included.
ANALYTICS_MONTHS = 12


def build_growth_report(rows: list[AccountMonthRow], current_month: str) -> GrowthReport:
    """The growth table for the months ending at ``current_month``.

    Every month of the window has a line, a month with no new account
    included. A month's total counts every account created up to its end:
    those from before the window, and those with no creation stamp, are in it
    from the first line.
    """
    months = trailing_months(current_month, ANALYTICS_MONTHS)
    new_by_month = {row.month: row.new_accounts for row in rows if row.month is not None}
    running = sum(row.new_accounts for row in rows if row.month is None or row.month < months[0])
    lines: list[GrowthMonth] = []
    for month in months:
        new_accounts = new_by_month.get(month, 0)
        running += new_accounts
        lines.append(
            GrowthMonth(
                month=month,
                new_accounts=new_accounts,
                change=new_accounts - new_by_month.get(shift_month(month, -1), 0),
                total=running,
            )
        )
    return GrowthReport(
        total_accounts=sum(row.new_accounts for row in rows),
        deactivated_accounts=sum(row.deactivated for row in rows),
        months=tuple(lines),
    )


def build_retention_report(rows: list[PresenceMonthRow], current_month: str) -> RetentionReport:
    """The retention table for the months ending at ``current_month``.

    Every month of the window has a line, a month no one was present in
    included. The current month has no month after it yet, so no one has
    returned from it; the month before it is measured against a month still in
    progress.
    """
    by_month = {row.month: row for row in rows}
    lines: list[RetentionMonth] = []
    for month in trailing_months(current_month, ANALYTICS_MONTHS):
        row = by_month.get(month)
        present = row.present if row else 0
        returned: int | None = None
        if month != current_month:
            returned = row.returned if row else 0
        lines.append(
            RetentionMonth(
                month=month,
                present=present,
                returned=returned,
                next_month_in_progress=shift_month(month, 1) == current_month,
            )
        )
    return RetentionReport(months=tuple(lines))


class AdminStatsService:
    """Cross-domain admin statistics backed by typed backend methods.

    Uses the CrossDomainBackend (shared with CrossDomainAnalyticsService,
    CrossDomainQueryService, and GraphIntelligenceService) because these queries
    span User, Task, Goal, Habit, Event, Choice, Principle, Entity, Session,
    and AuthEvent nodes — no single domain backend covers them all.
    """

    def __init__(
        self,
        backend: CrossDomainBackendOperations,
        search_event_backend: SearchEventBackendOperations | None = None,
    ) -> None:
        self.backend = backend
        self.search_event_backend = search_event_backend
        self.logger = logger

    async def get_entity_system_metrics(self) -> Result[dict[str, int]]:
        """Get system-wide learning metrics: entity totals and interaction counts."""
        result = await self.backend.get_entity_system_metrics()

        if result.is_error:
            return Result.fail(result)

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
        result = await self.backend.get_all_users_progress()

        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(r) for r in (result.value or [])])

    async def get_user_ku_detail(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """Get detailed KU progress (viewed/in-progress/mastered/bookmarked) for one user."""
        result = await self.backend.get_user_ku_detail(user_uid)

        if result.is_error:
            return Result.fail(result)

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

    async def get_user_submissions_detail(self, user_uid: UserUID) -> Result[list[dict[str, Any]]]:
        """Get exercise submissions owned by a user, with linked exercise and report count."""
        result = await self.backend.get_user_submissions_detail(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(r) for r in (result.value or [])])

    async def get_user_detail_stats(self, user_uid: UserUID) -> Result[dict[str, int]]:
        """Get cross-domain activity stats for a specific user.

        Covers all 6 activity domains + knowledge interactions + sessions/logins.
        """
        result = await self.backend.get_user_detail_stats(user_uid)

        if result.is_error:
            return Result.fail(result)

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

    async def get_activity_entity_counts(self) -> Result[ActivityTotals]:
        """Every task, habit and goal on the graph, counted: any status, any age."""
        result = await self.backend.get_activity_entity_counts()

        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        row = records[0] if records else {}
        return Result.ok(
            ActivityTotals(
                tasks=int(row.get("tasks") or 0),
                habits=int(row.get("habits") or 0),
                goals=int(row.get("goals") or 0),
            )
        )

    async def get_growth(self) -> Result[GrowthReport]:
        """New accounts per month for the trailing twelve months, with the running total.

        Months are UTC. A deactivated account stays counted in the month it
        signed up in; an erased one is counted nowhere.

        Backend: CrossDomainBackend.get_accounts_by_signup_month
        """
        result = await self.backend.get_accounts_by_signup_month()
        if result.is_error:
            return Result.fail(result)
        return Result.ok(build_growth_report(result.value or [], month_key(datetime.now(UTC))))

    async def get_retention(self) -> Result[RetentionReport]:
        """Who was present each month, and who of them was present the month after.

        A user is present in a UTC month when they signed in during it or a
        live session of theirs was seen in it.

        Backend: CrossDomainBackend.get_presence_by_month
        """
        current = month_key(datetime.now(UTC))
        months = trailing_months(current, ANALYTICS_MONTHS)
        result = await self.backend.get_presence_by_month(
            months, {month: shift_month(month, 1) for month in months}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(build_retention_report(result.value or [], current))

    async def get_user_role_counts(self) -> Result[RoleCounts]:
        """User counts grouped by role.

        Single Cypher GROUP BY query — replaces fetching all users just to count roles.
        """
        result = await self.backend.get_user_role_counts()

        if result.is_error:
            return Result.fail(result)

        stats: RoleCounts = {
            "total": 0,
            "admins": 0,
            "teachers": 0,
            "members": 0,
            "registered": 0,
        }

        records = result.value or []
        for r in records:
            parsed_role = UserRole.from_string(r["role"])
            count = r["cnt"] or 0
            stats["total"] += count
            if parsed_role == UserRole.ADMIN:
                stats["admins"] += count
            elif parsed_role == UserRole.TEACHER:
                stats["teachers"] += count
            elif parsed_role == UserRole.MEMBER:
                stats["members"] += count
            elif parsed_role == UserRole.REGISTERED:
                stats["registered"] += count

        return Result.ok(stats)

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
        where_clauses: list[str] = []
        params: dict[str, Any] = {}

        if role_filter:
            where_clauses.append("u.role = $role_filter")
            params["role_filter"] = role_filter
        if active_only:
            where_clauses.append("u.is_active = true")

        where_str = " AND ".join(where_clauses) or "true"

        result = await self.backend.get_users_with_activity_counts(where_str, params)

        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(r) for r in (result.value or [])])

    async def get_search_gaps(
        self,
        *,
        max_result_count: int = 2,
        days: int = 90,
        limit: int = 50,
    ) -> Result[list[SearchGapRow]]:
        """Zero/low-result searches grouped by normalized query — the content authoring queue.

        Empty list when no search-event backend is wired (nothing logged, nothing to show).

        Backend: SearchEventBackend.get_search_gaps
        """
        if self.search_event_backend is None:
            self.logger.info("Search-event backend not wired — returning empty search-gap queue")
            return Result.ok([])
        return await self.search_event_backend.get_search_gaps(
            max_result_count=max_result_count, days=days, limit=limit
        )

    async def get_search_event_total(self) -> Result[int]:
        """Running :SearchEvent total — tracked against the 1,000+ Phase-2 analytics trigger.

        Backend: SearchEventBackend.count_search_events
        """
        if self.search_event_backend is None:
            self.logger.info("Search-event backend not wired — search event total is 0")
            return Result.ok(0)
        return await self.search_event_backend.count_search_events()
