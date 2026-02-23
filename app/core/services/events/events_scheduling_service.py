"""
Events Scheduling Service - Smart Scheduling and Calendar Management
=====================================================================

Handles event scheduling, conflict detection, and learning path integration.

**Responsibilities:**
- Smart scheduling with calendar awareness
- Conflict detection and resolution suggestions
- Learning-aligned event scheduling
- Recurring event optimization
- Time slot recommendations

**Pattern:**
Similar to TasksSchedulingService but focused on calendar-based scheduling.
Events are temporal entities, so scheduling focuses on time slots and conflicts
rather than prerequisites and dependencies.
"""

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_tuple_first

if TYPE_CHECKING:
    from core.models.event.event_request import EventCreateRequest
    from core.ports import BackendOperations


class EventsSchedulingService(BaseService["BackendOperations[Event]", Event]):
    """
    Smart event scheduling and calendar management.

    Handles:
    - Calendar-aware scheduling (avoid conflicts)
    - Optimal time slot suggestions
    - Recurring event patterns
    - Conflict detection

    Source Tag: "events_scheduling_service_explicit"

    SKUEL Architecture:
    - Uses CypherGenerator for graph queries
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Ku",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

    # Configure BaseService
    _date_field = "event_date"

    def __init__(self, backend: "BackendOperations[Event]", event_bus=None) -> None:
        """
        Initialize scheduling service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)
        """
        super().__init__(backend, "events.scheduling")
        self.event_bus = event_bus

    @property
    def entity_label(self) -> str:
        """Return the graph label for Ku entities."""
        return "Ku"

    # ========================================================================
    # CONFLICT DETECTION
    # ========================================================================

    async def _detect_conflicts(
        self,
        user_uid: str,
        event_date: date,
        start_time: time | None,
        end_time: time | None,
        exclude_uid: str | None = None,
    ) -> list[Event]:
        """
        Detect conflicting events on the same date/time.

        Args:
            user_uid: User identifier
            event_date: Date to check
            start_time: Start time (optional)
            end_time: End time (optional)
            exclude_uid: Event UID to exclude from conflict check

        Returns:
            List of conflicting events
        """
        # Get events on same date
        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date=event_date.isoformat(),
        )
        if result.is_error or not result.value:
            return []

        conflicts = []
        for event in result.value:
            if exclude_uid and event.uid == exclude_uid:
                continue
            if event.status == EntityStatus.CANCELLED.value:
                continue

            # If no times specified, any same-day event is a potential conflict
            if not start_time or not end_time:
                conflicts.append(event)
                continue

            # Check time overlap
            if event.start_time and event.end_time:
                if start_time < event.end_time and end_time > event.start_time:
                    conflicts.append(event)

        return conflicts

    @with_error_handling("check_conflicts", error_type="database")
    async def check_conflicts(
        self,
        user_uid: str,
        event_date: date,
        start_time: time | None = None,
        end_time: time | None = None,
        exclude_uid: str | None = None,
    ) -> Result[list[Event]]:
        """
        Check for conflicting events.

        Args:
            user_uid: User identifier
            event_date: Date to check
            start_time: Start time (optional)
            end_time: End time (optional)
            exclude_uid: Event UID to exclude

        Returns:
            Result containing list of conflicting events
        """
        conflicts = await self._detect_conflicts(
            user_uid=user_uid,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            exclude_uid=exclude_uid,
        )

        self.logger.debug(f"Found {len(conflicts)} conflicts on {event_date}")
        return Result.ok(conflicts)

    # ========================================================================
    # SMART SCHEDULING
    # ========================================================================

    @with_error_handling("schedule_event_smart", error_type="database")
    async def schedule_event_smart(
        self,
        event_data: "EventCreateRequest",
        user_context: UserContext,
        avoid_conflicts: bool = True,
    ) -> Result[Event]:
        """
        Schedule an event with smart conflict avoidance.

        This method:
        1. Checks for conflicts on the proposed date/time
        2. Returns error if conflicts found and avoid_conflicts=True
        3. Creates the event if no conflicts

        Args:
            event_data: Event creation request
            user_context: User context
            avoid_conflicts: If True, fail on conflict; if False, warn only

        Returns:
            Result containing created event or conflict error
        """
        # Check for conflicts
        conflicts = await self._detect_conflicts(
            user_uid=user_context.user_uid,
            event_date=event_data.event_date,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
        )

        if conflicts and avoid_conflicts:
            conflict_titles = [e.title for e in conflicts[:3]]
            return Result.fail(
                Errors.validation(
                    message=f"Time conflict with: {', '.join(conflict_titles)}",
                    field="event_date",
                    value=event_data.event_date.isoformat(),
                )
            )

        # Create DTO from request
        dto = EventDTO.create_event(
            user_uid=user_context.user_uid,
            title=event_data.title,
            event_date=event_data.event_date,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            event_type=event_data.event_type,
            location=getattr(event_data, "location", None),
            is_online=getattr(event_data, "is_online", False),
            tags=getattr(event_data, "tags", None),
        )

        # Add integration fields
        dto.reinforces_habit_uid = getattr(event_data, "reinforces_habit_uid", None)
        dto.milestone_celebration_for_goal = getattr(
            event_data, "milestone_celebration_for_goal", None
        )

        # Create event
        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        event = self._to_domain_model(create_result.value, EventDTO, Event)

        if conflicts:
            self.logger.warning(
                f"Event {event.uid} created with {len(conflicts)} conflicts (avoid_conflicts=False)"
            )
        else:
            self.logger.info(f"Event {event.uid} scheduled successfully")

        return Result.ok(event)

    # ========================================================================
    # TIME SLOT SUGGESTIONS
    # ========================================================================

    @with_error_handling("suggest_time_slots", error_type="database")
    async def suggest_time_slots(
        self,
        user_uid: str,
        target_date: date,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
    ) -> Result[list[dict[str, Any]]]:
        """
        Suggest available time slots on a given date.

        Args:
            user_uid: User identifier
            target_date: Date to find slots on
            duration_minutes: Required duration
            preferred_hours: Tuple of (start_hour, end_hour) for preferences

        Returns:
            Result containing list of available slots
        """
        # Get existing events on that date
        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date=target_date.isoformat(),
        )

        existing_events = result.value if result.is_ok and result.value else []

        # Build blocked time ranges
        blocked: list[tuple[time, time]] = []
        for event in existing_events:
            if event.start_time and event.end_time and event.status != EntityStatus.CANCELLED.value:
                blocked.append((event.start_time, event.end_time))

        # Sort by start time
        blocked.sort(key=get_tuple_first)

        # Find gaps
        slots = []
        current = time(preferred_hours[0], 0)
        end_of_day = time(preferred_hours[1], 0)

        for block_start, block_end in blocked:
            # Check gap before this block
            if current < block_start:
                gap_minutes = (
                    datetime.combine(target_date, block_start)
                    - datetime.combine(target_date, current)
                ).total_seconds() / 60

                if gap_minutes >= duration_minutes:
                    slots.append(
                        {
                            "start_time": current.isoformat(),
                            "end_time": block_start.isoformat(),
                            "available_minutes": int(gap_minutes),
                            "fits_duration": True,
                        }
                    )

            # Move current past this block
            if block_end > current:
                current = block_end

        # Check final gap
        if current < end_of_day:
            gap_minutes = (
                datetime.combine(target_date, end_of_day) - datetime.combine(target_date, current)
            ).total_seconds() / 60

            if gap_minutes >= duration_minutes:
                slots.append(
                    {
                        "start_time": current.isoformat(),
                        "end_time": end_of_day.isoformat(),
                        "available_minutes": int(gap_minutes),
                        "fits_duration": True,
                    }
                )

        self.logger.debug(f"Found {len(slots)} available slots on {target_date}")
        return Result.ok(slots)

    @with_error_handling("find_next_available_slot", error_type="database")
    async def find_next_available_slot(
        self,
        user_uid: str,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
        days_to_search: int = 7,
    ) -> Result[dict[str, Any] | None]:
        """
        Find the next available time slot across multiple days.

        Args:
            user_uid: User identifier
            duration_minutes: Required duration
            preferred_hours: Tuple of (start_hour, end_hour)
            days_to_search: Number of days to search ahead

        Returns:
            Result containing next available slot or None
        """
        current_date = date.today()

        for _ in range(days_to_search):
            slots_result = await self.suggest_time_slots(
                user_uid=user_uid,
                target_date=current_date,
                duration_minutes=duration_minutes,
                preferred_hours=preferred_hours,
            )

            if slots_result.is_ok and slots_result.value:
                slot = slots_result.value[0]
                slot["date"] = current_date.isoformat()
                return Result.ok(slot)

            current_date += timedelta(days=1)

        return Result.ok(None)

    # ========================================================================
    # RECURRING EVENT OPTIMIZATION
    # ========================================================================

    @with_error_handling("optimize_recurring_schedule", error_type="database")
    async def optimize_recurring_schedule(
        self,
        user_uid: str,
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
        user_uid: str,
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
            return Result.fail(dates_result.expect_error())

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
            dto = EventDTO.create_event(
                user_uid=user_uid,
                title=title,
                event_date=event_date,
                start_time=start_time,
                end_time=end_time,
                event_type="RECURRING",
            )
            dto.recurrence_pattern = pattern
            if reinforces_habit_uid:
                dto.reinforces_habit_uid = reinforces_habit_uid

            create_result = await self.backend.create(dto.to_dict())
            if create_result.is_ok:
                event = self._to_domain_model(create_result.value, EventDTO, Event)
                created_events.append(event)

        self.logger.info(f"Created {len(created_events)} recurring events")

        return Result.ok(created_events)

    # ========================================================================
    # CALENDAR ANALYSIS
    # ========================================================================

    @with_error_handling("get_busy_times", error_type="database", uid_param="user_uid")
    async def get_busy_times(
        self,
        user_uid: str,
        start_date: date,
        end_date: date,
    ) -> Result[dict[str, list[dict[str, str]]]]:
        """
        Get busy time blocks for a date range.

        Args:
            user_uid: User identifier
            start_date: Start of range
            end_date: End of range

        Returns:
            Result containing dict mapping dates to busy time blocks
        """
        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
            event_date__lte=end_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = result.value or []

        # Group by date
        busy_times: dict[str, list[dict[str, str]]] = {}
        for event in events:
            if not event.event_date or event.status == EntityStatus.CANCELLED.value:
                continue

            date_key = event.event_date.isoformat()
            if date_key not in busy_times:
                busy_times[date_key] = []

            busy_times[date_key].append(
                {
                    "event_uid": event.uid,
                    "title": event.title,
                    "start_time": event.start_time.isoformat() if event.start_time else "",
                    "end_time": event.end_time.isoformat() if event.end_time else "",
                }
            )

        return Result.ok(busy_times)

    @with_error_handling("get_calendar_density", error_type="database", uid_param="user_uid")
    async def get_calendar_density(
        self,
        user_uid: str,
        days_ahead: int = 14,
    ) -> Result[dict[str, Any]]:
        """
        Calculate calendar density (how busy the calendar is).

        Args:
            user_uid: User identifier
            days_ahead: Number of days to analyze

        Returns:
            Result containing density metrics
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        result = await self.backend.find_by(
            user_uid=user_uid,
            event_date__gte=start_date.isoformat(),
            event_date__lte=end_date.isoformat(),
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        events = [e for e in (result.value or []) if e.status != EntityStatus.CANCELLED.value]

        # Calculate metrics
        events_per_day = len(events) / days_ahead if days_ahead > 0 else 0

        # Count days with events
        days_with_events = len(set(e.event_date for e in events if e.event_date))

        # Calculate total scheduled time
        total_minutes = sum(e.duration_minutes or 0 for e in events)

        return Result.ok(
            {
                "user_uid": user_uid,
                "days_analyzed": days_ahead,
                "total_events": len(events),
                "events_per_day": round(events_per_day, 2),
                "days_with_events": days_with_events,
                "free_days": days_ahead - days_with_events,
                "total_scheduled_minutes": total_minutes,
                "average_minutes_per_day": round(total_minutes / days_ahead, 1)
                if days_ahead > 0
                else 0,
                "density_rating": "high"
                if events_per_day > 3
                else ("medium" if events_per_day > 1 else "low"),
            }
        )
