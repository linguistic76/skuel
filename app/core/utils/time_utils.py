"""
Time Utilities
==============

Time and date manipulation utilities for domain models.
Ensures consistent timezone handling (UTC internally).
"""

from datetime import UTC, date, datetime, time, timedelta

from core.models.enums import TimeOfDay


class TimeHelper:
    """Time and date manipulation utilities"""

    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC datetime with timezone awareness."""
        return datetime.now(UTC)

    @staticmethod
    def today_utc() -> date:
        """Get current UTC date."""
        return datetime.now(UTC).date()

    @staticmethod
    def ensure_utc(dt: datetime) -> datetime:
        """
        Ensure datetime is timezone-aware and in UTC.

        Args:
            dt: Datetime to convert

        Returns:
            UTC datetime with timezone
        """
        if dt.tzinfo is None:
            # Assume naive datetime is UTC
            return dt.replace(tzinfo=UTC)
        elif dt.tzinfo != UTC:
            # Convert to UTC
            return dt.astimezone(UTC)
        return dt

    @staticmethod
    def combine_date_time_utc(date_obj: date, time_obj: time) -> datetime:
        """
        Combine date and time into UTC datetime.

        Args:
            date_obj: Date component
            time_obj: Time component

        Returns:
            Combined UTC datetime
        """
        # Combine and set UTC timezone
        dt = datetime.combine(date_obj, time_obj)
        return dt.replace(tzinfo=UTC)

    @staticmethod
    def get_time_of_day(hour: int) -> TimeOfDay:
        """
        Determine time of day from hour.

        Args:
            hour: Hour (0-23)

        Returns:
            TimeOfDay enum value
        """
        if 5 <= hour < 12:
            return TimeOfDay.MORNING
        elif 12 <= hour < 17:
            return TimeOfDay.AFTERNOON
        elif 17 <= hour < 21:
            return TimeOfDay.EVENING
        else:
            return TimeOfDay.NIGHT

    @staticmethod
    def is_within_window(check_time: datetime, start: datetime, end: datetime) -> bool:
        """
        Check if time falls within window.

        Args:
            check_time: Time to check,
            start: Window start,
            end: Window end

        Returns:
            True if within window
        """
        # Ensure all times are UTC for comparison
        check_time = TimeHelper.ensure_utc(check_time)
        start = TimeHelper.ensure_utc(start)
        end = TimeHelper.ensure_utc(end)

        return start <= check_time <= end

    @staticmethod
    def calculate_duration_minutes(start: datetime, end: datetime) -> int:
        """
        Calculate duration in minutes between two times.

        Args:
            start: Start time
            end: End time

        Returns:
            Duration in minutes
        """
        # Ensure UTC for calculation
        start = TimeHelper.ensure_utc(start)
        end = TimeHelper.ensure_utc(end)

        duration = end - start
        return int(duration.total_seconds() / 60)

    @staticmethod
    def add_business_days(start_date: date, days: int) -> date:
        """
        Add business days (excluding weekends).

        Args:
            start_date: Starting date
            days: Number of business days to add

        Returns:
            Result date
        """
        current = start_date
        remaining = days

        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                remaining -= 1

        return current

    @staticmethod
    def format_duration(minutes: int) -> str:
        """
        Format duration in human-readable form.

        Args:
            minutes: Duration in minutes

        Returns:
            Formatted string (e.g., "2h 30m")
        """
        if minutes < 60:
            return f"{minutes}m"

        hours = minutes // 60
        mins = minutes % 60

        if mins == 0:
            return f"{hours}h"
        return f"{hours}h {mins}m"
