"""
Report Schedule Service
========================

CRUD and scheduling logic for ReportSchedule entities.
Manages recurring progress report generation schedules.
"""

from datetime import datetime, timedelta
from typing import Any

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.report.report_schedule import (
    ReportSchedule,
    ReportScheduleDTO,
    ScheduleType,
    schedule_dto_to_pure,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.reports.schedule")


class ReportScheduleService:
    """
    CRUD and scheduling logic for report generation schedules.

    Uses UniversalNeo4jBackend[ReportSchedule] for persistence.
    """

    def __init__(
        self,
        backend: UniversalNeo4jBackend[ReportSchedule],
    ) -> None:
        self.backend = backend

    async def create_schedule(
        self,
        user_uid: str,
        schedule_type: str = "weekly",
        day_of_week: int = 0,
        domains: list[str] | None = None,
        depth: str = "standard",
    ) -> Result[ReportSchedule]:
        """
        Create a report generation schedule.

        Args:
            user_uid: User who owns this schedule
            schedule_type: weekly, biweekly, or monthly
            day_of_week: 0=Monday through 6=Sunday
            domains: Domains to include (empty = all)
            depth: summary, standard, or detailed

        Returns:
            Result containing the created ReportSchedule
        """
        uid = UIDGenerator.generate_uid("schedule")
        stype = ScheduleType(schedule_type)
        next_due = self.compute_next_due_at(stype, day_of_week)

        schedule = ReportSchedule(
            uid=uid,
            user_uid=user_uid,
            schedule_type=stype,
            day_of_week=day_of_week,
            domains=domains or [],
            depth=depth,
            is_active=True,
            next_due_at=next_due,
        )

        result = await self.backend.create(schedule)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Create HAS_SCHEDULE relationship
        try:
            await self.backend.driver.execute_query(
                """
                MATCH (u:User {uid: $user_uid})
                MATCH (s:ReportSchedule {uid: $schedule_uid})
                MERGE (u)-[:HAS_SCHEDULE]->(s)
                """,
                user_uid=user_uid,
                schedule_uid=uid,
            )
        except Exception as e:
            logger.warning(f"Failed to create HAS_SCHEDULE relationship: {e}")

        logger.info(f"Created report schedule {uid} for {user_uid}: {schedule_type}")
        return Result.ok(schedule)

    async def get_user_schedule(self, user_uid: str) -> Result[ReportSchedule | None]:
        """Get the user's active report schedule (one per user)."""
        result = await self.backend.find_by(user_uid=user_uid, is_active=True)
        if result.is_error:
            return Result.fail(result.expect_error())

        schedules = result.value or []
        if not schedules:
            return Result.ok(None)

        return Result.ok(schedules[0])

    async def update_schedule(self, uid: str, updates: dict[str, Any]) -> Result[ReportSchedule]:
        """Update a schedule's configuration."""
        updates["updated_at"] = datetime.now()
        result = await self.backend.update(uid, updates)
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found("resource", f"Schedule {uid} not found"))

        return Result.ok(result.value)

    async def deactivate_schedule(self, uid: str) -> Result[bool]:
        """Deactivate a schedule (soft delete)."""
        result = await self.backend.update(uid, {"is_active": False, "updated_at": datetime.now()})
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(True)

    async def get_due_schedules(self) -> Result[list[ReportSchedule]]:
        """Get all active schedules that are due for generation."""
        try:
            records, _, _ = await self.backend.driver.execute_query(
                """
                MATCH (s:ReportSchedule)
                WHERE s.is_active = true
                  AND s.next_due_at <= datetime()
                RETURN s
                ORDER BY s.next_due_at ASC
                """,
            )
            schedules = []
            for record in records:
                node = record["s"]
                dto = ReportScheduleDTO(
                    uid=node["uid"],
                    user_uid=node.get("user_uid", ""),
                    schedule_type=node.get("schedule_type", "weekly"),
                    day_of_week=node.get("day_of_week", 0),
                    domains=node.get("domains"),
                    depth=node.get("depth", "standard"),
                    is_active=node.get("is_active", True),
                    last_generated_at=node.get("last_generated_at"),
                    next_due_at=node.get("next_due_at"),
                    created_at=node.get("created_at"),
                    updated_at=node.get("updated_at"),
                )
                schedules.append(schedule_dto_to_pure(dto))
            return Result.ok(schedules)
        except Exception as e:
            logger.error(f"Failed to query due schedules: {e}")
            return Result.fail(Errors.database(str(e)))

    async def mark_generated(self, uid: str) -> Result[ReportSchedule]:
        """
        Mark a schedule as generated: update last_generated_at and compute next_due_at.
        """
        # Get current schedule to compute next due
        get_result = await self.backend.get(uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        schedule = get_result.value
        if not schedule:
            return Result.fail(Errors.not_found("resource", f"Schedule {uid} not found"))

        now = datetime.now()
        next_due = self.compute_next_due_at(schedule.schedule_type, schedule.day_of_week)

        return await self.update_schedule(
            uid,
            {
                "last_generated_at": now,
                "next_due_at": next_due,
            },
        )

    @staticmethod
    def compute_next_due_at(schedule_type: ScheduleType, day_of_week: int) -> datetime:
        """
        Compute the next due datetime based on schedule type and day of week.

        Args:
            schedule_type: weekly, biweekly, or monthly
            day_of_week: 0=Monday through 6=Sunday

        Returns:
            Next due datetime
        """
        now = datetime.now()
        current_weekday = now.weekday()

        if schedule_type == ScheduleType.WEEKLY:
            days_ahead = day_of_week - current_weekday
            if days_ahead <= 0:
                days_ahead += 7
            return now + timedelta(days=days_ahead)

        if schedule_type == ScheduleType.BIWEEKLY:
            days_ahead = day_of_week - current_weekday
            if days_ahead <= 0:
                days_ahead += 14
            return now + timedelta(days=days_ahead)

        # Monthly: next occurrence of the day_of_week in the following month
        # Simplified: add ~30 days then find the next matching weekday
        target = now + timedelta(days=28)
        while target.weekday() != day_of_week:
            target += timedelta(days=1)
        return target
