"""
Temporal Momentum Mixin
========================

Analyzes context.entities_rich to compute momentum signals for daily planning.
Reads the time-windowed activity data to detect patterns the user and planner
should act on: neglected domains, completion velocity, habit consistency.

These signals enrich get_ready_to_work_on_today() warnings and rationale.
No I/O — pure Python analysis of already-loaded UserContext data.

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext

_ACTIVITY_DOMAINS = ("tasks", "goals", "habits", "events", "choices", "principles")


class TemporalMomentumMixin:
    """
    Mixin providing temporal momentum analysis for daily planning.

    Requires self.context (UserContext) with entities_rich populated.
    compute_momentum_signals() is synchronous — no await needed.
    """

    context: "UserContext"

    def compute_momentum_signals(self) -> dict[str, Any]:
        """
        Compute temporal momentum signals from context.entities_rich.

        Returns dict with:
            velocities: {domain: 0.0-1.0}  — completion ratio per domain
            neglected: [domain, ...]       — domains with zero window activity
            habit_consistency: float       — avg completion_rate from habit entities
            phase: "accelerating" | "steady" | "decelerating"

        Returns empty signals if entities_rich is unpopulated (standard context).
        """
        entities_rich = self.context.entities_rich
        if not entities_rich:
            return {
                "velocities": {},
                "neglected": [],
                "habit_consistency": 0.0,
                "phase": "unknown",
            }

        velocities: dict[str, float] = {}
        neglected: list[str] = []

        for domain in _ACTIVITY_DOMAINS:
            items = entities_rich.get(domain, [])
            if not items:
                neglected.append(domain)
                velocities[domain] = 0.0
                continue
            completed = sum(
                1 for item in items if item.get("entity", {}).get("status") == "completed"
            )
            velocities[domain] = completed / len(items)

        # Habit consistency — use completion_rate field if available
        habit_items = entities_rich.get("habits", [])
        habit_rates = [
            item.get("entity", {}).get("completion_rate", 0.0)
            for item in habit_items
            if item.get("entity", {}).get("completion_rate") is not None
        ]
        habit_consistency = sum(habit_rates) / len(habit_rates) if habit_rates else 0.0

        # Overall phase from average velocity across active domains
        active_velocities = [v for d, v in velocities.items() if d not in neglected]
        avg_velocity = sum(active_velocities) / len(active_velocities) if active_velocities else 0.0
        if avg_velocity >= 0.6:
            phase = "accelerating"
        elif avg_velocity >= 0.3:
            phase = "steady"
        else:
            phase = "decelerating"

        return {
            "velocities": velocities,
            "neglected": neglected,
            "habit_consistency": habit_consistency,
            "phase": phase,
        }

    def _momentum_warnings(self, signals: dict[str, Any]) -> list[str]:
        """Generate warning strings from momentum signals."""
        warnings: list[str] = []
        neglected = signals.get("neglected", [])
        if neglected:
            domain_list = ", ".join(neglected[:3])
            warnings.append(f"No {domain_list} activity this period — consider engaging today")
        if signals.get("habit_consistency", 1.0) < 0.4:
            warnings.append("Habit consistency is low — rebuilding streaks is today's priority")
        return warnings

    def _momentum_rationale(self, signals: dict[str, Any]) -> str | None:
        """Return a rationale clause from momentum signals, or None if unknown."""
        phase = signals.get("phase", "unknown")
        if phase == "accelerating":
            return "Strong momentum across activity domains"
        if phase == "decelerating":
            return "Activity momentum declining — refocus today"
        return None
