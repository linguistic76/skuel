"""
Events Scheduling Service - Recurring Event Creation and Optimization
=====================================================================

Handles Event-domain scheduling: creating recurring Event nodes and optimizing
recurrence dates.

Cross-domain scheduling intelligence (conflict detection, slot suggestions,
busy times, calendar density) lives in CalendarOptimizationOrchestrator, which
has access to both Tasks and Events data.
"""

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from core.models.enums import EntityStatus, EntityType, EventType, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID, UserUID
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.uid_generator import UIDGenerator

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations


class EventsSchedulingService(BaseService["EventsOperations", Event]):
    """
    Events-domain scheduling: recurring event creation and date optimization.

    Cross-domain scheduling intelligence (conflict detection, slot suggestions,
    busy times, calendar density) lives in CalendarOptimizationOrchestrator.
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # Configure BaseService
    _date_field = "event_date"

    def __init__(self, backend: "EventsOperations", event_bus=None) -> None:
        """
        Initialize scheduling service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "events.scheduling")
        self.event_bus = event_bus

    # ========================================================================
    # RECURRING EVENT OPTIMIZATION
    # ========================================================================

    @with_error_handling("optimize_recurring_schedule", error_type="database")
    async def optimize_recurring_schedule(
        self,
        user_uid: UserUID,
        pattern: RecurrencePattern,
        preferred_time: time | None = None,
        days_to_schedule: int = 30,
    ) -> Result[list[date]]:
        """
        Generate optimized dates for recurring events.

        Avoids existing busy times and suggests best dates.

        Args:
            user_uid: User identifier
            pattern: Recurrence pattern
            preferred_time: Preferred time of day
            days_to_schedule: How many days to plan ahead

        Returns:
            Result containing list of recommended dates
        """
        today = date.today()
        end_date = today + timedelta(days=days_to_schedule)

        # Get existing events in period
        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=today.isoformat(),
            event_date__lte=end_date.isoformat(),
        )

        # Count events per day
        busy_days: dict[date, int] = {}
        for event in result.value or []:
            if event.event_date:
                busy_days[event.event_date] = busy_days.get(event.event_date, 0) + 1

        # Calculate interval
        interval_days = {
            RecurrencePattern.DAILY: 1,
            RecurrencePattern.WEEKLY: 7,
            RecurrencePattern.BIWEEKLY: 14,
            RecurrencePattern.MONTHLY: 30,
        }.get(pattern, 7)

        # Generate dates, preferring less busy days
        recommended_dates = []
        current = today

        while current <= end_date:
            # Find best date in the interval
            best_date = current
            min_conflicts = busy_days.get(current, 0)

            # Check a few days around the target
            for offset in range(-2, 3):
                check_date = current + timedelta(days=offset)
                if check_date < today or check_date > end_date:
                    continue
                conflicts = busy_days.get(check_date, 0)
                if conflicts < min_conflicts:
                    min_conflicts = conflicts
                    best_date = check_date

            recommended_dates.append(best_date)
            current += timedelta(days=interval_days)

        self.logger.debug(f"Generated {len(recommended_dates)} dates for {pattern.value} pattern")
        return Result.ok(recommended_dates)

    @with_error_handling("create_recurring_events", error_type="database")
    async def create_recurring_events(
        self,
        user_uid: UserUID,
        title: str,
        pattern: RecurrencePattern,
        duration_minutes: int = 60,
        preferred_time: time | None = None,
        days_to_create: int = 30,
        reinforces_habit_uid: str | None = None,
    ) -> Result[list[Event]]:
        """
        Create optimized recurring events.

        Args:
            user_uid: User identifier
            title: Event title
            pattern: Recurrence pattern
            duration_minutes: Duration per event
            preferred_time: Preferred start time
            days_to_create: How many days to create events for
            reinforces_habit_uid: Optional habit to reinforce

        Returns:
            Result containing list of created events
        """
        # Get optimized dates
        dates_result = await self.optimize_recurring_schedule(
            user_uid=user_uid,
            pattern=pattern,
            preferred_time=preferred_time,
            days_to_schedule=days_to_create,
        )
        if dates_result.is_error:
            return Result.fail(dates_result)

        recommended_dates = dates_result.value

        # Set default time if not provided
        start_time = preferred_time or time(9, 0)
        end_time_dt = datetime.combine(date.today(), start_time) + timedelta(
            minutes=duration_minutes
        )
        end_time = end_time_dt.time()

        # Create events
        created_events = []
        for event_date in recommended_dates:
            # Build the frozen Event end-to-end (ADR-035/ADR-065).
            event_model = Event(
                uid=EntityUID(UIDGenerator.generate_random_uid("event")),
                entity_type=EntityType.EVENT,
                user_uid=user_uid,
                title=title,
                event_date=event_date,
                start_time=start_time,
                end_time=end_time,
                event_type=EventType.PERSONAL,
                recurrence_pattern=pattern,
                status=EntityStatus.DRAFT,
            )

            create_result = await self.backend.create(event_model)
            if create_result.is_ok:
                event = self._to_domain_model(create_result.value, EventDTO, Event)
                created_events.append(event)
                # Habit reinforcement is a graph edge, not a property.
                if reinforces_habit_uid:
                    await self.backend.create_relationship(
                        event.uid,
                        reinforces_habit_uid,
                        RelationshipName.REINFORCES_HABIT,
                    )

        self.logger.info(f"Created {len(created_events)} recurring events")

        return Result.ok(created_events)
