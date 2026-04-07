"""Domain health status calculators.

Business rules for determining the health status ("healthy", "warning", "critical")
of each activity and curriculum domain based on entity counts.

These are pure functions — no I/O, no service calls.

See: /docs/patterns/UI_COMPONENT_PATTERNS.md
"""

from dataclasses import dataclass


@dataclass
class DomainStatus:
    """Calculate health status for each domain from entity counts."""

    @staticmethod
    def calculate_tasks_status(
        overdue_count: int,
        blocked_count: int,
    ) -> str:
        """Calculate tasks domain health status."""
        if overdue_count > 3 or blocked_count > 5:
            return "critical"
        elif overdue_count > 0 or blocked_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_habits_status(at_risk_count: int) -> str:
        """Calculate habits domain health status."""
        if at_risk_count > 2:
            return "critical"
        elif at_risk_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_goals_status(
        at_risk_count: int,
        stalled_count: int,
    ) -> str:
        """Calculate goals domain health status."""
        if at_risk_count > 0:
            return "critical"
        elif stalled_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_events_status(
        missed_today: int,
        missed_week: int,
    ) -> str:
        """Calculate events domain health status."""
        if missed_today > 0:
            return "critical"
        elif missed_week > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_principles_status(
        aligned_count: int,
        against_count: int,
    ) -> str:
        """Calculate principles domain health status."""
        if against_count > aligned_count:
            return "critical"
        elif aligned_count == 0 and against_count == 0:
            return "healthy"  # No decisions yet
        elif aligned_count < against_count * 2:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_choices_status(pending_count: int) -> str:
        """Calculate choices domain health status."""
        if pending_count > 5:
            return "critical"
        elif pending_count > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_knowledge_status(
        blocked: int,
        mastered: int,
        in_progress: int,
    ) -> str:
        """Calculate knowledge (KU) domain health status.

        Critical when blocked prerequisites outnumber active learning by 50%.
        """
        if blocked > (mastered + in_progress) * 0.5 and (mastered + in_progress) > 0:
            return "critical"
        elif blocked > 0:
            return "warning"
        return "healthy"

    @staticmethod
    def calculate_learning_paths_status(blocked: int, enrolled: int) -> str:
        """Calculate learning paths domain health status.

        Critical when blocked prerequisites outnumber enrolled paths by 50%.
        """
        if blocked > enrolled * 0.5 and enrolled > 0:
            return "critical"
        elif blocked > 0:
            return "warning"
        return "healthy"


__all__ = ["DomainStatus"]
