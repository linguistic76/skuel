"""
Progress Report Background Worker
===================================

Periodically checks for due report schedules and generates progress reports.

Architecture:
- Timer-based: asyncio.sleep loop (hourly check interval)
- Error isolation: One schedule failure doesn't block others
- Graceful degradation: Worker skips cycle on errors

See: EmbeddingBackgroundWorker for pattern reference
"""

import asyncio
from typing import Any

from core.utils.logging import get_logger

logger = get_logger("skuel.background.progress_reports")


class ProgressReportWorker:
    """
    Background worker that checks for due report schedules and generates progress reports.

    Runs on a configurable interval (default: 3600s / hourly).
    Each cycle queries active schedules where next_due_at <= now(),
    generates reports, and advances the schedule.
    """

    def __init__(
        self,
        schedule_service: Any,  # ReportScheduleService
        progress_generator: Any,  # ProgressReportGenerator
        check_interval_seconds: int = 3600,
    ) -> None:
        self.schedule_service = schedule_service
        self.progress_generator = progress_generator
        self.check_interval = check_interval_seconds
        self._cycles_run = 0
        self._reports_generated = 0
        self._errors = 0

    async def start(self) -> None:
        """Start the background processing loop."""
        logger.info(f"Progress report worker started (check_interval={self.check_interval}s)")
        await self._process_loop()

    async def _process_loop(self) -> None:
        """Check for due schedules on each cycle."""
        while True:
            await asyncio.sleep(self.check_interval)
            self._cycles_run += 1

            try:
                await self._process_due_schedules()
            except Exception as e:
                logger.error(f"Progress report worker cycle failed: {e}")
                self._errors += 1

    async def _process_due_schedules(self) -> None:
        """Query due schedules and generate reports for each."""
        result = await self.schedule_service.get_due_schedules()
        if result.is_error:
            logger.warning(f"Failed to query due schedules: {result.expect_error()}")
            return

        schedules = result.value or []
        if not schedules:
            return

        logger.info(f"Found {len(schedules)} due schedule(s)")

        for schedule in schedules:
            try:
                gen_result = await self.progress_generator.generate(
                    user_uid=schedule.user_uid,
                    time_period=self._schedule_type_to_period(schedule.schedule_type),
                    domains=schedule.domains if schedule.domains else None,
                    depth=schedule.depth,
                )

                if gen_result.is_error:
                    logger.warning(
                        f"Failed to generate report for schedule {schedule.uid}: "
                        f"{gen_result.expect_error()}"
                    )
                    self._errors += 1
                    continue

                # Mark schedule as generated (advances next_due_at)
                mark_result = await self.schedule_service.mark_generated(schedule.uid)
                if mark_result.is_error:
                    logger.warning(
                        f"Failed to mark schedule {schedule.uid} as generated: "
                        f"{mark_result.expect_error()}"
                    )

                self._reports_generated += 1
                logger.info(
                    f"Generated progress report for {schedule.user_uid} (schedule: {schedule.uid})"
                )

            except Exception as e:
                logger.error(f"Error processing schedule {schedule.uid}: {e}")
                self._errors += 1

    @staticmethod
    def _schedule_type_to_period(schedule_type: Any) -> str:
        """Map schedule type to time period string."""
        from core.models.enums.reports_enums import ScheduleType

        mapping = {
            ScheduleType.WEEKLY: "7d",
            ScheduleType.BIWEEKLY: "14d",
            ScheduleType.MONTHLY: "30d",
        }
        return mapping.get(schedule_type, "7d")

    def get_metrics(self) -> dict[str, int]:
        """Get worker performance metrics."""
        return {
            "cycles_run": self._cycles_run,
            "reports_generated": self._reports_generated,
            "errors": self._errors,
        }
