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

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums import EntityStatus
from core.services.user.intelligence._base import IntelligenceMixinBase

if TYPE_CHECKING:
    from core.ports.query_types import MomentumSignals

_ACTIVITY_DOMAINS = ("tasks", "goals", "habits", "events", "choices", "principles")


class TemporalMomentumMixin(IntelligenceMixinBase):
    """
    Mixin providing temporal momentum analysis for daily planning.

    Requires self.context (RichUserContext — entities_rich is rich-only).
    compute_momentum_signals() is synchronous — no await needed.
    """

    def compute_momentum_signals(self) -> MomentumSignals:
        """
        Compute temporal momentum signals from context.entities_rich.

        Returns:
            velocities: {domain: 0.0-1.0}  — completion ratio per domain
            neglected: [domain, ...]       — domains with zero window activity
            habit_consistency: float | None — mean adherence over the user's
                active habits (``context.habit_completion_rates``, derived at
                read time); None when they have none — an absent measurement,
                not a zero
            phase: "accelerating" | "steady" | "decelerating" | "unknown"

        Returns empty signals (phase "unknown") if entities_rich is unpopulated.
        """
        entities_rich = self.context.entities_rich
        if not entities_rich:
            return {
                "velocities": {},
                "neglected": [],
                "habit_consistency": None,
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
                1
                for item in items
                if item.get("entity", {}).get("status") == EntityStatus.COMPLETED
            )
            velocities[domain] = completed / len(items)

        # Habit consistency — the mean adherence of the active habits. With
        # nothing to average there is no consistency to report, low or otherwise.
        habit_rates = list(self.context.habit_completion_rates.values())
        habit_consistency = sum(habit_rates) / len(habit_rates) if habit_rates else None

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

    def _momentum_warnings(self, signals: MomentumSignals) -> list[str]:
        """Generate warning strings from momentum signals.

        The low-consistency warning needs a measured consistency: a user with no
        active habit gets none.
        """
        warnings: list[str] = []
        neglected = signals["neglected"]
        if neglected:
            domain_list = ", ".join(neglected[:3])
            warnings.append(f"No {domain_list} activity this period — consider engaging today")
        habit_consistency = signals["habit_consistency"]
        if habit_consistency is not None and habit_consistency < 0.4:
            warnings.append("Habit consistency is low — rebuilding streaks is today's priority")
        return warnings

    def _momentum_rationale(self, signals: MomentumSignals) -> str | None:
        """Return a rationale clause from momentum signals, or None if unknown."""
        phase = signals["phase"]
        if phase == "accelerating":
            return "Strong momentum across activity domains"
        if phase == "decelerating":
            return "Activity momentum declining — refocus today"
        return None
